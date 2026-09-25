from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, jsonify, render_template, request

from models import (
    BowelRecord,
    Elder,
    MealRecord,
    MedRecord,
    Photo,
    VitalRecord,
    WaterRecord,
    db,
    get_care_parameters,
)
from services.analytics import daily_fluids, fluid_summary, period_buckets
from services.medication import plan_adherence
from services.media import active_photos_query
from services.query_filters import request_date_range
from translations import tr
from utils import get_lang
from utils import active_elders, can_access_elder, current_user, login_required


bp = Blueprint("family", __name__, url_prefix="/family")


def _number_stats(values, digits=1):
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return {"avg": None, "min": None, "max": None, "count": 0}
    return {
        "avg": round(sum(cleaned) / len(cleaned), digits),
        "min": min(cleaned),
        "max": max(cleaned),
        "count": len(cleaned),
    }


def _default_days():
    return max(1, min(int(get_care_parameters().get("dashboard_default_days", 30)), 180))


def _period_default():
    days = _default_days()
    return date.today() - timedelta(days=days - 1), date.today(), days


def _period():
    """Interpret either a preset or an inclusive historical date range."""
    first, last = request.args.get("start"), request.args.get("end")
    if first or last:
        if not first or not last:
            raise ValueError("自訂區間須同時填寫起日與迄日")
        try:
            start, end = date.fromisoformat(first), date.fromisoformat(last)
        except ValueError:
            raise ValueError("請輸入有效的起訖日期") from None
        if start > end or end > date.today():
            raise ValueError("起日不得晚於迄日，迄日不得晚於今天")
        return start, end, None
    days = max(1, min(request.args.get("days", type=int) or _default_days(), 180))
    return date.today() - timedelta(days=days - 1), date.today(), days


@bp.route("/")
@login_required("family", "admin", "worker")
def dashboard():
    elders = active_elders()
    requested_eid = request.args.get("elder", type=int)
    valid_ids = {elder.id for elder in elders}
    elder_id = (
        requested_eid
        if requested_eid in valid_ids
        else (elders[0].id if elders else None)
    )
    try:
        start, end, days = _period()
        error = None
    except ValueError as exc:
        start, end, days = _period_default()
        error = str(exc)
    return render_template(
        "family/dashboard.html",
        elders=elders,
        eid=elder_id,
        days=days,
        start=start,
        end=end,
        period_error=error,
        today=date.today(),
        bristol_labels=[tr(get_lang(), f"bristol_{i}") for i in range(1, 8)],
        user=current_user(),
    )


@bp.route("/data")
@login_required("family", "admin", "worker")
def data():
    elder_id = request.args.get("elder", type=int)
    try:
        start, end, days = _period()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    elder = Elder.query.filter_by(id=elder_id, active=True).first() if can_access_elder(elder_id) else None
    if elder is None:
        return jsonify({"error": "no elder"}), 404
    vitals = (
        VitalRecord.query.filter(
            VitalRecord.elder_id == elder_id, VitalRecord.record_date >= start,
            VitalRecord.record_date <= end,
        )
        .order_by(VitalRecord.recorded_at)
        .all()
    )
    fluids = daily_fluids(elder_id, start, end)
    medications = MedRecord.query.filter(
        MedRecord.elder_id == elder_id, MedRecord.record_date >= start,
        MedRecord.record_date <= end,
    ).all()
    meals = MealRecord.query.filter(
        MealRecord.elder_id == elder_id, MealRecord.record_date >= start,
        MealRecord.record_date <= end,
    ).all()
    bowels = BowelRecord.query.filter(
        BowelRecord.elder_id == elder_id, BowelRecord.record_date >= start,
        BowelRecord.record_date <= end,
    ).all()

    med_rate = (
        round(sum(1 for item in medications if item.given) * 100 / len(medications))
        if medications
        else None
    )
    intake_sum = {
        key: sum(1 for meal in meals if meal.intake == key)
        for key in ("all", "half", "little", "none")
    }
    vital_summary = {
        "weight": _number_stats([item.weight for item in vitals], 2),
        "systolic": _number_stats([item.systolic for item in vitals], 1),
        "diastolic": _number_stats([item.diastolic for item in vitals], 1),
        "pulse": _number_stats([item.pulse for item in vitals], 1),
        "spo2": _number_stats([item.spo2 for item in vitals], 1),
    }
    water_summary = fluid_summary(fluids, start, end)
    labels, bucket_key = period_buckets(start, end)
    chart = {label: {"d": label, "water": 0, "supplement": 0,
                     "bowel": [0] * 7, "recorded": False} for label in labels}
    for day, entry in fluids.items():
        row = chart[bucket_key(day).isoformat()]
        row["water"] += entry["water"]
        row["supplement"] += entry["supplement"]
        row["recorded"] = row["recorded"] or bool(entry["water"] or entry["supplement"] or not entry["unknown"])
    for bowel in bowels:
        chart[bucket_key(bowel.record_date).isoformat()]["bowel"][bowel.bristol_type - 1] += 1
    abnormal_types = set(get_care_parameters().get("abnormal_rules", {}).get("bowel_types", [1, 2, 6, 7]))
    adherence = plan_adherence(elder_id, start, end)

    return jsonify(
        {
            "elder": {"name": elder.name, "water_goal": elder.water_goal},
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "vitals": [
                {
                    "t": vital.recorded_at.strftime("%m/%d %H:%M"),
                    "d": vital.record_date.isoformat(),
                    "weight": vital.weight,
                    "systolic": vital.systolic,
                    "diastolic": vital.diastolic,
                    "pulse": vital.pulse,
                    "spo2": vital.spo2,
                }
                for vital in vitals
            ],
            "vital_summary": vital_summary,
            "water": [{"d": row["d"], "water": row["water"] if row["recorded"] else None,
                       "supplement": row["supplement"] if row["recorded"] else None}
                      for row in chart.values()],
            "bowel_chart": [{"d": row["d"], "types": row["bowel"]} for row in chart.values()],
            "water_summary": water_summary,
            "med_rate": med_rate,
            "plan_rate": adherence["rate"],
            "plan_adherence": adherence,
            "med_total": len(medications),
            "med_given": sum(1 for item in medications if item.given),
            "meal_intake": intake_sum,
            "bowel_count": len(bowels),
            "bowel_abnormal": sum(
                1 for item in bowels if item.bristol_type in abnormal_types
            ),
        }
    )


@bp.route("/photos")
@login_required("family", "admin", "worker")
def photos():
    elders = active_elders()
    elder_id = request.args.get("elder", type=int)
    valid_ids = {elder.id for elder in elders}
    if elder_id not in valid_ids:
        elder_id = elders[0].id if elders else None

    query = active_photos_query()
    if elder_id:
        query = query.filter(Photo.elder_id == elder_id)
    else:
        query = query.filter(Photo.id == -1)
    kind = request.args.get("kind")
    record_type = request.args.get("type")
    if kind in ("care_evidence", "med_reference", "abnormal_followup"):
        query = query.filter(Photo.kind == kind)
    if record_type:
        query = query.filter(Photo.record_type == record_type)
    date_range = request_date_range()
    if date_range.start_date:
        query = query.filter(Photo.record_date >= date_range.start_date)
    if date_range.end_date:
        query = query.filter(Photo.record_date <= date_range.end_date)
    items = query.order_by(Photo.record_date.desc(), Photo.uploaded_at.desc()).limit(120).all()
    return render_template(
        "family/photos.html",
        photos=items,
        elders=elders,
        eid=elder_id,
        user=current_user(),
        date_range=date_range,
    )
