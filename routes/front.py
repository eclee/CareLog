import os
from datetime import date

from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash, send_from_directory, current_app, abort)
from sqlalchemy import func

from models import (db, MealRecord, MedRecord, MedPlan, VitalRecord, WaterRecord,
                    BowelRecord, Photo, TIMESLOTS, log_action)
from utils import (login_required, current_user, get_lang, current_elder,
                   active_elders, save_photos, photos_for)
from translations import tr
from services.alerts import check_and_alert

bp = Blueprint("front", __name__, url_prefix="/care")

INTAKES = ["all", "half", "little", "none"]


def _ctx(**kw):
    lang = get_lang()
    base = dict(lang=lang, t=lambda k: tr(lang, k), user=current_user(),
                elder=current_elder(), elders=active_elders(), today=date.today())
    base.update(kw)
    return base


@bp.route("/")
@login_required("worker", "admin")
def home():
    elder = current_elder()
    if elder is None:
        return render_template("front/home.html", **_ctx(status={}, water_total=0,
                                                         bowel_count=0, vitals_count=0))
    today = date.today()
    meal_done = {m.timeslot: m for m in MealRecord.query.filter_by(
        elder_id=elder.id, record_date=today)}

    # 用藥依「時段 × 餐前/飯後」分組：早/中/晚各可有餐前、飯後，睡前不分
    plans_all = MedPlan.query.filter_by(elder_id=elder.id, active=True).all()
    recorded = {r.med_plan_id for r in MedRecord.query.filter_by(
        elder_id=elder.id, record_date=today)}
    med_groups = []
    med_done = {}   # per-slot: True/False/None（無藥）供狀態圓點使用
    for s in TIMESLOTS:
        slot_plans = [p for p in plans_all if p.timeslot == s]
        med_done[s] = (all(p.id in recorded for p in slot_plans)
                       if slot_plans else None)
        for rel in ("before", "after", "none"):
            grp = [p for p in slot_plans if p.meal_relation == rel]
            if grp:
                med_groups.append({
                    "slot": s, "rel": rel, "count": len(grp),
                    "done": all(p.id in recorded for p in grp)})

    water_total = (db.session.query(func.coalesce(func.sum(WaterRecord.amount), 0))
                   .filter_by(elder_id=elder.id, record_date=today).scalar())
    bowel_count = BowelRecord.query.filter_by(elder_id=elder.id, record_date=today).count()
    vitals_count = VitalRecord.query.filter_by(elder_id=elder.id, record_date=today).count()

    return render_template("front/home.html", **_ctx(
        meal_done=meal_done, med_done=med_done, med_groups=med_groups,
        water_total=water_total, bowel_count=bowel_count,
        vitals_count=vitals_count, slots=TIMESLOTS))


@bp.route("/elder/<int:eid>")
@login_required("worker", "admin")
def pick_elder(eid):
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
    rec = MealRecord.query.filter_by(elder_id=elder.id, record_date=today,
                                     timeslot=slot).first()
    if request.method == "POST":
        intake = request.form.get("intake")
        if intake not in INTAKES:
            abort(400)
        note = (request.form.get("note") or "").strip()
        sup_raw = request.form.get("supplement")            # yes / no / None
        supplement = {"yes": True, "no": False}.get(sup_raw)
        sup_cc = request.form.get("supplement_cc", type=int) if supplement else None
        if sup_cc is not None and not 0 < sup_cc <= 2000:
            sup_cc = None
        uid = session.get("user_id")
        if rec:
            log_action(uid, "update", "meal", rec.id,
                       f"{rec.intake}->{intake}")
            rec.intake, rec.note, rec.created_by = intake, note, uid
            rec.supplement, rec.supplement_cc = supplement, sup_cc
        else:
            rec = MealRecord(elder_id=elder.id, record_date=today, timeslot=slot,
                             intake=intake, note=note, created_by=uid,
                             supplement=supplement, supplement_cc=sup_cc)
            db.session.add(rec)
            db.session.flush()
            log_action(uid, "create", "meal", rec.id, intake)
        db.session.commit()
        save_photos(request.files.getlist("photos"), "meal", rec.id, elder.id)
        flash(tr(get_lang(), "saved"), "ok")
        return redirect(url_for("front.home"))

    return render_template("front/meal.html", **_ctx(
        slot=slot, rec=rec, intakes=INTAKES,
        photos=photos_for("meal", rec.id) if rec else []))


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
    plans = MedPlan.query.filter_by(elder_id=elder.id, timeslot=slot,
                                    meal_relation=rel,
                                    active=True).order_by(MedPlan.id).all()
    existing = {r.med_plan_id: r for r in MedRecord.query.filter(
        MedRecord.elder_id == elder.id, MedRecord.record_date == today,
        MedRecord.med_plan_id.in_([p.id for p in plans]))} if plans else {}

    if request.method == "POST":
        uid = session.get("user_id")
        first_rec = None
        for p in plans:
            val = request.form.get(f"given_{p.id}")
            if val not in ("yes", "no"):
                continue
            given = val == "yes"
            reason = (request.form.get(f"reason_{p.id}") or "").strip() if not given else ""
            rec = existing.get(p.id)
            if rec:
                log_action(uid, "update", "med", rec.id,
                           f"{p.name}: {rec.given}->{given}")
                rec.given, rec.reason, rec.created_by = given, reason, uid
            else:
                rec = MedRecord(elder_id=elder.id, med_plan_id=p.id, record_date=today,
                                given=given, reason=reason, created_by=uid)
                db.session.add(rec)
                db.session.flush()
                log_action(uid, "create", "med", rec.id, f"{p.name}: {given}")
            first_rec = first_rec or rec
        db.session.commit()
        if first_rec:
            save_photos(request.files.getlist("photos"), "med", first_rec.id, elder.id)
        flash(tr(get_lang(), "saved"), "ok")
        return redirect(url_for("front.home"))

    return render_template("front/med.html", **_ctx(slot=slot, rel=rel, plans=plans,
                                                    existing=existing))


