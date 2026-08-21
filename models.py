import json
from datetime import datetime, date

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

TIMESLOTS = ["morning", "noon", "evening", "bedtime"]


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    role = db.Column(db.String(16), nullable=False)  # admin / family / worker
    password_hash = db.Column(db.String(256))
    pin = db.Column(db.String(16))  # worker quick login
    lang = db.Column(db.String(16), default="zh")
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return bool(self.password_hash) and check_password_hash(self.password_hash, pw)


class Elder(db.Model):
    __tablename__ = "elders"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    birthday = db.Column(db.Date, default=lambda: date(1940, 1, 1))
    notes = db.Column(db.Text, default="")
    water_goal = db.Column(db.Integer, default=1500)  # ml / day
    active = db.Column(db.Boolean, default=True)


class MedPlan(db.Model):
    __tablename__ = "med_plans"
    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    timeslot = db.Column(db.String(16), nullable=False)          # morning/noon/evening/bedtime
    meal_relation = db.Column(db.String(8), default="none")      # before / after / none
    dose_note = db.Column(db.String(128), default="")
    active = db.Column(db.Boolean, default=True)
    elder = db.relationship("Elder")


class MealRecord(db.Model):
    __tablename__ = "meal_records"
    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today)
    timeslot = db.Column(db.String(16), nullable=False)
    intake = db.Column(db.String(16), nullable=False)  # all / half / little / none
    supplement = db.Column(db.Boolean)                 # 營養品：None=未填(舊資料)
    supplement_cc = db.Column(db.Integer)              # 有喝時的 cc 數
    note = db.Column(db.String(256), default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    __table_args__ = (db.UniqueConstraint("elder_id", "record_date", "timeslot"),)


class MedRecord(db.Model):
    __tablename__ = "med_records"
    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    med_plan_id = db.Column(db.Integer, db.ForeignKey("med_plans.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today)
    given = db.Column(db.Boolean, nullable=False)
    reason = db.Column(db.String(256), default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    plan = db.relationship("MedPlan")
    __table_args__ = (db.UniqueConstraint("elder_id", "med_plan_id", "record_date"),)


class VitalRecord(db.Model):
    __tablename__ = "vital_records"
    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today)
    recorded_at = db.Column(db.DateTime, default=datetime.now)
    weight = db.Column(db.Float)      # kg
    systolic = db.Column(db.Integer)  # mmHg
    diastolic = db.Column(db.Integer)
    pulse = db.Column(db.Integer)
    spo2 = db.Column(db.Integer)      # %
    note = db.Column(db.String(256), default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class WaterRecord(db.Model):
    __tablename__ = "water_records"
    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today)
    recorded_at = db.Column(db.DateTime, default=datetime.now)
    amount = db.Column(db.Integer, nullable=False)  # ml
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class BowelRecord(db.Model):
    __tablename__ = "bowel_records"
    id = db.Column(db.Integer, primary_key=True)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today)
    recorded_at = db.Column(db.DateTime, default=datetime.now)
    bristol_type = db.Column(db.Integer, nullable=False)  # 1-7
    note = db.Column(db.String(256), default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class Photo(db.Model):
    __tablename__ = "photos"
    id = db.Column(db.Integer, primary_key=True)
    record_type = db.Column(db.String(16), nullable=False)  # meal/med/vital/bowel
    record_id = db.Column(db.Integer, nullable=False)
    elder_id = db.Column(db.Integer, db.ForeignKey("elders.id"))
    filename = db.Column(db.String(256), nullable=False)  # relative to uploads/
    uploaded_at = db.Column(db.DateTime, default=datetime.now)


class Setting(db.Model):
    __tablename__ = "settings"
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(16))       # create / update / delete
    record_type = db.Column(db.String(16))
    record_id = db.Column(db.Integer)
    detail = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.now)
    user = db.relationship("User")


class SentLog(db.Model):
    """Prevents duplicate scheduled sends. ref e.g. 'report_daily:2026-08-14'."""
    __tablename__ = "sent_logs"
    id = db.Column(db.Integer, primary_key=True)
    ref = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


# ---------------- settings helpers ----------------

DEFAULT_SETTINGS = {
    "smtp_user": "",
    "smtp_password": "",
    "recipients": "",
    "report_items": {"meals": True, "meds": True, "vitals": True, "water": True, "bowel": True},
    "report_daily": {"enabled": False, "time": "21:00"},
    "report_weekly": {"enabled": False, "weekday": 6, "time": "20:00"},   # 6 = Sunday
    "report_monthly": {"enabled": False, "day": 1, "time": "09:00"},
    "thresholds": {
        "enabled": True,
        "sys_hi": 160, "sys_lo": 90, "dia_hi": 100, "dia_lo": 55,
        "pulse_hi": 110, "pulse_lo": 45, "spo2_lo": 92,
    },
    "reminders": {
        "enabled": False,
        "morning": "09:30", "noon": "13:30", "evening": "19:30", "bedtime": "22:30",
    },
    "pdf_attach": True,
}


def get_setting(key):
    row = db.session.get(Setting, key)
    if row is None:
        return DEFAULT_SETTINGS.get(key)
    try:
        return json.loads(row.value)
    except (TypeError, ValueError):
        return row.value


def set_setting(key, value):
    row = db.session.get(Setting, key)
    if row is None:
        row = Setting(key=key)
        db.session.add(row)
    row.value = json.dumps(value, ensure_ascii=False)
    db.session.commit()


def log_action(user_id, action, record_type, record_id, detail=""):
    db.session.add(AuditLog(user_id=user_id, action=action, record_type=record_type,
                            record_id=record_id, detail=detail))
