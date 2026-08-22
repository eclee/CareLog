from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func

from models import (
    BowelRecord,
    MealRecord,
    MedPlan,
    MedRecord,
    MedSubmission,
    TIMESLOTS,
    VitalRecord,
    WaterRecord,
    db,
    get_care_parameters,
    get_elder_parameters,
    log_action,
)
from services.abnormal import (
    evaluate_bowel,
    evaluate_meal,
    evaluate_med_records,
    exclude_events_for_source,
)
from services.alerts import check_and_alert
from services.media import photos_for, save_images, soft_delete_record_photos
from translations import tr
from utils import active_elders, current_elder, current_user, get_lang, login_required


bp = Blueprint("front", __name__, url_prefix="/care")
INTAKES = ["all", "half", "little", "none"]


def _ctx(**kwargs):
    lang = get_lang()
    base = {
        "lang": lang,
        "t": lambda key: tr(lang, key),
        "user": current_user(),
        "elder": current_elder(),
        "elders": active_elders(),
        "today": date.today(),
    }
    base.update(kwargs)
    return base


def _uploaded_files(name="photos"):
    return request.files.getlist(name)


def _flash_media_errors(result):
    for error in result.errors:
        flash(error, "warn")


@bp.route("/")
@login_required("worker", "admin")
def home():
    elder = current_elder()
    if elder is None:
        return render_template(
            "front/home.html",
            **_ctx(status={}, water_total=0, bowel_count=0, vitals_count=0),
        )
    today = date.today()
    meal_done = {
        meal.timeslot: meal
        for meal in MealRecord.query.filter_by(elder_id=elder.id, record_date=today)
    }

    plans_all = MedPlan.query.filter_by(elder_id=elder.id, active=True).all()
    recorded = {
        record.med_plan_id
        for record in MedRecord.query.filter_by(elder_id=elder.id, record_date=today)
    }
    med_groups = []
    med_done = {}
    for slot in TIMESLOTS:
        slot_plans = [plan for plan in plans_all if plan.timeslot == slot]
        med_done[slot] = (
            all(plan.id in recorded for plan in slot_plans) if slot_plans else None
        )
        for relation in ("before", "after", "none"):
            group = [
                plan for plan in slot_plans if plan.meal_relation == relation
            ]
            if group:
                med_groups.append(
                    {
                        "slot": slot,
                        "rel": relation,
                        "count": len(group),
                        "done": all(plan.id in recorded for plan in group),
                    }
                )

    water_total = (
        db.session.query(func.coalesce(func.sum(WaterRecord.amount), 0))
        .filter_by(elder_id=elder.id, record_date=today)
        .scalar()
    )
    bowel_count = BowelRecord.query.filter_by(
        elder_id=elder.id, record_date=today
    ).count()
    vitals_count = VitalRecord.query.filter_by(
        elder_id=elder.id, record_date=today
    ).count()
    return render_template(
        "front/home.html",
        **_ctx(
            meal_done=meal_done,
            med_done=med_done,
            med_groups=med_groups,
            water_total=water_total,
            bowel_count=bowel_count,
            vitals_count=vitals_count,
            slots=TIMESLOTS,
        ),
    )


@bp.route("/elder/<int:eid>")
@login_required("worker", "admin")
def pick_elder(eid):
    if any(elder.id == eid for elder in active_elders()):
        session["elder_id"] = eid
    return redirect(request.referrer or url_for("front.home"))


# ---------------- meal ----------------


