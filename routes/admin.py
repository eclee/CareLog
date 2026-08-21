from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import SQLAlchemyError

from models import (
    db,
    User,
    Elder,
    MedPlan,
    MealRecord,
    MedRecord,
    VitalRecord,
    WaterRecord,
    BowelRecord,
    AuditLog,
    TIMESLOTS,
    get_setting,
    set_setting,
    log_action,
)
from services.mailer import MailNotConfigured, send_mail
from services.reports import build_report
from translations import LANGUAGES, normalize_lang
from utils import current_user, login_required

bp = Blueprint("admin", __name__, url_prefix="/admin")

SLOT_ZH = {"morning": "早上", "noon": "中午", "evening": "晚上", "bedtime": "睡前"}
REL_ZH = {"before": "餐前", "after": "飯後", "none": "—"}
ROLE_ZH = {"admin": "管理者", "family": "家屬", "worker": "照顧者"}
DEFAULT_ELDER_BIRTHDAY = date(1940, 1, 1)


def _ctx(**kw):
    base = {
        "user": current_user(),
        "SLOT_ZH": SLOT_ZH,
        "REL_ZH": REL_ZH,
        "ROLE_ZH": ROLE_ZH,
        "LANGUAGES": LANGUAGES,
    }
    base.update(kw)
    return base


@bp.route("/")
@login_required("admin")
def index():
    return render_template(
        "admin/index.html",
        **_ctx(
            elder_count=Elder.query.filter_by(active=True).count(),
            user_count=User.query.filter_by(active=True).count(),
            plan_count=MedPlan.query.filter_by(active=True).count(),
        ),
    )


# ---------------- elders ----------------


@bp.route("/elders", methods=["GET", "POST"])
@login_required("admin")
def elders():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            raw = request.form.get("birthday") or DEFAULT_ELDER_BIRTHDAY.isoformat()
            try:
                birthday = datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                birthday = DEFAULT_ELDER_BIRTHDAY
            elder = Elder(
                name=name,
                birthday=birthday,
                notes=(request.form.get("notes") or "").strip(),
                water_goal=request.form.get("water_goal", type=int) or 1500,
            )
            db.session.add(elder)
            db.session.flush()
            log_action(session.get("user_id"), "create", "elder", elder.id, elder.name)
            db.session.commit()
            flash("長輩資料已新增", "ok")
        return redirect(url_for("admin.elders"))
    return render_template(
        "admin/elders.html",
        **_ctx(
            elders=Elder.query.order_by(Elder.id).all(),
            default_birthday=DEFAULT_ELDER_BIRTHDAY,
        ),
    )


@bp.route("/elders/<int:eid>/edit", methods=["POST"])
@login_required("admin")
def elder_edit(eid):
    elder = db.session.get(Elder, eid)
    if elder:
        old_name = elder.name
        elder.name = (request.form.get("name") or elder.name).strip()
        raw = request.form.get("birthday")
        if raw:
            try:
                elder.birthday = datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                pass
        elder.notes = (request.form.get("notes") or "").strip()
        elder.water_goal = request.form.get("water_goal", type=int) or elder.water_goal
        elder.active = request.form.get("active") == "on"
        log_action(
            session.get("user_id"),
            "update",
            "elder",
            elder.id,
            f"{old_name} -> {elder.name}; active={elder.active}",
        )
        db.session.commit()
        flash("長輩資料已更新", "ok")
    return redirect(url_for("admin.elders"))


# ---------------- medication plans ----------------


@bp.route("/medplans", methods=["GET", "POST"])
@login_required("admin")
def medplans():
    elders_all = Elder.query.filter_by(active=True).order_by(Elder.id).all()
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        eid = request.form.get("elder_id", type=int)
        slot = request.form.get("timeslot")
        relation = request.form.get("meal_relation") or "none"
        if slot == "bedtime":
            relation = "none"
        if name and eid and slot in TIMESLOTS and relation in ("before", "after", "none"):
            plan = MedPlan(
                elder_id=eid,
                name=name,
                timeslot=slot,
                meal_relation=relation,
                dose_note=(request.form.get("dose_note") or "").strip(),
            )
            db.session.add(plan)
            db.session.flush()
            log_action(session.get("user_id"), "create", "medplan", plan.id, plan.name)
            db.session.commit()
            flash("用藥計畫已新增", "ok")
        return redirect(url_for("admin.medplans"))
    plans = MedPlan.query.order_by(MedPlan.elder_id, MedPlan.timeslot).all()
    return render_template(
        "admin/medplans.html", **_ctx(plans=plans, elders=elders_all, slots=TIMESLOTS)
    )


