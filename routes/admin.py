from __future__ import annotations

from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError

from models import (
    ABNORMAL_SEVERITIES,
    ABNORMAL_STATUSES,
    BLOOD_TYPE_VALUES,
    GENDER_VALUES,
    RH_FACTOR_VALUES,
    AuditLog,
    AbnormalEvent,
    BowelRecord,
    Elder,
    MealRecord,
    MedPlan,
    MedRecord,
    Photo,
    TIMESLOTS,
    User,
    VitalRecord,
    WaterRecord,
    db,
    get_care_parameters,
    get_elder_parameters,
    get_setting,
    log_action,
    set_elder_setting,
    set_setting,
)
from services.abnormal import (
    CATEGORY_LABELS,
    EVENT_TYPE_LABELS,
    SEVERITY_LABELS,
    STATUS_LABELS,
)
from services.mailer import (
    MailConfigurationError,
    MailNotConfigured,
    normalize_recipients,
    normalize_smtp_password,
    normalize_smtp_username,
    send_mail,
)
from services.media import (
    active_photos_query,
    photos_for,
    save_images,
    set_primary_med_photo,
    soft_delete_photo,
)
from services.query_filters import pagination_args, query_args_without, request_date_range
from services.reports import build_report
from translations import LANGUAGES, normalize_lang
from utils import current_user, login_required


bp = Blueprint("admin", __name__, url_prefix="/admin")

SLOT_ZH = {"morning": "早上", "noon": "中午", "evening": "晚上", "bedtime": "睡前"}
REL_ZH = {"before": "餐前", "after": "飯後", "none": "—"}
ROLE_ZH = {"admin": "管理者", "family": "家屬", "worker": "照顧者", "system": "系統"}
TYPE_ZH = {
    "meal": "餐飲",
    "med": "用藥",
    "med_submission": "用藥填報",
    "vital": "健康數據",
    "water": "喝水",
    "water_daily": "每日飲水",
    "bowel": "排便",
    "photo": "照片",
    "report": "報表",
    "user": "使用者",
    "elder": "長輩",
    "medplan": "用藥計畫",
    "parameter": "參數設定",
    "notify": "通知設定",
    "abnormal": "異常事件",
    "auth": "登入／登出",
}
ACT_ZH = {
    "create": "新增",
    "update": "修改",
    "delete": "刪除",
    "login": "登入",
    "logout": "登出",
    "send": "寄送",
}
PHOTO_KIND_ZH = {
    "care_evidence": "照顧填報佐證",
    "med_reference": "藥物參考",
    "abnormal_followup": "異常後續",
}
GENDER_ZH = {
    "unspecified": "未設定",
    "female": "女",
    "male": "男",
    "other": "其他／多元性別",
}
RH_FACTOR_ZH = {"unknown": "未知", "positive": "Rh+", "negative": "Rh−"}
SYSTEM_ADMIN_USERNAME = "admin"


def _is_system_admin(account: User | None) -> bool:
    """Only the built-in account named ``admin`` is undeletable."""

    return bool(
        account
        and account.username
        and account.username.casefold() == SYSTEM_ADMIN_USERNAME
    )