@bp.route("/meal/<slot>", methods=["GET", "POST"])
@login_required("worker", "admin")
def meal(slot):
    if slot not in TIMESLOTS:
        abort(404)
    elder = current_elder()
    if elder is None:
        return redirect(url_for("front.home"))
    today = date.today()
    record = MealRecord.query.filter_by(
        elder_id=elder.id, record_date=today, timeslot=slot
    ).first()

    if request.method == "POST":
        intake = request.form.get("intake")
        if intake not in INTAKES:
            abort(400)
        note = (request.form.get("note") or "").strip()
        supplement = {"yes": True, "no": False}.get(request.form.get("supplement"))
        supplement_cc = (
            request.form.get("supplement_cc", type=int) if supplement else None
        )
        if supplement_cc is not None and not 0 < supplement_cc <= 2000:
            supplement_cc = None
        user_id = session.get("user_id")
        if record:
            before = {"intake": record.intake, "note": record.note}
            record.intake = intake
            record.note = note
            record.created_by = user_id
            record.supplement = supplement
            record.supplement_cc = supplement_cc
            log_action(
                user_id,
                "update",
                "meal",
                record.id,
                f"{before['intake']} -> {intake}",
                elder_id=elder.id,
                event_code="meal.update",
                metadata={"before": before, "after": {"intake": intake, "note": note}},
            )
        else:
            record = MealRecord(
                elder_id=elder.id,
                record_date=today,
                timeslot=slot,
                intake=intake,
                note=note,
                created_by=user_id,
                supplement=supplement,
                supplement_cc=supplement_cc,
            )
            db.session.add(record)
            db.session.flush()
            log_action(
                user_id,
                "create",
                "meal",
                record.id,
                intake,
                elder_id=elder.id,
                event_code="meal.create",
                metadata={"timeslot": slot, "intake": intake},
            )

        max_photos = int(get_care_parameters().get("max_care_photos_per_record", 5))
        existing_photos = photos_for("meal", record.id, kind="care_evidence")
        result = save_images(
            _uploaded_files(),
            kind="care_evidence",
            record_type="meal",
            record_id=record.id,
            elder_id=elder.id,
            record_date=today,
            uploaded_by=user_id,
            limit=max(0, max_photos - len(existing_photos)),
            start_order=len(existing_photos),
        )
        db.session.commit()
        evaluate_meal(record)
        _flash_media_errors(result)
        flash(tr(get_lang(), "saved"), "ok")
        return redirect(url_for("front.home"))

    return render_template(
        "front/meal.html",
        **_ctx(
            slot=slot,
            rec=record,
            intakes=INTAKES,
            photos=photos_for("meal", record.id) if record else [],
        ),
    )


# ---------------- medication ----------------


@bp.route("/med/<slot>/<rel>", methods=["GET", "POST"])
@login_required("worker", "admin")
def med(slot, rel):
    if slot not in TIMESLOTS or rel not in ("before", "after", "none"):
        abort(404)
    elder = current_elder()
    if elder is None:
        return redirect(url_for("front.home"))
    today = date.today()
    plans = (
        MedPlan.query.filter_by(
            elder_id=elder.id,
            timeslot=slot,
            meal_relation=rel,
            active=True,
        )
        .order_by(MedPlan.id)
        .all()
    )
    plan_ids = [plan.id for plan in plans]
    existing = (
        {
            record.med_plan_id: record
            for record in MedRecord.query.filter(
                MedRecord.elder_id == elder.id,
                MedRecord.record_date == today,
                MedRecord.med_plan_id.in_(plan_ids),
            )
        }
        if plan_ids
        else {}
    )
    submission = MedSubmission.query.filter_by(
        elder_id=elder.id,
        record_date=today,
        timeslot=slot,
        meal_relation=rel,
    ).first()

    if request.method == "POST":
        user_id = session.get("user_id")
        if submission is None:
            submission = MedSubmission(
                elder_id=elder.id,
                record_date=today,
                timeslot=slot,
                meal_relation=rel,
                created_by=user_id,
            )
            db.session.add(submission)
            db.session.flush()
        else:
            submission.created_by = user_id

        changed_records = []
        for plan in plans:
            value = request.form.get(f"given_{plan.id}")
            if value not in ("yes", "no"):
                continue
            given = value == "yes"
            reason = (
                (request.form.get(f"reason_{plan.id}") or "").strip()
                if not given
                else ""
            )
            record = existing.get(plan.id)
            if record:
                before = {"given": record.given, "reason": record.reason}
                record.given = given
                record.reason = reason
                record.created_by = user_id
                record.submission_id = submission.id
                log_action(
                    user_id,
                    "update",
                    "med",
                    record.id,
                    f"{plan.name}: {before['given']} -> {given}",
                    elder_id=elder.id,
                    event_code="med.update",
                    metadata={"before": before, "after": {"given": given, "reason": reason}},
                )
            else:
                record = MedRecord(
                    elder_id=elder.id,
                    med_plan_id=plan.id,
                    submission_id=submission.id,
                    record_date=today,
                    given=given,
                    reason=reason,
                    created_by=user_id,
                )
                db.session.add(record)
                db.session.flush()
                log_action(
                    user_id,
                    "create",
                    "med",
                    record.id,
                    f"{plan.name}: {given}",
                    elder_id=elder.id,
                    event_code="med.create",
                    metadata={"plan_id": plan.id, "given": given, "reason": reason},
                )
            changed_records.append(record)

        max_photos = int(get_care_parameters().get("max_care_photos_per_record", 5))
        evidence = photos_for(
            "med_submission", submission.id, kind="care_evidence"
        )
        result = save_images(
            _uploaded_files(),
            kind="care_evidence",
            record_type="med_submission",
            record_id=submission.id,
            elder_id=elder.id,
            record_date=today,
            uploaded_by=user_id,
            limit=max(0, max_photos - len(evidence)),
            start_order=len(evidence),
        )
        db.session.commit()
        evaluate_med_records(changed_records)
        _flash_media_errors(result)
        flash(tr(get_lang(), "saved"), "ok")
        return redirect(url_for("front.home"))

    plan_photos = {
        plan.id: photos_for("medplan", plan.id, kind="med_reference") for plan in plans
    }
    evidence_photos = (
        photos_for("med_submission", submission.id, kind="care_evidence")
        if submission
        else []
    )
    return render_template(
        "front/med.html",
        **_ctx(
            slot=slot,
            rel=rel,
            plans=plans,
            existing=existing,
            plan_photos=plan_photos,
            evidence_photos=evidence_photos,
        ),
    )