@bp.route("/medplans/<int:pid>/toggle", methods=["POST"])
@login_required("admin")
def medplan_toggle(pid):
    plan = db.session.get(MedPlan, pid)
    if plan:
        plan.active = not plan.active
        log_action(
            session.get("user_id"),
            "update",
            "medplan",
            plan.id,
            f"active={plan.active}",
        )
        db.session.commit()
    return redirect(url_for("admin.medplans"))


# ---------------- users ----------------


@bp.route("/users", methods=["GET", "POST"])
@login_required("admin")
def users():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        name = (request.form.get("name") or "").strip()
        role = request.form.get("role")
        language = normalize_lang(request.form.get("lang"))
        if (
            username
            and name
            and role in ("admin", "family", "worker")
            and not User.query.filter_by(username=username).first()
        ):
            user = User(username=username, name=name, role=role, lang=language)
            if role == "worker":
                user.pin = (request.form.get("pin") or "").strip() or "1234"
            else:
                user.set_password(request.form.get("password") or "care1234")
            db.session.add(user)
            db.session.flush()
            log_action(
                session.get("user_id"),
                "create",
                "user",
                user.id,
                f"{user.username} / {user.role}",
            )
            db.session.commit()
            flash(f"使用者「{name}」已建立", "ok")
        else:
            flash("建立失敗：帳號重複或欄位不完整", "error")
        return redirect(url_for("admin.users"))
    return render_template(
        "admin/users.html", **_ctx(users=User.query.order_by(User.role, User.id).all())
    )


@bp.route("/users/<int:uid>/edit", methods=["POST"])
@login_required("admin")
def user_edit(uid):
    user = db.session.get(User, uid)
    me = current_user()
    if user:
        old_name = user.name
        user.name = (request.form.get("name") or user.name).strip()
        user.lang = normalize_lang(request.form.get("lang") or user.lang)
        if not (user.id == me.id and request.form.get("active") != "on"):
            user.active = request.form.get("active") == "on"
        pin = (request.form.get("pin") or "").strip()
        if user.role == "worker" and pin:
            user.pin = pin
        password = request.form.get("password") or ""
        if user.role in ("admin", "family") and password:
            user.set_password(password)
        log_action(
            session.get("user_id"),
            "update",
            "user",
            user.id,
            f"{old_name} -> {user.name}; lang={user.lang}; active={user.active}",
        )
        db.session.commit()
        flash("使用者已更新", "ok")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:uid>/delete", methods=["POST"])
@login_required("admin")
def user_delete(uid):
    """Delete a login account while retaining care records for historical reporting."""
    target = db.session.get(User, uid)
    me = current_user()
    if target is None:
        flash("找不到要刪除的使用者", "error")
        return redirect(url_for("admin.users"))
    if target.id == me.id:
        flash("不能刪除目前登入中的管理者帳號", "error")
        return redirect(url_for("admin.users"))
    if target.role == "admin" and target.active:
        active_admins = User.query.filter_by(role="admin", active=True).count()
        if active_admins <= 1:
            flash("系統至少必須保留一位啟用中的管理者", "error")
            return redirect(url_for("admin.users"))

    label = f"{target.name}（{target.username}）"

    try:
        # Historical care data must remain. Remove only the foreign-key attribution
        # to the deleted login account, then keep a separate deletion audit entry.
        for model in (MealRecord, MedRecord, VitalRecord, WaterRecord, BowelRecord):
            db.session.query(model).filter(model.created_by == target.id).update(
                {model.created_by: None}, synchronize_session=False
            )
        db.session.query(AuditLog).filter(AuditLog.user_id == target.id).update(
            {AuditLog.user_id: None}, synchronize_session=False
        )

        log_action(me.id, "delete", "user", target.id, label)
        db.session.delete(target)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash("刪除帳號失敗，資料庫未做任何變更", "error")
        return redirect(url_for("admin.users"))

    flash(f"使用者帳號「{label}」已刪除；既有照顧紀錄仍予保留", "ok")
    return redirect(url_for("admin.users"))


