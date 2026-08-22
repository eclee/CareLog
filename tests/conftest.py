from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from models import db, Elder, User


@pytest.fixture()
def app(tmp_path: Path):
    database_path = tmp_path / "test.db"
    upload_path = tmp_path / "uploads"
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "UPLOAD_DIR": str(upload_path),
            "START_SCHEDULER": False,
            "CSRF_ENABLED": False,
        }
    )
    with application.app_context():
        db.create_all()

        admin = User(
            username="admin", name="Admin", role="admin", pin="1111", lang="zh"
        )
        admin.set_password("admin-password")
        worker = User(
            username="worker", name="Worker", role="worker", pin="1234", lang="vi"
        )
        worker.set_password("worker-password")
        family = User(
            username="family", name="Family", role="family", pin="2222", lang="zh"
        )
        family.set_password("family-password")
        elder = Elder(name="Test Elder", water_goal=1500)
        db.session.add_all([admin, worker, family, elder])
        db.session.commit()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login_as(client, user_id: int, lang: str = "zh"):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["lang"] = lang
        session.permanent = True