# ---------------- vitals ----------------


@bp.route("/vitals", methods=["GET", "POST"])
@login_required("worker", "admin")
def vitals():
    elder = current_elder()
    if elder is None:
        return redirect(url_for("front.home"))
    today = date.today()
    lang = get_lang()
    vital_defaults = get_elder_parameters(elder.id).get("vital_defaults", {})

    if request.method == "POST":
        ranges = {
            "weight": (float, 20, 300),
            "systolic": (int, 50, 260),
            "diastolic": (int, 30, 180),
            "pulse": (int, 30, 220),
            "spo2": (int, 50, 100),
        }
        values = {}
        invalid = False
        for name, (caster, minimum, maximum) in ranges.items():
            raw = (request.form.get(name) or "").strip()
            if not raw:
                values[name] = None
                continue
            try:
                value = caster(raw)
            except ValueError:
                invalid = True
                values[name] = None
                continue
            if value < minimum or value > maximum:
                invalid = True
            values[name] = value
        if invalid:
            flash(tr(lang, "invalid_value"), "error")
            return redirect(url_for("front.vitals"))
        if all(value is None for value in values.values()):
            flash(tr(lang, "at_least_one"), "error")
            return redirect(url_for("front.vitals"))

        user_id = session.get("user_id")
        record = VitalRecord(
            elder_id=elder.id,
            record_date=today,
            note=(request.form.get("note") or "").strip(),
            created_by=user_id,
            **values,
        )
        db.session.add(record)
        db.session.flush()
        log_action(
            user_id,
            "create",
            "vital",
            record.id,
            "",
            elder_id=elder.id,
            event_code="vital.create",
            metadata=values,
        )
        result = save_images(
            _uploaded_files(),
            kind="care_evidence",
            record_type="vital",
            record_id=record.id,
            elder_id=elder.id,
            record_date=today,
            uploaded_by=user_id,
            limit=int(get_care_parameters().get("max_care_photos_per_record", 5)),
        )
        db.session.commit()
        warnings = check_and_alert(elder, record, lang=lang)
        _flash_media_errors(result)
        flash(tr(lang, "saved"), "ok")
        for warning in warnings:
            flash("⚠️ " + warning, "warn")
        return redirect(url_for("front.vitals"))

    todays = (
        VitalRecord.query.filter_by(elder_id=elder.id, record_date=today)
        .order_by(VitalRecord.recorded_at.desc())
        .all()
    )
    return render_template(
        "front/vitals.html",
        **_ctx(todays=todays, vital_defaults=vital_defaults),
    )


@bp.route("/vitals/<int:rid>/delete", methods=["POST"])
@login_required("worker", "admin")
def vitals_delete(rid):
    record = db.session.get(VitalRecord, rid)
    if record and record.record_date == date.today():
        user_id = session.get("user_id")
        log_action(
            user_id,
            "delete",
            "vital",
            rid,
            "",
            elder_id=record.elder_id,
            event_code="vital.delete",
        )
        soft_delete_record_photos("vital", rid, user_id=user_id)
        exclude_events_for_source("vital", rid, user_id=user_id)
        db.session.delete(record)
        db.session.commit()
    return redirect(url_for("front.vitals"))