def _parse_pin(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    if not value.isdigit() or not 4 <= len(value) <= 16:
        raise ValueError("PIN 必須為 4 至 16 位數字")
    return value


def _username_exists(username: str, *, excluding_id: int | None = None) -> bool:
    query = User.query.filter(func.lower(User.username) == username.casefold())
    if excluding_id is not None:
        query = query.filter(User.id != excluding_id)
    return query.first() is not None


def _ctx(**kwargs):
    base = {
        "user": current_user(),
        "SLOT_ZH": SLOT_ZH,
        "REL_ZH": REL_ZH,
        "ROLE_ZH": ROLE_ZH,
        "TYPE_ZH": TYPE_ZH,
        "ACT_ZH": ACT_ZH,
        "LANGUAGES": LANGUAGES,
        "CATEGORY_LABELS": CATEGORY_LABELS,
        "EVENT_TYPE_LABELS": EVENT_TYPE_LABELS,
        "STATUS_LABELS": STATUS_LABELS,
        "SEVERITY_LABELS": SEVERITY_LABELS,
        "PHOTO_KIND_ZH": PHOTO_KIND_ZH,
        "GENDER_ZH": GENDER_ZH,
        "RH_FACTOR_ZH": RH_FACTOR_ZH,
        "BLOOD_TYPE_VALUES": BLOOD_TYPE_VALUES,
    }
    base.update(kwargs)
    return base


def _flash_media_result(result):
    if result.saved_count:
        flash(f"已儲存 {result.saved_count} 張圖片", "ok")
    for error in result.errors:
        flash(error, "warn")


def _parse_birthday(raw: str | None, fallback: date) -> date:
    try:
        return datetime.strptime(raw or "", "%Y-%m-%d").date()
    except ValueError:
        return fallback


def _bounded_int(name, default, minimum, maximum):
    value = request.form.get(name, type=int)
    if value is None:
        return default
    return max(minimum, min(value, maximum))


def _valid_hhmm(value: str | None, default: str) -> str:
    try:
        datetime.strptime(value or "", "%H:%M")
    except (TypeError, ValueError):
        return default
    return value


def _text_value(name: str, max_length: int) -> str:
    return (request.form.get(name) or "").strip()[:max_length]


def _optional_float(name: str, minimum: float, maximum: float) -> float | None:
    raw = (request.form.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必須是數字") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} 必須介於 {minimum:g} 與 {maximum:g} 之間")
    return round(value, 1)


def _optional_int(name: str, minimum: int, maximum: int) -> int | None:
    raw = (request.form.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必須是整數") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} 必須介於 {minimum} 與 {maximum} 之間")
    return value


def _elder_profile_from_form() -> dict[str, object]:
    gender = request.form.get("gender") or "unspecified"
    blood_type = request.form.get("blood_type") or "unknown"
    rh_factor = request.form.get("rh_factor") or "unknown"
    if gender not in GENDER_VALUES:
        gender = "unspecified"
    if blood_type not in BLOOD_TYPE_VALUES:
        blood_type = "unknown"
    if rh_factor not in RH_FACTOR_VALUES:
        rh_factor = "unknown"
    return {
        "gender": gender,
        "blood_type": blood_type,
        "rh_factor": rh_factor,
        "height_cm": _optional_float("height_cm", 50, 250),
        "phone": _text_value("phone", 32),
        "address": _text_value("address", 256),
        "allergies": _text_value("allergies", 2000),
        "chronic_conditions": _text_value("chronic_conditions", 2000),
        "primary_hospital": _text_value("primary_hospital", 128),
        "primary_physician": _text_value("primary_physician", 64),
        "emergency_contact_name": _text_value("emergency_contact_name", 64),
        "emergency_contact_relation": _text_value("emergency_contact_relation", 32),
        "emergency_contact_phone": _text_value("emergency_contact_phone", 32),
    }


def _elder_snapshot(elder: Elder) -> dict[str, object]:
    return {
        "name": elder.name,
        "birthday": elder.birthday.isoformat() if elder.birthday else None,
        "gender": elder.gender,
        "blood_type": elder.blood_type,
        "rh_factor": elder.rh_factor,
        "height_cm": elder.height_cm,
        "phone": elder.phone,
        "address": elder.address,
        "allergies": elder.allergies,
        "chronic_conditions": elder.chronic_conditions,
        "primary_hospital": elder.primary_hospital,
        "primary_physician": elder.primary_physician,
        "emergency_contact_name": elder.emergency_contact_name,
        "emergency_contact_relation": elder.emergency_contact_relation,
        "emergency_contact_phone": elder.emergency_contact_phone,
        "notes": elder.notes,
        "water_goal": elder.water_goal,
        "active": elder.active,
    }


@bp.route("/")
@login_required("admin")
def index():
    return render_template(
        "admin/index.html",
        **_ctx(
            elder_count=Elder.query.filter_by(active=True).count(),
            user_count=User.query.filter(
                User.active.is_(True), User.deleted_at.is_(None)
            ).count(),
            plan_count=MedPlan.query.filter_by(active=True).count(),
            pending_count=AbnormalEvent.query.filter(
                AbnormalEvent.status.in_(("pending", "tracking"))
            ).count(),
        ),
    )


# ---------------- elders ----------------


@bp.route("/elders", methods=["GET", "POST"])
@login_required("admin")
def elders():
    params = get_care_parameters()
    default_birthday = _parse_birthday(
        params.get("default_elder_birthday"), date(1940, 1, 1)
    )
    default_water_goal = int(params.get("default_water_goal_ml", 1500))
    if request.method == "POST":
        name = _text_value("name", 64)
        if not name:
            flash("請輸入長輩姓名", "error")
            return redirect(url_for("admin.elders"))
        try:
            profile = _elder_profile_from_form()
        except ValueError as exc:
            flash(f"長輩資料格式錯誤：{exc}", "error")
            return redirect(url_for("admin.elders"))
        birthday = _parse_birthday(request.form.get("birthday"), default_birthday)
        water_goal = request.form.get("water_goal", type=int)
        if water_goal is None:
            water_goal = default_water_goal
        elder = Elder(
            name=name,
            birthday=birthday,
            notes=_text_value("notes", 4000),
            water_goal=max(0, min(water_goal, 10000)),
            **profile,
        )
        db.session.add(elder)
        db.session.flush()
        log_action(
            session.get("user_id"),
            "create",
            "elder",
            elder.id,
            elder.name,
            elder_id=elder.id,
            event_code="elder.create",
            metadata={"after": _elder_snapshot(elder)},
        )
        db.session.commit()
        flash("長輩資料已新增", "ok")
        return redirect(url_for("admin.elders"))

    return render_template(
        "admin/elders.html",
        **_ctx(
            elders=Elder.query.order_by(Elder.id).all(),
            default_birthday=default_birthday,
            default_water_goal=default_water_goal,
        ),
    )


@bp.route("/elders/<int:eid>/edit", methods=["POST"])
@login_required("admin")
def elder_edit(eid):
    elder = db.session.get(Elder, eid)
    if elder is None:
        flash("找不到長輩資料", "error")
        return redirect(url_for("admin.elders"))

    name = _text_value("name", 64)
    if not name:
        flash("長輩姓名不可空白", "error")
        return redirect(url_for("admin.elders"))
    try:
        profile = _elder_profile_from_form()
    except ValueError as exc:
        flash(f"長輩資料格式錯誤：{exc}", "error")
        return redirect(url_for("admin.elders"))

    before = _elder_snapshot(elder)
    elder.name = name
    elder.birthday = _parse_birthday(
        request.form.get("birthday"), elder.birthday or date(1940, 1, 1)
    )
    elder.notes = _text_value("notes", 4000)
    water_goal = request.form.get("water_goal", type=int)
    if water_goal is not None:
        elder.water_goal = max(0, min(water_goal, 10000))
    elder.active = request.form.get("active") == "on"
    for key, value in profile.items():
        setattr(elder, key, value)
    after = _elder_snapshot(elder)
    log_action(
        session.get("user_id"),
        "update",
        "elder",
        elder.id,
        f"{before['name']} -> {after['name']}; active={elder.active}",
        elder_id=elder.id,
        event_code="elder.update",
        metadata={"before": before, "after": after},
    )
    db.session.commit()
    flash("長輩資料已更新", "ok")
    return redirect(url_for("admin.elders"))


# ---------------- medication plans ----------------


def _med_upload_files():
    return request.files.getlist("photo_camera") + request.files.getlist("photo_upload")


@bp.route("/medplans", methods=["GET", "POST"])
@login_required("admin")
def medplans():
    elders_all = Elder.query.filter_by(active=True).order_by(Elder.id).all()
    params = get_care_parameters()
    max_photos = int(params.get("max_medication_photos_per_plan", 3))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        elder_id = request.form.get("elder_id", type=int)
        slot = request.form.get("timeslot")
        relation = request.form.get("meal_relation") or "none"
        if slot == "bedtime":
            relation = "none"
        elder = Elder.query.filter_by(id=elder_id, active=True).first() if elder_id else None
        if not (
            name
            and elder
            and slot in TIMESLOTS
            and relation in ("before", "after", "none")
        ):
            flash("用藥項目欄位不完整", "error")
            return redirect(url_for("admin.medplans"))

        plan = MedPlan(
            elder_id=elder.id,
            name=name,
            timeslot=slot,
            meal_relation=relation,
            dose_note=(request.form.get("dose_note") or "").strip(),
        )
        db.session.add(plan)
        db.session.flush()
        log_action(
            session.get("user_id"),
            "create",
            "medplan",
            plan.id,
            plan.name,
            elder_id=elder.id,
            event_code="medplan.create",
            metadata={
                "timeslot": slot,
                "meal_relation": relation,
                "dose_note": plan.dose_note,
            },
        )
        result = save_images(
            _med_upload_files(),
            kind="med_reference",
            record_type="medplan",
            record_id=plan.id,
            elder_id=elder.id,
            record_date=date.today(),
            uploaded_by=session.get("user_id"),
            limit=max_photos,
        )
        db.session.commit()
        flash("用藥計畫已新增", "ok")
        _flash_media_result(result)
        return redirect(url_for("admin.medplans"))

    plans = MedPlan.query.order_by(MedPlan.elder_id, MedPlan.timeslot, MedPlan.id).all()
    plan_photos = {
        plan.id: photos_for("medplan", plan.id, kind="med_reference") for plan in plans
    }
    return render_template(
        "admin/medplans.html",
        **_ctx(
            plans=plans,
            elders=elders_all,
            slots=TIMESLOTS,
            plan_photos=plan_photos,
            max_photos=max_photos,
        ),
    )


@bp.route("/medplans/<int:pid>/edit", methods=["POST"])
@login_required("admin")
def medplan_edit(pid):
    plan = db.session.get(MedPlan, pid)
    if plan is None:
        flash("找不到用藥計畫", "error")
        return redirect(url_for("admin.medplans"))

    slot = request.form.get("timeslot") or plan.timeslot
    relation = request.form.get("meal_relation") or plan.meal_relation
    if slot == "bedtime":
        relation = "none"
    if slot not in TIMESLOTS or relation not in ("before", "after", "none"):
        flash("時段或餐前／飯後設定錯誤", "error")
        return redirect(url_for("admin.medplans"))

    before = {
        "name": plan.name,
        "timeslot": plan.timeslot,
        "meal_relation": plan.meal_relation,
        "dose_note": plan.dose_note,
        "active": plan.active,
    }
    plan.name = (request.form.get("name") or plan.name).strip()
    plan.timeslot = slot
    plan.meal_relation = relation
    plan.dose_note = (request.form.get("dose_note") or "").strip()
    plan.active = request.form.get("active") == "on"
    after = {
        "name": plan.name,
        "timeslot": plan.timeslot,
        "meal_relation": plan.meal_relation,
        "dose_note": plan.dose_note,
        "active": plan.active,
    }
    log_action(
        session.get("user_id"),
        "update",
        "medplan",
        plan.id,
        f"{before['name']} -> {after['name']}; active={plan.active}",
        elder_id=plan.elder_id,
        event_code="medplan.update",
        metadata={"before": before, "after": after},
    )

    existing = photos_for("medplan", plan.id, kind="med_reference")
    max_photos = int(get_care_parameters().get("max_medication_photos_per_plan", 3))
    result = save_images(
        _med_upload_files(),
        kind="med_reference",
        record_type="medplan",
        record_id=plan.id,
        elder_id=plan.elder_id,
        record_date=date.today(),
        uploaded_by=session.get("user_id"),
        limit=max(0, max_photos - len(existing)),
        start_order=len(existing),
    )
    db.session.commit()
    flash("用藥計畫已更新", "ok")
    _flash_media_result(result)
    return redirect(url_for("admin.medplans"))


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
            elder_id=plan.elder_id,
            event_code="medplan.toggle",
        )
        db.session.commit()
    return redirect(url_for("admin.medplans"))


