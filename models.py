import copy
import json
from datetime import date, datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()

TIMESLOTS = ["morning", "noon", "evening", "bedtime"]
USER_ROLES = ("admin", "family", "worker")
GENDER_VALUES = ("unspecified", "female", "male", "other")
BLOOD_TYPE_VALUES = ("unknown", "A", "B", "AB", "O")
RH_FACTOR_VALUES = ("unknown", "positive", "negative")
ABNORMAL_STATUSES = ("pending", "tracking", "resolved", "dismissed")
ABNORMAL_SEVERITIES = ("attention", "warning", "critical")


abnormal_event_photos = db.Table(
    "abnormal_event_photos",
    db.Column(
        "abnormal_event_id",
        db.Integer,
        db.ForeignKey("abnormal_events.id"),
        primary_key=True,
    ),
    db.Column(
        "photo_id",
        db.Integer,
        db.ForeignKey("photos.id"),
        primary_key=True,
    ),
)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    role = db.Column(db.String(16), nullable=False)  # admin / family / worker
    password_hash = db.Column(db.String(256))  # required for active accounts; cleared on soft delete
    pin = db.Column(db.String(16))  # required for active accounts; workers use it to sign in
    lang = db.Column(db.String(16), default="zh")
    active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    deleted_at = db.Column(db.DateTime, index=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(self.password_hash) and check_password_hash(
            self.password_hash, password
        )

    @property
    def is_deleted(self):
        return self.deleted_at is not None


class Elder(db.Model):
    __tablename__ = "elders"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    birthday = db.Column(db.Date, default=lambda: date(1940, 1, 1))
    gender = db.Column(db.String(16), default="unspecified")
    blood_type = db.Column(db.String(8), default="unknown")
    rh_factor = db.Column(db.String(16), default="unknown")
    height_cm = db.Column(db.Float)
    phone = db.Column(db.String(32), default="")
    address = db.Column(db.String(256), default="")
    allergies = db.Column(db.Text, default="")
    chronic_conditions = db.Column(db.Text, default="")
    primary_hospital = db.Column(db.String(128), default="")
    primary_physician = db.Column(db.String(64), default="")
    emergency_contact_name = db.Column(db.String(64), default="")
    emergency_contact_relation = db.Column(db.String(32), default="")
    emergency_contact_phone = db.Column(db.String(32), default="")
    notes = db.Column(db.Text, default="")
    water_goal = db.Column(db.Integer, default=1500)  # ml / day
    active = db.Column(db.Boolean, default=True, index=True)


class ElderSetting(db.Model):
    """Per-elder JSON settings. Keys can grow without changing the elder table."""

    __tablename__ = "elder_settings"

    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False, index=True)
    key = db.Column(db.String(64), nullable=False)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    elder = db.relationship("Elder")
    __table_args__ = (
        db.UniqueConstraint("elder_id", "key", name="uq_elder_setting_key"),
    )


class MedPlan(db.Model):
    __tablename__ = "med_plans"

    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    timeslot = db.Column(db.String(16), nullable=False)
    meal_relation = db.Column(db.String(8), default="none")
    dose_note = db.Column(db.String(128), default="")
    active = db.Column(db.Boolean, default=True, index=True)
    elder = db.relationship("Elder")


