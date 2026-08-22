from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import func

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
from services.media import active_photos_query
from services.query_filters import request_date_range
from utils import active_elders, current_user, login_required


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
    days = max(1, min(request.args.get("days", type=int) or _default_days(), 180))
    return render_template(
        "family/dashboard.html",
        elders=elders,
        eid=elder_id,
        days=days,
        user=current_user(),
    )


@bp.route("/data")
@login_required("family", "admin", "worker")
def data():
    elder_id = request.args.get("elder", type=int)
    days = max(1, min(request.args.get("days", type=int) or _default_days(), 180))
    elder = Elder.query.filter_by(id=elder_id, active=True).first() if elder_id else None
    if elder is None:
        return jsonify({"error": "no elder"}), 404
    start = date.today() - timedelta(days=days - 1)

    vitals = (
        VitalRecord.query.filter(
            VitalRecord.elder_id == elder_id, VitalRecord.record_date >= start
        )
        .order_by(VitalRecord.recorded_at)
        .all()
    )
    water_rows = (
        db.session.query(WaterRecord.record_date, func.sum(WaterRecord.amount))
        .filter(WaterRecord.elder_id == elder_id, WaterRecord.record_date >= start)
        .group_by(WaterRecord.record_date)
        .order_by(WaterRecord.record_date)
        .all()
    )
    medications = MedRecord.query.filter(
        MedRecord.elder_id == elder_id, MedRecord.record_date >= start
    ).all()
    meals = MealRecord.query.filter(
        MealRecord.elder_id == elder_id, MealRecord.record_date >= start
    ).all()
    bowels = BowelRecord.query.filter(
        BowelRecord.elder_id == elder_id, BowelRecord.record_date >= start
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
        "weight": _number_stats([item.weight for item in vitals], 1),
        "systolic": _number_stats([item.systolic for item in vitals], 1),
        "diastolic": _number_stats([item.diastolic for item in vitals], 1),
        "pulse": _number_stats([item.pulse for item in vitals], 1),
        "spo2": _number_stats([item.spo2 for item in vitals], 1),
    }
    water_by_date = {row_date: int(total or 0) for row_date, total in water_rows}
    water_daily = [
        (
            start + timedelta(days=offset),
            water_by_date.get(start + timedelta(days=offset)),
        )
        for offset in range(days)
    ]
    recorded_water_values = [int(total or 0) for _row_date, total in water_rows]
    water_summary = _number_stats(recorded_water_values, 0)
    water_summary["period_avg"] = (
        round(sum(recorded_water_values) / days) if days else None
    )
    water_summary["recorded_days"] = len(water_rows)
    water_summary["total_days"] = days

    return jsonify(
        {
            "elder": {"name": elder.name, "water_goal": elder.water_goal},
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
            "water": [
                {"d": day.strftime("%m/%d"), "ml": total}
                for day, total in water_daily
            ],
            "water_summary": water_summary,
            "med_rate": med_rate,
            "med_total": len(medications),
            "med_given": sum(1 for item in medications if item.given),
            "meal_intake": intake_sum,
            "bowel_count": len(bowels),
            "bowel_abnormal": sum(
                1 for item in bowels if item.bristol_type in (1, 2, 6, 7)
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