@bp.route("/photos/<int:photo_id>/primary", methods=["POST"])
@login_required("admin")
def photo_primary(photo_id):
    photo = db.session.get(Photo, photo_id)
    if photo and photo.deleted_at is None:
        try:
            set_primary_med_photo(photo, user_id=session.get("user_id"))
            db.session.commit()
            flash("已指定主要藥物圖片", "ok")
        except ValueError:
            flash("此圖片不能設為藥物主圖", "error")
    return redirect(request.referrer or url_for("admin.medplans"))


@bp.route("/photos/<int:photo_id>/delete", methods=["POST"])
@login_required("admin")
def photo_delete(photo_id):
    photo = db.session.get(Photo, photo_id)
    if photo and photo.deleted_at is None:
        was_primary = photo.is_primary
        record_type = photo.record_type
        record_id = photo.record_id
        kind = photo.kind
        soft_delete_photo(photo, user_id=session.get("user_id"))
        if was_primary and kind == "med_reference" and record_type == "medplan":
            remaining = photos_for("medplan", record_id, kind="med_reference")
            if remaining:
                remaining[0].is_primary = True
        db.session.commit()
        flash("圖片已刪除", "ok")
    return redirect(request.referrer or url_for("admin.photos"))


# ---------------- users ----------------


def _validate_user_credentials(*, role: str, existing: User | None = None):
    """Require both PIN and password for every active account.

    New accounts must submit both fields. When editing an account, a blank
    field means "keep the existing credential"; however, a legacy account that
    is missing either credential must supply the missing value before the edit
    can be saved. ``role`` is retained in the signature for clear call sites
    and future role-specific policies.
    """

    del role  # All roles currently share the same credential requirements.
    raw_pin = request.form.get("pin")
    raw_password = request.form.get("password") or ""
    try:
        submitted_pin = _parse_pin(raw_pin)
    except ValueError as exc:
        return None, None, str(exc)

    existing_pin = existing.pin if existing else None
    existing_password = existing.password_hash if existing else None
    has_pin = bool(submitted_pin or existing_pin)
    has_password = bool(raw_password or existing_password)

    if not has_pin:
        return None, None, "PIN 為必填欄位，請設定 4 至 16 位數字 PIN"
    if not has_password:
        return None, None, "登入密碼為必填欄位"
    return submitted_pin, raw_password, None