class MealRecord(db.Model):
    __tablename__ = "meal_records"

    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    timeslot = db.Column(db.String(16), nullable=False)
    intake = db.Column(db.String(16), nullable=False)  # all / half / little / none
    supplement = db.Column(db.Boolean)
    supplement_cc = db.Column(db.Integer)
    note = db.Column(db.String(256), default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    __table_args__ = (
        db.UniqueConstraint("elder_id", "record_date", "timeslot"),
    )


class MedSubmission(db.Model):
    """One medication-form submission containing one or more medication records."""

    __tablename__ = "med_submissions"

    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    timeslot = db.Column(db.String(16), nullable=False)
    meal_relation = db.Column(db.String(8), nullable=False, default="none")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    elder = db.relationship("Elder")
    records = db.relationship("MedRecord", back_populates="submission")
    __table_args__ = (
        db.UniqueConstraint(
            "elder_id",
            "record_date",
            "timeslot",
            "meal_relation",
            name="uq_med_submission_group",
        ),
    )


class MedRecord(db.Model):
    __tablename__ = "med_records"

    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    med_plan_id = db.Column(db.Integer, db.ForeignKey("med_plans.id"), nullable=False)
    submission_id = db.Column(db.Integer, db.ForeignKey("med_submissions.id"))
    record_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    given = db.Column(db.Boolean, nullable=False)
    reason = db.Column(db.String(256), default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    plan = db.relationship("MedPlan")
    submission = db.relationship("MedSubmission", back_populates="records")
    __table_args__ = (
        db.UniqueConstraint("elder_id", "med_plan_id", "record_date"),
    )


class VitalRecord(db.Model):
    __tablename__ = "vital_records"

    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    recorded_at = db.Column(db.DateTime, default=datetime.now, index=True)
    weight = db.Column(db.Float)
    systolic = db.Column(db.Integer)
    diastolic = db.Column(db.Integer)
    pulse = db.Column(db.Integer)
    spo2 = db.Column(db.Integer)
    note = db.Column(db.String(256), default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class WaterRecord(db.Model):
    __tablename__ = "water_records"

    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    recorded_at = db.Column(db.DateTime, default=datetime.now, index=True)
    amount = db.Column(db.Integer, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class BowelRecord(db.Model):
    __tablename__ = "bowel_records"

    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    recorded_at = db.Column(db.DateTime, default=datetime.now, index=True)
    bristol_type = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(256), default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class Photo(db.Model):
    """Unified media asset for care evidence, medicine references and follow-up."""

    __tablename__ = "photos"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(32), default="care_evidence", nullable=False, index=True)
    record_type = db.Column(db.String(32), nullable=False, index=True)
    record_id = db.Column(db.Integer, nullable=False, index=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), index=True)
    record_date = db.Column(db.Date, index=True)
    filename = db.Column(db.String(512), nullable=False)
    thumbnail_filename = db.Column(db.String(512))
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    sort_order = db.Column(db.Integer, default=0)
    is_primary = db.Column(db.Boolean, default=False)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(64), default="image/jpeg")
    checksum = db.Column(db.String(64))
    uploaded_at = db.Column(db.DateTime, default=datetime.now, index=True)
    deleted_at = db.Column(db.DateTime, index=True)

    elder = db.relationship("Elder")
    uploader = db.relationship("User", foreign_keys=[uploaded_by])
    abnormal_events = db.relationship(
        "AbnormalEvent",
        secondary=abnormal_event_photos,
        back_populates="photos",
    )

    @property
    def active(self):
        return self.deleted_at is None

    @property
    def display_date(self):
        """Best-effort date for legacy photos whose metadata may be incomplete."""

        if self.record_date is not None:
            return self.record_date
        if self.uploaded_at is not None:
            return self.uploaded_at.date()
        return None


class Setting(db.Model):
    __tablename__ = "settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    actor_username = db.Column(db.String(64), index=True)
    actor_name = db.Column(db.String(64))
    actor_role = db.Column(db.String(16), index=True)
    action = db.Column(db.String(16), index=True)
    record_type = db.Column(db.String(32), index=True)
    record_id = db.Column(db.Integer, index=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), index=True)
    elder_name_snapshot = db.Column(db.String(64))
    event_code = db.Column(db.String(64), index=True)
    detail = db.Column(db.Text, default="")
    metadata_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)

    user = db.relationship("User", foreign_keys=[user_id])
    elder = db.relationship("Elder", foreign_keys=[elder_id])

    @property
    def actor_display(self):
        return self.actor_name or (self.user.name if self.user else None) or "系統"

    @property
    def metadata_dict(self):
        if not self.metadata_json:
            return {}
        try:
            return json.loads(self.metadata_json)
        except (TypeError, ValueError):
            return {}


