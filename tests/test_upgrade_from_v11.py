from __future__ import annotations

import sqlite3
from pathlib import Path

from app import create_app
from models import db
from services.schema import CURRENT_SCHEMA_VERSION, schema_health


def _create_v11_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA foreign_keys=OFF;
        CREATE TABLE users (
          id INTEGER PRIMARY KEY,
          username VARCHAR(64) NOT NULL UNIQUE,
          name VARCHAR(64) NOT NULL,
          role VARCHAR(16) NOT NULL,
          password_hash VARCHAR(256),
          pin VARCHAR(16),
          lang VARCHAR(8),
          active BOOLEAN,
          created_at DATETIME
        );
        CREATE TABLE elders (
          id INTEGER PRIMARY KEY,
          name VARCHAR(64) NOT NULL,
          birthday DATE,
          notes TEXT,
          water_goal INTEGER,
          active BOOLEAN
        );
        CREATE TABLE med_plans (
          id INTEGER PRIMARY KEY,
          elder_id INTEGER NOT NULL,
          name VARCHAR(128) NOT NULL,
          timeslot VARCHAR(16) NOT NULL,
          meal_relation VARCHAR(8),
          dose_note VARCHAR(128),
          active BOOLEAN
        );
        CREATE TABLE meal_records (
          id INTEGER PRIMARY KEY,
          elder_id INTEGER NOT NULL,
          record_date DATE NOT NULL,
          timeslot VARCHAR(16) NOT NULL,
          intake VARCHAR(16) NOT NULL,
          note VARCHAR(256),
          created_by INTEGER,
          created_at DATETIME,
          updated_at DATETIME,
          UNIQUE(elder_id, record_date, timeslot)
        );
        CREATE TABLE med_records (
          id INTEGER PRIMARY KEY,
          elder_id INTEGER NOT NULL,
          med_plan_id INTEGER NOT NULL,
          record_date DATE NOT NULL,
          given BOOLEAN NOT NULL,
          reason VARCHAR(256),
          created_by INTEGER,
          created_at DATETIME,
          updated_at DATETIME,
          UNIQUE(elder_id, med_plan_id, record_date)
        );
        CREATE TABLE vital_records (
          id INTEGER PRIMARY KEY,
          elder_id INTEGER NOT NULL,
          record_date DATE NOT NULL,
          recorded_at DATETIME,
          weight FLOAT,
          systolic INTEGER,
          diastolic INTEGER,
          pulse INTEGER,
          spo2 INTEGER,
          note VARCHAR(256),
          created_by INTEGER
        );
        CREATE TABLE water_records (
          id INTEGER PRIMARY KEY,
          elder_id INTEGER NOT NULL,
          record_date DATE NOT NULL,
          recorded_at DATETIME,
          amount INTEGER NOT NULL,
          created_by INTEGER
        );
        CREATE TABLE bowel_records (
          id INTEGER PRIMARY KEY,
          elder_id INTEGER NOT NULL,
          record_date DATE NOT NULL,
          recorded_at DATETIME,
          bristol_type INTEGER NOT NULL,
          note VARCHAR(256),
          created_by INTEGER
        );
        CREATE TABLE photos (
          id INTEGER PRIMARY KEY,
          record_type VARCHAR(16) NOT NULL,
          record_id INTEGER NOT NULL,
          elder_id INTEGER NOT NULL,
          filename VARCHAR(512) NOT NULL,
          uploaded_at DATETIME
        );
        CREATE TABLE settings (key VARCHAR(64) PRIMARY KEY, value TEXT);
        CREATE TABLE audit_logs (
          id INTEGER PRIMARY KEY,
          user_id INTEGER,
          action VARCHAR(16),
          record_type VARCHAR(16),
          record_id INTEGER,
          detail TEXT,
          created_at DATETIME
        );
        CREATE TABLE sent_logs (
          id INTEGER PRIMARY KEY,
          ref VARCHAR(128) NOT NULL UNIQUE,
          created_at DATETIME
        );
        INSERT INTO users
          (id, username, name, role, password_hash, pin, lang, active, created_at)
          VALUES (1, 'admin', 'Legacy Admin', 'admin', NULL, NULL, 'zh', 1, CURRENT_TIMESTAMP);
        INSERT INTO elders
          (id, name, birthday, notes, water_goal, active)
          VALUES (1, 'Legacy Elder', '1940-01-01', 'legacy', 1500, 1);
        INSERT INTO photos
          (id, record_type, record_id, elder_id, filename, uploaded_at)
          VALUES (1, 'vital', 999, 1, '1/2026-08-01/vital_legacy.jpg', NULL);
        """
    )
    connection.commit()
    connection.close()


def test_v11_database_upgrades_and_admin_search_pages_render(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "legacy-v11.db"
    upload_path = tmp_path / "uploads"
    upload_path.mkdir()
    _create_v11_database(database_path)
    monkeypatch.setenv("CARELOG_ALLOW_UPGRADE", "1")

    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "legacy-upgrade-test",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "UPLOAD_DIR": str(upload_path),
            "START_SCHEDULER": False,
            "CSRF_ENABLED": False,
        }
    )
    result = application.test_cli_runner().invoke(args=["upgrade-db"])
    assert result.exit_code == 0, result.output
    monkeypatch.delenv("CARELOG_ALLOW_UPGRADE")

    with application.app_context():
        report = schema_health()
        assert report["ok"] is True
        assert report["current_version"] == CURRENT_SCHEMA_VERSION
        columns = {
            row[1]
            for row in db.session.execute(
                __import__("sqlalchemy").text("PRAGMA table_info(elders)")
            )
        }
        assert {"gender", "blood_type", "height_cm", "allergies"} <= columns

    client = application.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["lang"] = "zh"

    for url in ("/admin/photos", "/admin/abnormal", "/admin/elders", "/admin/parameters"):
        response = client.get(url)
        assert response.status_code == 200, (url, response.get_data(as_text=True))

    photo_page = client.get("/admin/photos").get_data(as_text=True)
    assert "Legacy Elder" in photo_page
    assert "日期未記錄" in photo_page

    runner = application.test_cli_runner()
    result = runner.invoke(args=["check-db"])
    assert result.exit_code == 0
    assert "資料庫結構檢查通過" in result.output