@bp.route("/users", methods=["GET", "POST"])
@login_required("admin")
def users():
    if request.method == "POST":
        username = _text_value("username", 64)
        name = _text_value("name", 64)
        role = request.form.get("role")
        language = normalize_lang(request.form.get("lang"))

        if not username or not name or role not in ("admin", "family", "worker"):
            flash("建立失敗：請完整填寫帳號、名稱與角色", "error")
            return redirect(url_for("admin.users"))
        if _username_exists(username):
            flash("建立失敗：帳號名稱已被使用", "error")
            return redirect(url_for("admin.users"))

        pin, password, credential_error = _validate_user_credentials(role=role)
        if credential_error:
            flash(credential_error, "error")
            return redirect(url_for("admin.users"))

        account = User(
            username=username,
            name=name,
            role=role,
            lang=language,
            pin=pin,
            active=True,
        )
        if password:
            account.set_password(password)

        try:
            db.session.add(account)
            db.session.flush()
            log_action(
                session.get("user_id"),
                "create",
                "user",
                account.id,
                f"{account.username} / {account.role}",
                event_code="user.create",
                metadata={
                    "username": account.username,
                    "role": account.role,
                    "pin_set": bool(account.pin),
                    "password_set": bool(account.password_hash),
                },
            )
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash("建立使用者失敗，請確認帳號沒有重複", "error")
            return redirect(url_for("admin.users"))

        flash(f"使用者「{name}」已建立", "ok")
        return redirect(url_for("admin.users"))

    accounts = (
        User.query.filter(User.deleted_at.is_(None))
        .order_by(User.role, User.id)
        .all()
    )
    return render_template("admin/users.html", **_ctx(users=accounts))


@bp.route("/users/<int:uid>/edit", methods=["POST"])
@login_required("admin")
def user_edit(uid):
    account = db.session.get(User, uid)
    me = current_user()
    if account is None or account.deleted_at is not None:
        flash("找不到要編輯的使用者", "error")
        return redirect(url_for("admin.users"))

    system_admin = _is_system_admin(account)
    before = {
        "username": account.username,
        "name": account.name,
        "role": account.role,
        "lang": account.lang,
        "active": account.active,
        "pin_set": bool(account.pin),
        "password_set": bool(account.password_hash),
    }

    requested_name = _text_value("name", 64)
    if not requested_name:
        flash("顯示名稱不可空白", "error")
        return redirect(url_for("admin.users"))

    requested_username = account.username if system_admin else _text_value("username", 64)
    if not requested_username:
        flash("帳號不可空白", "error")
        return redirect(url_for("admin.users"))
    if _username_exists(requested_username, excluding_id=account.id):
        flash("帳號名稱已被其他使用者使用", "error")
        return redirect(url_for("admin.users"))

    # Only the built-in account named ``admin`` has an immutable role. Every
    # other account, including administrators created later, can be assigned
    # any supported role.
    if system_admin:
        requested_role = "admin"
    else:
        requested_role = request.form.get("role")
        if requested_role not in ("admin", "family", "worker"):
            flash("請指定有效的管理者、家屬或照顧者角色", "error")
            return redirect(url_for("admin.users"))

    pin, password, credential_error = _validate_user_credentials(
        role=requested_role, existing=account
    )
    if credential_error:
        flash(credential_error, "error")
        return redirect(url_for("admin.users"))

    requested_active = request.form.get("active") == "on"
    if system_admin or account.id == me.id:
        requested_active = True
    elif account.role == "admin" and account.active and not requested_active:
        other_active_admins = User.query.filter(
            User.role == "admin",
            User.active.is_(True),
            User.deleted_at.is_(None),
            User.id != account.id,
        ).count()
        if other_active_admins < 1:
            flash("系統至少必須保留一位啟用中的管理者", "error")
            return redirect(url_for("admin.users"))

    account.username = requested_username
    account.name = requested_name
    account.role = requested_role
    account.lang = normalize_lang(request.form.get("lang") or account.lang)
    account.active = requested_active
    if pin is not None:
        account.pin = pin
    if password:
        account.set_password(password)

    after = {
        "username": account.username,
        "name": account.name,
        "role": account.role,
        "lang": account.lang,
        "active": account.active,
        "pin_set": bool(account.pin),
        "password_set": bool(account.password_hash),
        "pin_changed": pin is not None,
        "password_changed": bool(password),
    }
    log_action(
        session.get("user_id"),
        "update",
        "user",
        account.id,
        f"{before['username']} -> {after['username']}; {before['role']} -> {after['role']}",
        event_code="user.update",
        metadata={"before": before, "after": after},
    )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash("使用者更新失敗，請確認帳號沒有重複", "error")
        return redirect(url_for("admin.users"))

    flash("使用者已更新", "ok")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:uid>/delete", methods=["POST"])
