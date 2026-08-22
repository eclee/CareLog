"""Small, dependency-free compatibility migrations for SQLite deployments.

CareLog intentionally keeps a lightweight deployment footprint.  New installations are
created with SQLAlchemy metadata; existing 1.1.x databases are upgraded in place by
adding nullable/defaulted columns and new indexes.  The command is idempotent.
"""

from __future__ import annotations

from flask import current_app
from sqlalchemy import inspect, text

from models import db


COLUMN_MIGRATIONS = {
    "meal_records": {
        "supplement": "BOOLEAN",
        "supplement_cc": "INTEGER",
    },
    "users": {
        "deleted_at": "DATETIME",
    },
    "med_records": {
        "submission_id": "INTEGER",
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

    for statement in INDEX_STATEMENTS:
        table_name = statement.split(" ON ", 1)[1].split(" ", 1)[0]
        if table_name in existing:
            db.session.execute(text(statement))

    db.session.commit()
    if actions:
        current_app.logger.info("CareLog schema upgraded: %s", ", ".join(actions))
    return actions