class AbnormalEvent(db.Model):
    __tablename__ = "abnormal_events"

    id = db.Column(db.Integer, primary_key=True)
    event_key = db.Column(db.String(160), unique=True, nullable=False, index=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False, index=True)
    occurred_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)
    detected_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    category = db.Column(db.String(32), nullable=False, index=True)
    event_type = db.Column(db.String(64), nullable=False, index=True)
    metric_code = db.Column(db.String(64), index=True)
    direction = db.Column(db.String(16))
    observed_value = db.Column(db.Float)
    observed_text = db.Column(db.String(256))
    unit = db.Column(db.String(24))
    threshold_operator = db.Column(db.String(8))
    threshold_value = db.Column(db.Float)
    threshold_snapshot = db.Column(db.Text)
    severity = db.Column(db.String(16), default="warning", index=True)
    status = db.Column(db.String(16), default="pending", index=True)
    source_type = db.Column(db.String(32), nullable=False, index=True)
    source_id = db.Column(db.Integer, nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    acknowledged_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    resolved_at = db.Column(db.DateTime)
    handling_note = db.Column(db.Text, default="")
    notification_status = db.Column(db.String(32), default="not_requested")

    elder = db.relationship("Elder")
    creator = db.relationship("User", foreign_keys=[created_by])
    acknowledger = db.relationship("User", foreign_keys=[acknowledged_by])
    resolver = db.relationship("User", foreign_keys=[resolved_by])
    photos = db.relationship(
        "Photo",
        secondary=abnormal_event_photos,
        back_populates="abnormal_events",
    )

    @property
    def threshold(self):
        if not self.threshold_snapshot:
            return {}
        try:
            return json.loads(self.threshold_snapshot)
        except (TypeError, ValueError):
            return {}


class SentLog(db.Model):
    """Prevents duplicate scheduled sends. ref e.g. report_daily:2026-08-14."""

    __tablename__ = "sent_logs"

    id = db.Column(db.Integer, primary_key=True)
    ref = db.Column(db.String(128), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


DEFAULT_ELDER_PARAMETERS = {
    "version": 1,
    "vital_defaults": {
        "weight": None,
        "systolic": None,
        "diastolic": None,
        "pulse": None,
        "spo2": None,
    },
}


DEFAULT_CARE_PARAMETERS = {
    "version": 1,
    "water_quick_amounts_ml": [100, 250, 500],
    "default_elder_birthday": "1940-01-01",
    "default_water_goal_ml": 1500,
    "water_entry_min_ml": 10,
    "water_entry_max_ml": 2000,
    "dashboard_default_days": 30,
    "max_care_photos_per_record": 5,
    "max_medication_photos_per_plan": 3,
    "abnormal_rules": {
        "vitals_enabled": True,
        "sys_hi": 160,
        "sys_lo": 90,
        "dia_hi": 100,
        "dia_lo": 55,
        "pulse_hi": 110,
        "pulse_lo": 45,
        "spo2_lo": 92,
        "med_not_given_enabled": True,
        "bowel_enabled": True,
        "bowel_types": [1, 2, 6, 7],
        "meal_none_enabled": True,
        "meal_little_enabled": False,
        "water_low_enabled": False,
        "water_close_time": "22:00",
        "water_min_percent": 100,
    },
}


DEFAULT_SETTINGS = {
    "smtp_user": "",
    "smtp_password": "",
    "recipients": "",
    "report_items": {
        "meals": True,
        "meds": True,
        "vitals": True,
        "water": True,
        "bowel": True,
    },
    "report_daily": {"enabled": False, "time": "21:00"},
    "report_weekly": {"enabled": False, "weekday": 6, "time": "20:00"},
    "report_monthly": {"enabled": False, "day": 1, "time": "09:00"},
    # Kept for backward compatibility. New code reads care_parameters.abnormal_rules.
    "thresholds": {
        "enabled": True,
        "sys_hi": 160,
        "sys_lo": 90,
        "dia_hi": 100,
        "dia_lo": 55,
        "pulse_hi": 110,
        "pulse_lo": 45,
        "spo2_lo": 92,
    },
    "reminders": {
        "enabled": False,
        # Slot switches default to on so existing installations keep their
        # previous behaviour when the master reminder switch is enabled.
        "morning_enabled": True,
        "morning": "09:30",
        "noon_enabled": True,
        "noon": "13:30",
        "evening_enabled": True,
        "evening": "19:30",
        "bedtime_enabled": True,
        "bedtime": "22:30",
    },
    "pdf_attach": True,
    "care_parameters": DEFAULT_CARE_PARAMETERS,
}


def _deep_merge(defaults, override):
    result = copy.deepcopy(defaults)
    if not isinstance(override, dict):
        return result
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_setting(key):
    row = db.session.get(Setting, key)
    if row is None:
        return copy.deepcopy(DEFAULT_SETTINGS.get(key))
    try:
        value = json.loads(row.value)
    except (TypeError, ValueError):
        return row.value
    default = DEFAULT_SETTINGS.get(key)
    if isinstance(default, dict) and isinstance(value, dict):
        return _deep_merge(default, value)
    return value


def set_setting(key, value, *, commit=True):
    row = db.session.get(Setting, key)
    if row is None:
        row = Setting(key=key)
        db.session.add(row)
    row.value = json.dumps(value, ensure_ascii=False)
    if commit:
        db.session.commit()
    return row


def get_care_parameters():
    value = get_setting("care_parameters")
    return _deep_merge(DEFAULT_CARE_PARAMETERS, value)


def get_elder_setting(elder_id, key, default=None):
    row = ElderSetting.query.filter_by(elder_id=elder_id, key=key).first()
    if row is None or row.value is None:
        return copy.deepcopy(default)
    try:
        return json.loads(row.value)
    except (TypeError, ValueError):
        return copy.deepcopy(default)


def set_elder_setting(elder_id, key, value, *, commit=True):
    row = ElderSetting.query.filter_by(elder_id=elder_id, key=key).first()
    if row is None:
        row = ElderSetting(elder_id=elder_id, key=key)
        db.session.add(row)
    row.value = json.dumps(value, ensure_ascii=False)
    if commit:
        db.session.commit()
    return row


def get_elder_parameters(elder_id):
    value = get_elder_setting(elder_id, "care_parameters", {})
    return _deep_merge(DEFAULT_ELDER_PARAMETERS, value)


def log_action(
    user_id,
    action,
    record_type,
    record_id,
    detail="",
    *,
    elder_id=None,
    event_code=None,
    metadata=None,
):
    user = db.session.get(User, user_id) if user_id else None
    elder = db.session.get(Elder, elder_id) if elder_id else None
    log = AuditLog(
        user_id=user_id if user else None,
        actor_username=user.username if user else "system",
        actor_name=user.name if user else "系統",
        actor_role=user.role if user else "system",
        action=action,
        record_type=record_type,
        record_id=record_id,
        elder_id=elder_id,
        elder_name_snapshot=elder.name if elder else None,
        event_code=event_code,
        detail=detail,
        metadata_json=(
            json.dumps(metadata, ensure_ascii=False, default=str)
            if metadata is not None
            else None
        ),
    )
    db.session.add(log)
    return log