@login_required("admin")
def user_delete(uid):
    """Soft-delete any account except the built-in ``admin`` or oneself."""

    target = db.session.get(User, uid)
    me = current_user()
    if target is None or target.deleted_at is not None:
        flash("找不到要刪除的使用者", "error")
        return redirect(url_for("admin.users"))
    if _is_system_admin(target):
        flash("系統內建 admin 帳號受保護，不能刪除", "error")
        return redirect(url_for("admin.users"))
    if target.id == me.id:
        flash("不能刪除目前登入中的帳號", "error")
        return redirect(url_for("admin.users"))
    if target.role == "admin" and target.active:
        other_active_admins = User.query.filter(
            User.role == "admin",
            User.active.is_(True),
            User.deleted_at.is_(None),
            User.id != target.id,
        ).count()
        if other_active_admins < 1:
            flash("系統至少必須保留一位啟用中的管理者", "error")
            return redirect(url_for("admin.users"))

    label = f"{target.name}（{target.username}）"
    try:
        log_action(
            me.id,
            "delete",
            "user",
            target.id,
            label,
            event_code="user.soft_delete",
            metadata={
                "target_username": target.username,
                "target_name": target.name,
                "target_role": target.role,
            },
        )
        target.active = False
        target.deleted_at = datetime.now()
        target.password_hash = None
        target.pin = None
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash("刪除帳號失敗，資料庫未做任何變更", "error")
        return redirect(url_for("admin.users"))

    flash(f"使用者帳號「{label}」已停用刪除；歷史身分與照顧紀錄仍予保留", "ok")
    return redirect(url_for("admin.users"))


# ---------------- parameters ----------------


@bp.route("/parameters", methods=["GET", "POST"])
@login_required("admin")
def parameters():
    current = get_care_parameters()
    if request.method == "POST":
        quick_values = []
        for key in ("water_quick_1", "water_quick_2", "water_quick_3"):
            value = request.form.get(key, type=int)
            if value is not None:
                quick_values.append(value)
        minimum = _bounded_int("water_entry_min_ml", 10, 1, 5000)
        maximum = _bounded_int("water_entry_max_ml", 2000, minimum, 10000)
        if len(quick_values) != 3 or any(
            value < minimum or value > maximum for value in quick_values
        ):
            flash("三個喝水快捷值都必須介於單次最小值與最大值之間", "error")
            return redirect(url_for("admin.parameters"))
        if len(set(quick_values)) != len(quick_values):
            flash("喝水快捷值不可重複", "error")
            return redirect(url_for("admin.parameters"))

        birthday = _parse_birthday(
            request.form.get("default_elder_birthday"), date(1940, 1, 1)
        )
        bowel_types = sorted(
            {
                int(value)
                for value in request.form.getlist("bowel_types")
                if value.isdigit() and 1 <= int(value) <= 7
            }
        )
        sys_hi = _bounded_int("sys_hi", 160, 50, 300)
        sys_lo = _bounded_int("sys_lo", 90, 30, 250)
        dia_hi = _bounded_int("dia_hi", 100, 30, 200)
        dia_lo = _bounded_int("dia_lo", 55, 20, 180)
        pulse_hi = _bounded_int("pulse_hi", 110, 30, 250)
        pulse_lo = _bounded_int("pulse_lo", 45, 20, 220)
        if sys_lo >= sys_hi or dia_lo >= dia_hi or pulse_lo >= pulse_hi:
            flash("生命徵象的下限必須小於上限", "error")
            return redirect(url_for("admin.parameters"))

        rules = {
            "vitals_enabled": request.form.get("vitals_enabled") == "on",
            "sys_hi": sys_hi,
            "sys_lo": sys_lo,
            "dia_hi": dia_hi,
            "dia_lo": dia_lo,
            "pulse_hi": pulse_hi,
            "pulse_lo": pulse_lo,
            "spo2_lo": _bounded_int("spo2_lo", 92, 50, 100),
            "med_not_given_enabled": request.form.get("med_not_given_enabled") == "on",
            "bowel_enabled": request.form.get("bowel_enabled") == "on",
            "bowel_types": bowel_types or [1, 2, 6, 7],
            "meal_none_enabled": request.form.get("meal_none_enabled") == "on",
            "meal_little_enabled": request.form.get("meal_little_enabled") == "on",
            "water_low_enabled": request.form.get("water_low_enabled") == "on",
            "water_close_time": _valid_hhmm(request.form.get("water_close_time"), "22:00"),
            "water_min_percent": _bounded_int("water_min_percent", 100, 1, 200),
        }
        updated = {
            "version": 1,
            "water_quick_amounts_ml": quick_values,
            "default_elder_birthday": birthday.isoformat(),
            "default_water_goal_ml": _bounded_int(
                "default_water_goal_ml", 1500, 0, 10000
            ),
            "water_entry_min_ml": minimum,
            "water_entry_max_ml": maximum,
            "dashboard_default_days": _bounded_int(
                "dashboard_default_days", 30, 1, 180
            ),
            "max_care_photos_per_record": _bounded_int(
                "max_care_photos_per_record", 5, 1, 20
            ),
            "max_medication_photos_per_plan": _bounded_int(
                "max_medication_photos_per_plan", 3, 1, 10
            ),
            "abnormal_rules": rules,
        }
        set_setting("care_parameters", updated, commit=False)
        # Keep the old threshold key synchronised for older integrations.
        set_setting(
            "thresholds",
            {
                "enabled": rules["vitals_enabled"],
                **{
                    key: rules[key]
                    for key in (
                        "sys_hi",
                        "sys_lo",
                        "dia_hi",
                        "dia_lo",
                        "pulse_hi",
                        "pulse_lo",
                        "spo2_lo",
                    )
                },
            },
            commit=False,
        )
        log_action(
            session.get("user_id"),
            "update",
            "parameter",
            0,
            "系統參數已更新",
            event_code="parameters.update",
            metadata={"before": current, "after": updated},
        )
        db.session.commit()
        flash("參數設定已儲存；新設定會立即套用", "ok")
        return redirect(url_for("admin.parameters"))

    elders_all = Elder.query.order_by(Elder.active.desc(), Elder.name).all()
    elder_parameters = {
        elder.id: get_elder_parameters(elder.id) for elder in elders_all
    }
    return render_template(
        "admin/parameters.html",
        **_ctx(p=current, elders=elders_all, elder_parameters=elder_parameters),
    )


