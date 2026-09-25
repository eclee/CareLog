"""Small, dependency-free compatibility migrations for SQLite deployments.

CareLog intentionally keeps a lightweight deployment footprint. New installations are
created with SQLAlchemy metadata; existing databases require the explicit upgrade-db
command after backup. The migration adds nullable/defaulted columns, new tables and
indexes, and can be safely rerun.
"""

from __future__ import annotations

from datetime import date

from flask import current_app
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from models import db


CURRENT_SCHEMA_VERSION = 4


COLUMN_MIGRATIONS = {
    "elders": {
        "gender": "VARCHAR(16) DEFAULT 'unspecified'",
        "blood_type": "VARCHAR(8) DEFAULT 'unknown'",
        "rh_factor": "VARCHAR(16) DEFAULT 'unknown'",
        "height_cm": "FLOAT",
        "phone": "VARCHAR(32) DEFAULT ''",
        "address": "VARCHAR(256) DEFAULT ''",
        "allergies": "TEXT DEFAULT ''",
        "chronic_conditions": "TEXT DEFAULT ''",
        "primary_hospital": "VARCHAR(128) DEFAULT ''",
        "primary_physician": "VARCHAR(64) DEFAULT ''",
        "emergency_contact_name": "VARCHAR(64) DEFAULT ''",
        "emergency_contact_relation": "VARCHAR(32) DEFAULT ''",
        "emergency_contact_phone": "VARCHAR(32) DEFAULT ''",
    },
    "meal_records": {
        "supplement": "BOOLEAN",
        "supplement_cc": "INTEGER",
    },
    "users": {
        "deleted_at": "DATETIME",
        "pin_hash": "VARCHAR(256)",
    },
    "med_records": {
        "submission_id": "INTEGER",
        "plan_version_id": "INTEGER",
    },
    "photos": {
        "kind": "VARCHAR(32) DEFAULT 'care_evidence'",
        "record_date": "DATE",
        "thumbnail_filename": "VARCHAR(512)",
        "uploaded_by": "INTEGER",
        "sort_order": "INTEGER DEFAULT 0",
        "is_primary": "BOOLEAN DEFAULT 0",
        "width": "INTEGER",
        "height": "INTEGER",
        "file_size": "INTEGER",
        "mime_type": "VARCHAR(64) DEFAULT 'image/jpeg'",
        "checksum": "VARCHAR(64)",
        "deleted_at": "DATETIME",
    },
    "audit_logs": {
        "actor_username": "VARCHAR(64)",
        "actor_name": "VARCHAR(64)",
        "actor_role": "VARCHAR(16)",
        "elder_id": "INTEGER",
        "elder_name_snapshot": "VARCHAR(64)",
        "event_code": "VARCHAR(64)",
        "metadata_json": "TEXT",
    },
}


INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS ix_elder_settings_elder_id ON elder_settings (elder_id)",
    "CREATE INDEX IF NOT EXISTS ix_users_active ON users (active)",
    "CREATE INDEX IF NOT EXISTS ix_users_deleted_at ON users (deleted_at)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_role ON audit_logs (actor_role)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_record_type ON audit_logs (record_type)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_record_id ON audit_logs (record_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_elder_id ON audit_logs (elder_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_event_code ON audit_logs (event_code)",
    "CREATE INDEX IF NOT EXISTS ix_photos_kind ON photos (kind)",
    "CREATE INDEX IF NOT EXISTS ix_photos_record_type ON photos (record_type)",
    "CREATE INDEX IF NOT EXISTS ix_photos_record_id ON photos (record_id)",
    "CREATE INDEX IF NOT EXISTS ix_photos_elder_id ON photos (elder_id)",
    "CREATE INDEX IF NOT EXISTS ix_photos_record_date ON photos (record_date)",
    "CREATE INDEX IF NOT EXISTS ix_photos_uploaded_by ON photos (uploaded_by)",
    "CREATE INDEX IF NOT EXISTS ix_photos_uploaded_at ON photos (uploaded_at)",
    "CREATE INDEX IF NOT EXISTS ix_photos_deleted_at ON photos (deleted_at)",
]


