from __future__ import annotations

from datetime import date, datetime, timedelta
import re

from models import (
    db,
    AuditLog,
    Elder,
    MealRecord,
    User,
    VitalRecord,
    WaterRecord,
)
from services.reports import build_html, collect_period
from services.alerts import check_and_alert
from translations import LANGUAGES, T
from tests.conftest import login_as


def _ids(app):
    with app.app_context():
        return {
            "admin": User.query.filter_by(username="admin").first().id,
            "worker": User.query.filter_by(username="worker").first().id,
            "family": User.query.filter_by(username="family").first().id,
            "elder": Elder.query.first().id,
        }


def test_all_languages_have_identical_translation_keys():
    assert {"zh", "id", "vi", "fil", "th"} <= set(LANGUAGES)
    reference = set(T["zh"])
    assert all(set(payload) == reference for payload in T.values())


def test_language_switch_supports_thai(client):
    response = client.get("/lang/th")
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["lang"] == "th"


def test_new_elder_birthday_defaults_to_1940(app, client):
    ids = _ids(app)
    login_as(client, ids["admin"])
    response = client.post(
        "/admin/elders",
        data={"name": "Default Birthday", "water_goal": "1200", "notes": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        elder = Elder.query.filter_by(name="Default Birthday").first()
        assert elder is not None
        assert elder.birthday == date(1940, 1, 1)


def test_admin_can_delete_account_and_keep_historical_records(app, client):
    ids = _ids(app)
    with app.app_context():
        target = User(username="old-worker", name="Old Worker", role="worker", pin="9999")
        db.session.add(target)
        db.session.flush()
        record = MealRecord(
            elder_id=ids["elder"],
            record_date=date.today(),
            timeslot="morning",
            intake="all",
            created_by=target.id,
        )
        db.session.add(record)
        db.session.commit()
        target_id = target.id
        record_id = record.id

    login_as(client, ids["admin"])
    response = client.post(f"/admin/users/{target_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert "已刪除" in response.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(User, target_id) is None
        assert db.session.get(MealRecord, record_id).created_by is None
        deletion = AuditLog.query.filter_by(
            action="delete", record_type="user", record_id=target_id
        ).first()
        assert deletion is not None
        assert deletion.user_id == ids["admin"]


def test_admin_cannot_delete_current_account(app, client):
    ids = _ids(app)
    login_as(client, ids["admin"])
    response = client.post(f"/admin/users/{ids['admin']}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert "不能刪除目前登入中的管理者帳號" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(User, ids["admin"]) is not None


def test_worker_can_open_dashboard_and_persistent_navigation(app, client):
    ids = _ids(app)
    login_as(client, ids["worker"], "vi")

    care_page = client.get("/care/")
    assert care_page.status_code == 200
    care_html = care_page.get_data(as_text=True)
    assert "Bảng điều khiển" in care_html
    assert 'href="/family/"' in care_html

    dashboard = client.get(f"/family/?elder={ids['elder']}&days=7")
    assert dashboard.status_code == 200
    assert "Bảng xu hướng sức khỏe" in dashboard.get_data(as_text=True)

    data = client.get(f"/family/data?elder={ids['elder']}&days=7")
    assert data.status_code == 200
    payload = data.get_json()
    assert "vital_summary" in payload
    assert "water_summary" in payload


def test_report_contains_average_minimum_and_maximum(app):
    ids = _ids(app)
    start = date.today() - timedelta(days=2)
    end = date.today()
    with app.app_context():
        db.session.add_all(
            [
                VitalRecord(
                    elder_id=ids["elder"],
                    record_date=start,
                    recorded_at=datetime.combine(start, datetime.min.time()).replace(hour=8),
                    weight=50.0,
                    systolic=110,
                    diastolic=70,
                    pulse=60,
                    spo2=96,
                ),
                VitalRecord(
                    elder_id=ids["elder"],
                    record_date=end,
                    recorded_at=datetime.combine(end, datetime.min.time()).replace(hour=8),
                    weight=54.0,
                    systolic=150,
                    diastolic=90,
                    pulse=80,
                    spo2=99,
                ),
                WaterRecord(elder_id=ids["elder"], record_date=start, amount=500),
                WaterRecord(elder_id=ids["elder"], record_date=end, amount=1200),
            ]
        )
        db.session.commit()
        elder = db.session.get(Elder, ids["elder"])
        data = collect_period(elder, start, end)
        assert data["vital_stats"]["systolic"]["avg"] == 130.0
        assert data["vital_stats"]["systolic"]["min"] == 110
        assert data["vital_stats"]["systolic"]["max"] == 150
        assert data["water_avg"] == 850
        assert data["water_period_avg"] == 567
        assert data["water_min"] == 500
        assert data["water_max"] == 1200
        html = build_html(
            [data],
            "測試報表",
            items={"vitals": True, "meds": True, "meals": True, "water": True, "bowel": True},
        )
        assert "最低" in html
        assert "最高" in html
        assert "150 mmHg" in html


def test_abnormal_vital_warning_uses_caregiver_language(app):
    ids = _ids(app)
    with app.app_context():
        elder = db.session.get(Elder, ids["elder"])
        vital = VitalRecord(
            elder_id=elder.id,
            record_date=date.today(),
            recorded_at=datetime.now(),
            systolic=170,
        )
        warnings = check_and_alert(elder, vital, lang="vi")
        assert len(warnings) == 1
        assert "Tâm thu" in warnings[0]
        assert "ngưỡng cảnh báo" in warnings[0]



def test_csrf_protection_rejects_missing_token_and_accepts_valid_token(app, client):
    ids = _ids(app)
    app.config["CSRF_ENABLED"] = True
    login_as(client, ids["admin"])

    rejected = client.post(
        "/admin/elders",
        data={"name": "No Token", "water_goal": "1200", "notes": ""},
    )
    assert rejected.status_code == 400

    page = client.get("/admin/elders")
    match = re.search(r'name="_csrf_token" value="([^"]+)"', page.get_data(as_text=True))
    assert match is not None
    accepted = client.post(
        "/admin/elders",
        data={
            "_csrf_token": match.group(1),
            "name": "Valid Token",
            "water_goal": "1200",
            "notes": "",
        },
    )
    assert accepted.status_code == 302


def test_primary_pages_render_for_admin(app, client):
    ids = _ids(app)
    login_as(client, ids["admin"])
    urls = [
        "/admin/",
        "/admin/elders",
        "/admin/medplans",
        "/admin/users",
        "/admin/notify",
        "/admin/audit",
        "/care/",
        f"/family/?elder={ids['elder']}",
        f"/family/photos?elder={ids['elder']}",
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
        html = response.get_data(as_text=True)
        assert "後台" in html, url
        assert "儀表板" in html, url
        assert "填報" in html, url