@bp.route("/parameters/elder/<int:eid>", methods=["POST"])
@login_required("admin")
def elder_parameters_update(eid):
    elder = db.session.get(Elder, eid)
    if elder is None:
        flash("找不到被照顧者", "error")
        return redirect(url_for("admin.parameters"))
    try:
        defaults = {
            "weight": _optional_float("default_weight", 20, 300),
            "systolic": _optional_int("default_systolic", 50, 260),
            "diastolic": _optional_int("default_diastolic", 30, 180),
            "pulse": _optional_int("default_pulse", 30, 220),
            "spo2": _optional_int("default_spo2", 50, 100),
        }
    except ValueError as exc:
        flash(f"健康數據預設值格式錯誤：{exc}", "error")
        return redirect(url_for("admin.parameters", elder=eid))

    before = get_elder_parameters(elder.id)
    updated = {"version": 1, "vital_defaults": defaults}
    set_elder_setting(elder.id, "care_parameters", updated, commit=False)
    log_action(
        session.get("user_id"),
        "update",
        "parameter",
        elder.id,
        f"更新 {elder.name} 的健康數據預設值",
        elder_id=elder.id,
        event_code="parameters.elder_vital_defaults_update",
        metadata={"before": before, "after": updated},
    )
    db.session.commit()
    flash(f"已儲存「{elder.name}」的健康數據預設值", "ok")
    return redirect(url_for("admin.parameters", elder=eid))


# ---------------- notification settings ----------------


@bp.route("/notify", methods=["GET", "POST"])
@login_required("admin")
def notify():
    if request.method == "POST":
        form = request.form
        before = {
            key: get_setting(key)
            for key in (
                "smtp_user",
                "recipients",
                "report_items",
                "report_daily",
                "report_weekly",
                "report_monthly",
                "reminders",
                "pdf_attach",
            )
        }
        try:
            smtp_user = normalize_smtp_username(form.get("smtp_user") or "")
            password = normalize_smtp_password(form.get("smtp_password") or "")
            recipients = normalize_recipients(form.get("recipients") or "")
        except MailConfigurationError as exc:
            flash(f"郵件設定格式錯誤：{exc}", "error")
            return redirect(url_for("admin.notify"))

        set_setting("smtp_user", smtp_user, commit=False)
        if password:
            set_setting("smtp_password", password, commit=False)
        set_setting("recipients", ", ".join(recipients), commit=False)
        set_setting(
            "report_items",
            {
                key: form.get(f"item_{key}") == "on"
                for key in ("meals", "meds", "vitals", "water", "bowel")
            },
            commit=False,
        )
        set_setting(
            "report_daily",
            {
                "enabled": form.get("daily_on") == "on",
                "time": form.get("daily_time") or "21:00",
            },
            commit=False,
        )
        set_setting(
            "report_weekly",
            {
                "enabled": form.get("weekly_on") == "on",
                "weekday": int(form.get("weekly_day") or 6),
                "time": form.get("weekly_time") or "20:00",
            },
            commit=False,
        )
        set_setting(
            "report_monthly",
            {
                "enabled": form.get("monthly_on") == "on",
                "day": int(form.get("monthly_day") or 1),
                "time": form.get("monthly_time") or "09:00",
            },
            commit=False,
        )
        set_setting(
            "reminders",
            {
                "enabled": form.get("rem_on") == "on",
                "morning_enabled": form.get("rem_morning_on") == "on",
                "morning": _valid_hhmm(form.get("rem_morning"), "09:30"),
                "noon_enabled": form.get("rem_noon_on") == "on",
                "noon": _valid_hhmm(form.get("rem_noon"), "13:30"),
                "evening_enabled": form.get("rem_evening_on") == "on",
                "evening": _valid_hhmm(form.get("rem_evening"), "19:30"),
                "bedtime_enabled": form.get("rem_bedtime_on") == "on",
                "bedtime": _valid_hhmm(form.get("rem_bedtime"), "22:30"),
            },
            commit=False,
        )
        set_setting("pdf_attach", form.get("pdf_attach") == "on", commit=False)
        after = {
            key: get_setting(key)
            for key in (
                "smtp_user",
                "recipients",
                "report_items",
                "report_daily",
                "report_weekly",
                "report_monthly",
                "reminders",
                "pdf_attach",
            )
        }
        log_action(
            session.get("user_id"),
            "update",
            "notify",
            0,
            "通知與報表設定已更新",
            event_code="notify.update",
            metadata={"before": before, "after": after},
        )
        db.session.commit()
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
        log_action(
            session.get("user_id"),
            "send",
            "report",
            0,
            f"manual {period}",
            event_code="report.send_manual",
        )
        db.session.commit()
        flash(f"報表已寄出：{subject}", "ok")
    except MailNotConfigured as exc:
        flash(f"無法寄送：{exc}", "error")
    except MailConfigurationError as exc:
        flash(f"郵件設定錯誤：{exc}", "error")
    except Exception as exc:
        flash(f"寄送失敗：{exc}", "error")
    return redirect(url_for("admin.notify"))