REQUIRED_SCHEMA = {
    "elders": {
        "gender",
        "blood_type",
        "rh_factor",
        "height_cm",
        "phone",
        "address",
        "allergies",
        "chronic_conditions",
        "primary_hospital",
        "primary_physician",
        "emergency_contact_name",
        "emergency_contact_relation",
        "emergency_contact_phone",
    },
    "users": {"deleted_at", "pin_hash"},
    "meal_records": {"supplement", "supplement_cc"},
    "photos": {
        "kind",
        "record_date",
        "thumbnail_filename",
        "uploaded_by",
        "sort_order",
        "is_primary",
        "width",
        "height",
        "file_size",
        "mime_type",
        "checksum",
        "deleted_at",
    },
    "audit_logs": {
        "actor_username",
        "actor_name",
        "actor_role",
        "elder_id",
        "elder_name_snapshot",
        "event_code",
        "metadata_json",
    },
    "med_records": {"submission_id", "plan_version_id"},
    "user_elder_access": {"user_id", "elder_id"},
    "login_attempts": {"id", "identity_key", "ip_key", "created_at"},
    "med_plan_versions": {"id", "med_plan_id", "elder_id", "effective_on", "name", "timeslot", "meal_relation", "dose_note", "active"},
    "settings": {"key", "value"},
    "elder_settings": {"id", "elder_id", "key", "value", "updated_at"},
    "med_submissions": {
        "elder_id",
        "record_date",
        "timeslot",
        "meal_relation",
        "created_by",
    },
    "abnormal_events": {
        "event_key",
        "elder_id",
        "occurred_at",
        "category",
        "event_type",
        "metric_code",
        "observed_value",
        "observed_text",
        "severity",
        "status",
        "source_type",
        "source_id",
        "created_by",
        "handling_note",
        "notification_status",
    },
    "abnormal_event_photos": {"abnormal_event_id", "photo_id"},
}


def schema_health() -> dict[str, object]:
    """Return a compact database compatibility report without mutating data."""

    inspector = inspect(db.engine)
    existing = set(inspector.get_table_names())
    missing_tables = sorted(set(REQUIRED_SCHEMA) - existing)
    missing_columns: dict[str, list[str]] = {}
    for table_name, required in REQUIRED_SCHEMA.items():
        if table_name not in existing:
            continue
        present = {column["name"] for column in inspector.get_columns(table_name)}
        missing = sorted(required - present)
        if missing:
            missing_columns[table_name] = missing
    plaintext_pins = 0
    if "users" in existing and "pin_hash" in {c["name"] for c in inspector.get_columns("users")}:
        plaintext_pins = db.session.execute(text(
            "SELECT COUNT(*) FROM users WHERE pin IS NOT NULL AND pin != ''"
        )).scalar() or 0
    stored_version = None
    if "settings" in existing:
        stored_version = db.session.execute(text(
            "SELECT value FROM settings WHERE key='schema_version'"
        )).scalar()
    return {
        "current_version": CURRENT_SCHEMA_VERSION,
        "stored_version": stored_version,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "plaintext_pins": plaintext_pins,
        "ok": not missing_tables and not missing_columns and not plaintext_pins
              and stored_version == str(CURRENT_SCHEMA_VERSION),
    }


def schema_health_message(report: dict[str, object] | None = None) -> str:
    report = report or schema_health()
    parts: list[str] = []
    missing_tables = report.get("missing_tables") or []
    if missing_tables:
        parts.append("缺少資料表：" + ", ".join(missing_tables))
    missing_columns = report.get("missing_columns") or {}
    for table_name, columns in missing_columns.items():
        parts.append(f"{table_name} 缺少欄位：" + ", ".join(columns))
    if report.get("plaintext_pins"):
        parts.append(f"仍有 {report['plaintext_pins']} 個明文 PIN 待遷移")
    if report.get("stored_version") != str(CURRENT_SCHEMA_VERSION):
        parts.append(f"結構版本 {report.get('stored_version') or '未記錄'}，需為 {CURRENT_SCHEMA_VERSION}")
    return "；".join(parts) or "資料庫結構正常"


def _columns(table_name: str) -> set[str]:
    rows = db.session.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in rows}



def _backfill_photo_source(table_name: str, record_type: str) -> None:
    """Copy the original care date and author into legacy photo metadata."""

    db.session.execute(
        text(
            f"UPDATE photos SET "
            f"record_date=COALESCE(record_date, "
            f"(SELECT record_date FROM {table_name} WHERE {table_name}.id=photos.record_id)), "
            f"uploaded_by=COALESCE(uploaded_by, "
            f"(SELECT created_by FROM {table_name} WHERE {table_name}.id=photos.record_id)) "
            f"WHERE record_type=:record_type"
        ),
        {"record_type": record_type},
    )


def _backfill_audit_elder(table_name: str, record_type: str) -> None:
    db.session.execute(
        text(
            f"UPDATE audit_logs SET elder_id=COALESCE(elder_id, "
            f"(SELECT elder_id FROM {table_name} WHERE {table_name}.id=audit_logs.record_id)) "
            f"WHERE record_type=:record_type AND elder_id IS NULL"
        ),
        {"record_type": record_type},
    )