# ---------------- notification settings ----------------


@bp.route("/notify", methods=["GET", "POST"])
@login_required("admin")
def notify():
    if request.method == "POST":
        form = request.form
        set_setting("smtp_user", (form.get("smtp_user") or "").strip())
        password = (form.get("smtp_password") or "").strip()
        if password:
            set_setting("smtp_password", password)
        set_setting("recipients", (form.get("recipients") or "").strip())
        set_setting(
            "report_items",
            {
                key: form.get(f"item_{key}") == "on"
                for key in ("meals", "meds", "vitals", "water", "bowel")
            },
        )
        set_setting(
            "report_daily",
            {"enabled": form.get("daily_on") == "on", "time": form.get("daily_time") or "21:00"},
        )
        set_setting(
            "report_weekly",
            {
                "enabled": form.get("weekly_on") == "on",
                "weekday": int(form.get("weekly_day") or 6),
                "time": form.get("weekly_time") or "20:00",
            },
        )
        set_setting(
            "report_monthly",
            {
                "enabled": form.get("monthly_on") == "on",
                "day": int(form.get("monthly_day") or 1),
                "time": form.get("monthly_time") or "09:00",
            },
        )
        set_setting(
            "thresholds",
            {
                "enabled": form.get("th_on") == "on",
                "sys_hi": form.get("sys_hi", type=int) or 160,
                "sys_lo": form.get("sys_lo", type=int) or 90,
                "dia_hi": form.get("dia_hi", type=int) or 100,
                "dia_lo": form.get("dia_lo", type=int) or 55,
                "pulse_hi": form.get("pulse_hi", type=int) or 110,
                "pulse_lo": form.get("pulse_lo", type=int) or 45,
                "spo2_lo": form.get("spo2_lo", type=int) or 92,
            },
        )
        set_setting(
            "reminders",
            {
                "enabled": form.get("rem_on") == "on",
                "morning": form.get("rem_morning") or "09:30",
                "noon": form.get("rem_noon") or "13:30",
                "evening": form.get("rem_evening") or "19:30",
                "bedtime": form.get("rem_bedtime") or "22:30",
            },
        )
        set_setting("pdf_attach", form.get("pdf_attach") == "on")
        flash("通知設定已儲存", "ok")
        return redirect(url_for("admin.notify"))

    settings = {
        key: get_setting(key)
        for key in (
            "smtp_user",
            "recipients",
            "report_items",
            "report_daily",
            "report_weekly",
            "report_monthly",
            "thresholds",
            "reminders",
            "pdf_attach",
        )
    }
    settings["smtp_password_set"] = bool(get_setting("smtp_password"))
    return render_template("admin/notify.html", **_ctx(s=settings))


@bp.route("/send-now/<period>", methods=["POST"])
@login_required("admin")
def send_now(period):
    if period not in ("daily", "weekly", "monthly"):
        return redirect(url_for("admin.notify"))
    try:
        subject, html, pdf = build_report(period)
        send_mail(subject, html, pdf)
        log_action(session.get("user_id"), "create", "report", 0, f"manual {period}")
        db.session.commit()
        flash(f"報表已寄出：{subject}", "ok")
    except MailNotConfigured as exc:
        flash(f"無法寄送：{exc}", "error")
    except Exception as exc:
        flash(f"寄送失敗：{exc}", "error")
    return redirect(url_for("admin.notify"))


# ---------------- audit log ----------------


@bp.route("/audit")
@login_required("admin")
def audit():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()
    type_zh = {
        "meal": "餐飲",
        "med": "用藥",
        "vital": "健康數據",
        "water": "喝水",
        "bowel": "排便",
        "photo": "照片",
        "report": "報表",
        "user": "使用者",
        "elder": "長輩",
        "medplan": "用藥計畫",
    }
    act_zh = {"create": "新增", "update": "修改", "delete": "刪除"}
    return render_template(
        "admin/audit.html", **_ctx(logs=logs, type_zh=type_zh, act_zh=act_zh)
    )