# ---------------- audit log ----------------


@bp.route("/audit")
@login_required("admin")
def audit():
    query = AuditLog.query
    user_id = request.args.get("user", type=int)
    role = request.args.get("role")
    action = request.args.get("action")
    record_type = request.args.get("type")
    elder_id = request.args.get("elder", type=int)
    keyword = (request.args.get("q") or "").strip()
    date_range = request_date_range()

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if role in ROLE_ZH:
        query = query.filter(AuditLog.actor_role == role)
    if action:
        query = query.filter(AuditLog.action == action)
    if record_type:
        query = query.filter(AuditLog.record_type == record_type)
    if elder_id:
        query = query.filter(AuditLog.elder_id == elder_id)
    if date_range.start_datetime:
        query = query.filter(AuditLog.created_at >= date_range.start_datetime)
    if date_range.end_datetime:
        query = query.filter(AuditLog.created_at < date_range.end_datetime)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                AuditLog.actor_username.ilike(pattern),
                AuditLog.actor_name.ilike(pattern),
                AuditLog.detail.ilike(pattern),
                AuditLog.event_code.ilike(pattern),
                AuditLog.elder_name_snapshot.ilike(pattern),
            )
        )
    if request.args.get("sort") == "oldest":
        query = query.order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    else:
        query = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())

    page, per_page = pagination_args()
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "admin/audit.html",
        **_ctx(
            logs=pagination.items,
            pagination=pagination,
            users=User.query.order_by(User.name).all(),
            elders=Elder.query.order_by(Elder.name).all(),
            date_range=date_range,
            page_args=query_args_without("page"),
        ),
    )


# ---------------- structured photo library ----------------


@bp.route("/photos")
@login_required("admin")
def photos():
    query = active_photos_query()
    elder_id = request.args.get("elder", type=int)
    kind = request.args.get("kind")
    record_type = request.args.get("type")
    source_record_id = request.args.get("record_id", type=int)
    uploader_id = request.args.get("uploader", type=int)
    abnormal_only = request.args.get("abnormal") == "1"
    keyword = (request.args.get("q") or "").strip()
    date_range = request_date_range()

    if elder_id:
        query = query.filter(Photo.elder_id == elder_id)
    if kind in PHOTO_KIND_ZH:
        query = query.filter(Photo.kind == kind)
    if record_type:
        query = query.filter(Photo.record_type == record_type)
    if source_record_id:
        query = query.filter(Photo.record_id == source_record_id)
    if uploader_id:
        query = query.filter(Photo.uploaded_by == uploader_id)
    if abnormal_only:
        query = query.filter(Photo.abnormal_events.any())
    if date_range.start_date:
        query = query.filter(Photo.record_date >= date_range.start_date)
    if date_range.end_date:
        query = query.filter(Photo.record_date <= date_range.end_date)
    if keyword:
        if keyword.isdigit():
            query = query.filter(Photo.id == int(keyword))
        else:
            query = query.filter(Photo.filename.ilike(f"%{keyword}%"))

    if request.args.get("sort") == "oldest":
        query = query.order_by(Photo.record_date.asc(), Photo.uploaded_at.asc())
    else:
        query = query.order_by(Photo.record_date.desc(), Photo.uploaded_at.desc())
    page, per_page = pagination_args(default_per_page=25)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    grouped = {}
    for photo in pagination.items:
        key = (
            photo.elder.name if photo.elder else "未指定長輩",
            photo.display_date or "日期未記錄",
            photo.kind,
            photo.record_type,
            photo.record_id,
        )
        grouped.setdefault(key, []).append(photo)

    return render_template(
        "admin/photos.html",
        **_ctx(
            photos=pagination.items,
            grouped=grouped,
            pagination=pagination,
            elders=Elder.query.order_by(Elder.name).all(),
            uploaders=User.query.order_by(User.name).all(),
            date_range=date_range,
            page_args=query_args_without("page"),
            view=request.args.get("view", "gallery"),
        ),
    )


# ---------------- abnormal events ----------------