def ensure_schema_compatibility(*, create_missing: bool = True) -> list[str]:
    """Upgrade a database created by an older CareLog release.

    Returns a human-readable list of actions.  It is safe to call repeatedly.
    """

    actions: list[str] = []
    inspector = inspect(db.engine)
    existing = set(inspector.get_table_names())
    old_tables = existing.copy()
    if not existing and not create_missing:
        return actions

    if create_missing:
        db.create_all()
        existing = set(inspect(db.engine).get_table_names())

    for table_name, definitions in COLUMN_MIGRATIONS.items():
        if table_name not in existing:
            continue
        present = _columns(table_name)
        for column_name, sql_type in definitions.items():
            if column_name in present:
                continue
            db.session.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN {column_name} {sql_type}"
                )
            )
            actions.append(f"added {table_name}.{column_name}")

    if "user_elder_access" not in old_tables and "users" in old_tables:
        db.session.execute(text(
            "INSERT INTO user_elder_access (user_id, elder_id) "
            "SELECT users.id, elders.id FROM users CROSS JOIN elders "
            "WHERE users.active = 1 AND users.deleted_at IS NULL AND elders.active = 1"
        ))
        actions.append("backfilled user-to-elder access")

    if "users" in existing:
        rows = db.session.execute(text(
            "SELECT id, pin FROM users WHERE pin IS NOT NULL AND pin != ''"
        )).all()
        for user_id, pin in rows:
            db.session.execute(text(
                "UPDATE users SET pin_hash=:hash, pin=NULL WHERE id=:id"
            ), {"hash": generate_password_hash(str(pin)), "id": user_id})
        if rows:
            actions.append(f"hashed and cleared {len(rows)} legacy PINs")

    if "med_plan_versions" not in old_tables and "med_plans" in old_tables:
        db.session.execute(text(
            "INSERT INTO med_plan_versions "
            "(med_plan_id, elder_id, effective_on, changed_at, name, timeslot, meal_relation, dose_note, active) "
            "SELECT id, elder_id, :today, CURRENT_TIMESTAMP, name, timeslot, "
            "COALESCE(meal_relation, 'none'), COALESCE(dose_note, ''), active FROM med_plans"
        ), {"today": date.today().isoformat()})
        actions.append("snapshotted existing medication plans from migration date")

    # Existing rows receive useful defaults/snapshots.  These statements are
    # intentionally conservative and never overwrite already populated values.
    if "photos" in existing:
        db.session.execute(
            text(
                "UPDATE photos SET kind='care_evidence' "
                "WHERE kind IS NULL OR kind=''"
            )
        )
        source_tables = {
            "meal": "meal_records",
            "med": "med_records",
            "vital": "vital_records",
            "bowel": "bowel_records",
        }
        for record_type, table_name in source_tables.items():
            if table_name in existing:
                _backfill_photo_source(table_name, record_type)
        db.session.execute(
            text(
                "UPDATE photos SET record_date=DATE(uploaded_at) "
                "WHERE record_date IS NULL"
            )
        )
        db.session.execute(
            text(
                "UPDATE photos SET mime_type='image/jpeg' "
                "WHERE mime_type IS NULL OR mime_type=''"
            )
        )

    if "audit_logs" in existing and "users" in existing:
        db.session.execute(
            text(
                "UPDATE audit_logs SET "
                "actor_username=(SELECT username FROM users WHERE users.id=audit_logs.user_id), "
                "actor_name=(SELECT name FROM users WHERE users.id=audit_logs.user_id), "
                "actor_role=(SELECT role FROM users WHERE users.id=audit_logs.user_id) "
                "WHERE user_id IS NOT NULL AND "
                "(actor_username IS NULL OR actor_name IS NULL OR actor_role IS NULL)"
            )
        )
        audit_sources = {
            "meal": "meal_records",
            "med": "med_records",
            "vital": "vital_records",
            "water": "water_records",
            "bowel": "bowel_records",
            "medplan": "med_plans",
        }
        for record_type, table_name in audit_sources.items():
            if table_name in existing:
                _backfill_audit_elder(table_name, record_type)
        if "elders" in existing:
            db.session.execute(
                text(
                    "UPDATE audit_logs SET elder_name_snapshot="
                    "(SELECT name FROM elders WHERE elders.id=audit_logs.elder_id) "
                    "WHERE elder_id IS NOT NULL AND elder_name_snapshot IS NULL"
                )
            )
        db.session.execute(
            text(
                "UPDATE audit_logs SET actor_username='system', "
                "actor_name='系統', actor_role='system' "
                "WHERE actor_username IS NULL"
            )
        )

    if "elders" in existing:
        db.session.execute(
            text(
                "UPDATE elders SET gender='unspecified' "
                "WHERE gender IS NULL OR gender=''"
            )
        )
        db.session.execute(
            text(
                "UPDATE elders SET blood_type='unknown' "
                "WHERE blood_type IS NULL OR blood_type=''"
            )
        )
        db.session.execute(
            text(
                "UPDATE elders SET rh_factor='unknown' "
                "WHERE rh_factor IS NULL OR rh_factor=''"
            )
        )

    for statement in INDEX_STATEMENTS:
        table_name = statement.split(" ON ", 1)[1].split(" ", 1)[0]
        if table_name in existing:
            db.session.execute(text(statement))

    if "settings" in existing:
        db.session.execute(
            text(
                "INSERT OR REPLACE INTO settings (key, value) "
                "VALUES ('schema_version', :value)"
            ),
            {"value": str(CURRENT_SCHEMA_VERSION)},
        )

    db.session.commit()
    report = schema_health()
    if not report["ok"]:
        raise RuntimeError("CareLog 資料庫升級不完整：" + schema_health_message(report))
    if actions:
        current_app.logger.info("CareLog schema upgraded: %s", ", ".join(actions))
    return actions