# ---------------- water ----------------


@bp.route("/water", methods=["GET", "POST"])
@login_required("worker", "admin")
def water():
    elder = current_elder()
    if elder is None:
        return redirect(url_for("front.home"))
    today = date.today()
    params = get_care_parameters()
    minimum = int(params.get("water_entry_min_ml", 10))
    maximum = int(params.get("water_entry_max_ml", 2000))
    quick_amounts = [
        int(value) for value in params.get("water_quick_amounts_ml", [100, 250, 500])
    ]
    if request.method == "POST":
        amount = request.form.get("amount", type=int)
        if amount is None or not minimum <= amount <= maximum:
            flash(tr(get_lang(), "invalid_value"), "error")
            return redirect(url_for("front.water"))
        user_id = session.get("user_id")
        record = WaterRecord(
            elder_id=elder.id,
            record_date=today,
            amount=amount,
            created_by=user_id,
        )
        db.session.add(record)
        db.session.flush()
        log_action(
            user_id,
            "create",
            "water",
            record.id,
            f"{amount}ml",
            elder_id=elder.id,
            event_code="water.create",
            metadata={"amount": amount},
        )
        db.session.commit()
        return redirect(url_for("front.water"))

    events = (
        WaterRecord.query.filter_by(elder_id=elder.id, record_date=today)
        .order_by(WaterRecord.recorded_at.desc())
        .all()
    )
    total = sum(event.amount for event in events)
    return render_template(
        "front/water.html",
        **_ctx(
            events=events,
            total=total,
            quick_amounts=quick_amounts,
            water_min=minimum,
            water_max=maximum,
        ),
    )


@bp.route("/water/<int:rid>/delete", methods=["POST"])
@login_required("worker", "admin")
def water_delete(rid):
    record = db.session.get(WaterRecord, rid)
    if record and record.record_date == date.today():
        log_action(
            session.get("user_id"),
            "delete",
            "water",
            rid,
            f"{record.amount}ml",
            elder_id=record.elder_id,
            event_code="water.delete",
        )
        db.session.delete(record)
        db.session.commit()
    return redirect(url_for("front.water"))


# ---------------- bowel ----------------


@bp.route("/bowel", methods=["GET", "POST"])
@login_required("worker", "admin")
def bowel():
    elder = current_elder()
    if elder is None:
        return redirect(url_for("front.home"))
    today = date.today()
    if request.method == "POST":
        bowel_type = request.form.get("bristol_type", type=int)
        if not bowel_type or not 1 <= bowel_type <= 7:
            abort(400)
        user_id = session.get("user_id")
        record = BowelRecord(
            elder_id=elder.id,
            record_date=today,
            bristol_type=bowel_type,
            note=(request.form.get("note") or "").strip(),
            created_by=user_id,
        )
        db.session.add(record)
        db.session.flush()
        log_action(
            user_id,
            "create",
            "bowel",
            record.id,
            f"type{bowel_type}",
            elder_id=elder.id,
            event_code="bowel.create",
            metadata={"bristol_type": bowel_type},
        )
        result = save_images(
            _uploaded_files(),
            kind="care_evidence",
            record_type="bowel",
            record_id=record.id,
            elder_id=elder.id,
            record_date=today,
            uploaded_by=user_id,
            limit=int(get_care_parameters().get("max_care_photos_per_record", 5)),
        )
        db.session.commit()
        evaluate_bowel(record)
        _flash_media_errors(result)
        flash(tr(get_lang(), "saved"), "ok")
        return redirect(url_for("front.bowel"))

    todays = (
        BowelRecord.query.filter_by(elder_id=elder.id, record_date=today)
        .order_by(BowelRecord.recorded_at.desc())
        .all()
    )
    return render_template("front/bowel.html", **_ctx(todays=todays))


@bp.route("/bowel/<int:rid>/delete", methods=["POST"])
@login_required("worker", "admin")
def bowel_delete(rid):
    record = db.session.get(BowelRecord, rid)
    if record and record.record_date == date.today():
        user_id = session.get("user_id")
        log_action(
            user_id,
            "delete",
            "bowel",
            rid,
            "",
            elder_id=record.elder_id,
            event_code="bowel.delete",
        )
        soft_delete_record_photos("bowel", rid, user_id=user_id)
        exclude_events_for_source("bowel", rid, user_id=user_id)
        db.session.delete(record)
        db.session.commit()
    return redirect(url_for("front.bowel"))