# ---------------- vitals ----------------

@bp.route("/vitals", methods=["GET", "POST"])
@login_required("worker", "admin")
def vitals():
    elder = current_elder()
    if elder is None:
        return redirect(url_for("front.home"))
    today = date.today()
    lang = get_lang()

    if request.method == "POST":
        def num(name, cast):
            raw = (request.form.get(name) or "").strip()
            try:
                return cast(raw) if raw else None
            except ValueError:
                return None
        rec = VitalRecord(elder_id=elder.id, record_date=today,
                          weight=num("weight", float), systolic=num("systolic", int),
                          diastolic=num("diastolic", int), pulse=num("pulse", int),
                          spo2=num("spo2", int),
                          note=(request.form.get("note") or "").strip(),
                          created_by=session.get("user_id"))
        if all(getattr(rec, f) is None for f in
               ("weight", "systolic", "diastolic", "pulse", "spo2")):
            flash(tr(lang, "at_least_one"), "error")
            return redirect(url_for("front.vitals"))
        db.session.add(rec)
        db.session.flush()
        log_action(session.get("user_id"), "create", "vital", rec.id, "")
        db.session.commit()
        save_photos(request.files.getlist("photos"), "vital", rec.id, elder.id)
        warnings = check_and_alert(elder, rec, lang=lang)
        flash(tr(lang, "saved"), "ok")
        for w in warnings:
            flash("⚠️ " + w, "warn")
        return redirect(url_for("front.vitals"))

    todays = VitalRecord.query.filter_by(elder_id=elder.id, record_date=today) \
        .order_by(VitalRecord.recorded_at.desc()).all()
    return render_template("front/vitals.html", **_ctx(todays=todays))


@bp.route("/vitals/<int:rid>/delete", methods=["POST"])
@login_required("worker", "admin")
def vitals_delete(rid):
    rec = db.session.get(VitalRecord, rid)
    if rec and rec.record_date == date.today():
        log_action(session.get("user_id"), "delete", "vital", rid, "")
        db.session.delete(rec)
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
    if request.method == "POST":
        amount = request.form.get("amount", type=int)
        if amount and 0 < amount <= 2000:
            rec = WaterRecord(elder_id=elder.id, record_date=today, amount=amount,
                              created_by=session.get("user_id"))
            db.session.add(rec)
            db.session.flush()
            log_action(session.get("user_id"), "create", "water", rec.id, f"{amount}ml")
            db.session.commit()
        return redirect(url_for("front.water"))

    events = WaterRecord.query.filter_by(elder_id=elder.id, record_date=today) \
        .order_by(WaterRecord.recorded_at.desc()).all()
    total = sum(e.amount for e in events)
    return render_template("front/water.html", **_ctx(events=events, total=total))


@bp.route("/water/<int:rid>/delete", methods=["POST"])
@login_required("worker", "admin")
def water_delete(rid):
    rec = db.session.get(WaterRecord, rid)
    if rec and rec.record_date == date.today():
        log_action(session.get("user_id"), "delete", "water", rid, f"{rec.amount}ml")
        db.session.delete(rec)
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
        btype = request.form.get("bristol_type", type=int)
        if not btype or not 1 <= btype <= 7:
            abort(400)
        rec = BowelRecord(elder_id=elder.id, record_date=today, bristol_type=btype,
                          note=(request.form.get("note") or "").strip(),
                          created_by=session.get("user_id"))
        db.session.add(rec)
        db.session.flush()
        log_action(session.get("user_id"), "create", "bowel", rec.id, f"type{btype}")
        db.session.commit()
        save_photos(request.files.getlist("photos"), "bowel", rec.id, elder.id)
        flash(tr(get_lang(), "saved"), "ok")
        return redirect(url_for("front.bowel"))

    todays = BowelRecord.query.filter_by(elder_id=elder.id, record_date=today) \
        .order_by(BowelRecord.recorded_at.desc()).all()
    return render_template("front/bowel.html", **_ctx(todays=todays))


@bp.route("/bowel/<int:rid>/delete", methods=["POST"])
@login_required("worker", "admin")
def bowel_delete(rid):
    rec = db.session.get(BowelRecord, rid)
    if rec and rec.record_date == date.today():
        log_action(session.get("user_id"), "delete", "bowel", rid, "")
        db.session.delete(rec)
        db.session.commit()
    return redirect(url_for("front.bowel"))


# ---------------- protected photo serving ----------------

@bp.route("/uploads/<path:fname>")
@login_required()
def uploaded(fname):
    return send_from_directory(current_app.config["UPLOAD_DIR"], fname)