def _abnormal_query():
    query = AbnormalEvent.query
    elder_id = request.args.get("elder", type=int)
    category = request.args.get("category")
    event_type = request.args.get("event_type")
    severity = request.args.get("severity")
    status = request.args.get("status")
    creator = request.args.get("creator", type=int)
    has_photo = request.args.get("photo")
    keyword = (request.args.get("q") or "").strip()
    date_range = request_date_range()

    if elder_id:
        query = query.filter(AbnormalEvent.elder_id == elder_id)
    if category in CATEGORY_LABELS:
        query = query.filter(AbnormalEvent.category == category)
    if event_type:
        query = query.filter(AbnormalEvent.event_type == event_type)
    if severity in ABNORMAL_SEVERITIES:
        query = query.filter(AbnormalEvent.severity == severity)
    if status in ABNORMAL_STATUSES:
        query = query.filter(AbnormalEvent.status == status)
    if creator:
        query = query.filter(AbnormalEvent.created_by == creator)
    if has_photo == "yes":
        query = query.filter(
            AbnormalEvent.photos.any(Photo.deleted_at.is_(None))
        )
    elif has_photo == "no":
        query = query.filter(
            ~AbnormalEvent.photos.any(Photo.deleted_at.is_(None))
        )
    if date_range.start_datetime:
        query = query.filter(AbnormalEvent.occurred_at >= date_range.start_datetime)
    if date_range.end_datetime:
        query = query.filter(AbnormalEvent.occurred_at < date_range.end_datetime)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                AbnormalEvent.observed_text.ilike(pattern),
                AbnormalEvent.handling_note.ilike(pattern),
                AbnormalEvent.metric_code.ilike(pattern),
                AbnormalEvent.event_key.ilike(pattern),
            )
        )
    return query, date_range


@bp.route("/abnormal")
@login_required("admin")
def abnormal():
    query, date_range = _abnormal_query()
    if request.args.get("sort") == "oldest":
        query = query.order_by(AbnormalEvent.occurred_at.asc(), AbnormalEvent.id.asc())
    else:
        query = query.order_by(AbnormalEvent.occurred_at.desc(), AbnormalEvent.id.desc())
    page, per_page = pagination_args()
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    counts = {
        status: AbnormalEvent.query.filter_by(status=status).count()
        for status in ABNORMAL_STATUSES
    }
    event_types = [
        row[0]
        for row in db.session.query(AbnormalEvent.event_type)
        .distinct()
        .order_by(AbnormalEvent.event_type)
        .all()
    ]
    return render_template(
        "admin/abnormal.html",
        **_ctx(
            events=pagination.items,
            pagination=pagination,
            counts=counts,
            event_types=event_types,
            elders=Elder.query.order_by(Elder.name).all(),
            creators=User.query.order_by(User.name).all(),
            date_range=date_range,
            page_args=query_args_without("page"),
        ),
    )


def _event_source(event):
    model_by_source = {
        "vital": VitalRecord,
        "meal": MealRecord,
        "bowel": BowelRecord,
        "med": MedRecord,
    }
    model = model_by_source.get(event.source_type)
    return db.session.get(model, event.source_id) if model else None


@bp.route("/abnormal/<int:event_id>")
@login_required("admin")
def abnormal_detail(event_id):
    event = db.session.get(AbnormalEvent, event_id)
    if event is None:
        return redirect(url_for("admin.abnormal"))
    related_logs = (
        AuditLog.query.filter(
            or_(
                (AuditLog.record_type == "abnormal") & (AuditLog.record_id == event.id),
                (AuditLog.record_type == event.source_type)
                & (AuditLog.record_id == event.source_id),
            )
        )
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    return render_template(
        "admin/abnormal_detail.html",
        **_ctx(event=event, source=_event_source(event), related_logs=related_logs),
    )


@bp.route("/abnormal/<int:event_id>/status", methods=["POST"])
@login_required("admin")
def abnormal_status(event_id):
    event = db.session.get(AbnormalEvent, event_id)
    status = request.form.get("status")
    if event is None or status not in ABNORMAL_STATUSES:
        flash("異常事件或狀態無效", "error")
        return redirect(url_for("admin.abnormal"))
    before = event.status
    note = (request.form.get("handling_note") or "").strip()
    event.status = status
    if status in ("tracking", "resolved", "dismissed") and event.acknowledged_at is None:
        event.acknowledged_by = session.get("user_id")
        event.acknowledged_at = datetime.now()
    if status in ("resolved", "dismissed"):
        event.resolved_by = session.get("user_id")
        event.resolved_at = datetime.now()
    else:
        event.resolved_by = None
        event.resolved_at = None
    if note:
        event.handling_note = note
    log_action(
        session.get("user_id"),
        "update",
        "abnormal",
        event.id,
        f"{before} -> {status}; {note}",
        elder_id=event.elder_id,
        event_code="abnormal.status_update",
        metadata={"before": before, "after": status, "handling_note": note},
    )
    db.session.commit()
    flash("異常事件狀態已更新", "ok")
    return redirect(url_for("admin.abnormal_detail", event_id=event.id))


@bp.route("/abnormal/<int:event_id>/photos", methods=["POST"])
@login_required("admin")
def abnormal_photo_upload(event_id):
    event = db.session.get(AbnormalEvent, event_id)
    if event is None:
        flash("找不到異常事件", "error")
        return redirect(url_for("admin.abnormal"))
    files = request.files.getlist("photo_camera") + request.files.getlist("photo_upload")
    max_photos = int(get_care_parameters().get("max_care_photos_per_record", 5))
    existing_count = len(
        [
            photo
            for photo in event.photos
            if photo.deleted_at is None and photo.kind == "abnormal_followup"
        ]
    )
    result = save_images(
        files,
        kind="abnormal_followup",
        record_type="abnormal",
        record_id=event.id,
        elder_id=event.elder_id,
        record_date=event.occurred_at.date(),
        uploaded_by=session.get("user_id"),
        limit=max(0, max_photos - existing_count),
        start_order=existing_count,
    )
    for photo in result.photos:
        if photo not in event.photos:
            event.photos.append(photo)
    db.session.commit()
    _flash_media_result(result)
    return redirect(url_for("admin.abnormal_detail", event_id=event.id))
