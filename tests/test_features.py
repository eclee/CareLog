from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
import re

from PIL import Image

from models import (
    AbnormalEvent,
    AuditLog,
    Elder,
    MealRecord,
    MedPlan,
    Photo,
    Setting,
    User,
    VitalRecord,
    WaterRecord,
    db,
    get_care_parameters,
    log_action,
)
from services.reports import build_html, collect_period
from services.schema import ensure_schema_compatibility
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


def _image_file(filename: str = "sample.png", *, size=(720, 480), fmt="PNG"):
    stream = BytesIO()
    Image.new("RGB", size, (240, 235, 220)).save(stream, format=fmt)
    stream.seek(0)
    return stream, filename


def _parameter_form(**overrides):
    data = {
        "water_quick_1": "100",
        "water_quick_2": "250",
        "water_quick_3": "500",
        "water_entry_min_ml": "10",
        "water_entry_max_ml": "2000",
        "default_elder_birthday": "1940-01-01",
        "default_water_goal_ml": "1500",
        "dashboard_default_days": "30",
        "max_care_photos_per_record": "5",
        "max_medication_photos_per_plan": "3",
        "vitals_enabled": "on",
        "sys_hi": "160",
        "sys_lo": "90",
        "dia_hi": "100",
        "dia_lo": "55",
        "pulse_hi": "110",
        "pulse_lo": "45",
        "spo2_lo": "92",
        "med_not_given_enabled": "on",
        "bowel_enabled": "on",
        "bowel_types": ["1", "2", "6", "7"],
        "meal_none_enabled": "on",
        "water_close_time": "22:00",
        "water_min_percent": "100",
    }
    data.update(overrides)
    return data


def test_all_languages_have_identical_translation_keys():
    assert {"zh", "id", "vi", "fil", "th"} <= set(LANGUAGES)
    reference = set(T["zh"])
    assert all(set(payload) == reference for payload in T.values())


def test_language_switch_supports_thai(client):
    response = client.get("/lang/th")
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["lang"] == "th"


def test_parameters_change_water_buttons_and_new_elder_defaults(app, client):
    ids = _ids(app)
    login_as(client, ids["admin"])
    response = client.post(
        "/admin/parameters",
        data=_parameter_form(
            water_quick_1="150",
            water_quick_2="300",
            water_quick_3="600",
            default_elder_birthday="1935-02-03",
            default_water_goal_ml="1800",
            dashboard_default_days="14",
        ),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "參數設定已儲存" in response.get_data(as_text=True)

    with app.app_context():
        parameters = get_care_parameters()
        assert parameters["water_quick_amounts_ml"] == [150, 300, 600]
        assert parameters["default_elder_birthday"] == "1935-02-03"
        assert parameters["default_water_goal_ml"] == 1800
        assert parameters["dashboard_default_days"] == 14
        assert db.session.get(Setting, "care_parameters") is not None

    water_page = client.get("/care/water")
    water_html = water_page.get_data(as_text=True)
    assert water_page.status_code == 200
    assert 'value="150"' in water_html and "+150" in water_html
    assert 'value="300"' in water_html and "+300" in water_html
    assert 'value="600"' in water_html and "+600" in water_html

    created = client.post(
        "/admin/elders",
        data={"name": "Config Default Elder", "notes": ""},
        follow_redirects=True,
    )
    assert created.status_code == 200
    with app.app_context():
        elder = Elder.query.filter_by(name="Config Default Elder").first()
        assert elder is not None
        assert elder.birthday == date(1935, 2, 3)
        assert elder.water_goal == 1800


def test_parameter_validation_rejects_duplicate_water_buttons(app, client):
    ids = _ids(app)
    login_as(client, ids["admin"])
    response = client.post(
        "/admin/parameters",
        data=_parameter_form(
            water_quick_1="250",
            water_quick_2="250",
            water_quick_3="500",
        ),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "喝水快捷值不可重複" in response.get_data(as_text=True)


def test_admin_soft_deletes_account_and_preserves_identity_and_records(app, client):
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
    assert "已停用刪除" in response.get_data(as_text=True)

    with app.app_context():
        target = db.session.get(User, target_id)
        assert target is not None
        assert target.active is False
        assert target.deleted_at is not None
        assert target.pin is None
        assert db.session.get(MealRecord, record_id).created_by == target_id
        deletion = AuditLog.query.filter_by(
            action="delete", record_type="user", record_id=target_id
        ).first()
        assert deletion is not None
        assert deletion.user_id == ids["admin"]
        assert deletion.actor_username == "admin"
        assert deletion.actor_role == "admin"

    login_page = client.get("/login")
    assert "Old Worker" not in login_page.get_data(as_text=True)


def test_admin_cannot_delete_current_account(app, client):
    ids = _ids(app)
    login_as(client, ids["admin"])
    response = client.post(f"/admin/users/{ids['admin']}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert "不能刪除目前登入中的管理者帳號" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(User, ids["admin"]).deleted_at is None


def test_user_management_has_scoped_compact_typography(app, client):
    ids = _ids(app)
    login_as(client, ids["admin"])
    response = client.get("/admin/users")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "users-management-page" in html
    stylesheet = Path(app.root_path, "static", "style.css").read_text(encoding="utf-8")
    assert ".users-management-page" in stylesheet
    assert "font-size: 14px" in stylesheet
    assert "font-size: 13px" in stylesheet


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


def test_medication_reference_photo_is_structured_and_visible_to_caregiver(app, client):
    ids = _ids(app)
    login_as(client, ids["admin"])
    response = client.post(
        "/admin/medplans",
        data={
            "elder_id": str(ids["elder"]),
            "name": "Photo Medicine 10mg",
            "timeslot": "morning",
            "meal_relation": "after",
            "dose_note": "1 顆",
            "photo_upload": _image_file("medicine.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "用藥計畫已新增" in response.get_data(as_text=True)

    with app.app_context():
        plan = MedPlan.query.filter_by(name="Photo Medicine 10mg").first()
        assert plan is not None
        photo = Photo.query.filter_by(
            kind="med_reference", record_type="medplan", record_id=plan.id
        ).first()
        assert photo is not None
        assert photo.is_primary is True
        assert photo.filename.startswith(
            f"elders/elder-{ids['elder']:06d}/medication-plans/plan-{plan.id:06d}/reference/"
        )
        assert photo.filename.endswith(".jpg")
        assert photo.thumbnail_filename.endswith("_thumb.jpg")
        assert len(photo.checksum) == 64
        assert Path(app.config["UPLOAD_DIR"], photo.filename).is_file()
        assert Path(app.config["UPLOAD_DIR"], photo.thumbnail_filename).is_file()
        plan_id = plan.id
        photo_id = photo.id

    login_as(client, ids["worker"], "zh")
    page = client.get("/care/med/morning/after")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Photo Medicine 10mg" in html
    assert "1 顆" in html
    assert f"/media/photos/{photo_id}/thumbnail" in html

    image_response = client.get(f"/media/photos/{photo_id}")
    assert image_response.status_code == 200
    assert image_response.headers["Cache-Control"] == "private, no-store"
    assert image_response.headers["X-Content-Type-Options"] == "nosniff"
    assert image_response.mimetype == "image/jpeg"

    with app.app_context():
        assert db.session.get(MedPlan, plan_id) is not None


def test_vital_photo_creates_structured_media_and_persistent_abnormal_event(app, client):
    ids = _ids(app)
    login_as(client, ids["worker"], "zh")
    response = client.post(
        "/care/vitals",
        data={
            "systolic": "181",
            "diastolic": "101",
            "pulse": "80",
            "spo2": "97",
            "note": "recheck requested",
            "photos": _image_file("vital-proof.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "已儲存" in response.get_data(as_text=True)

    with app.app_context():
        vital = VitalRecord.query.order_by(VitalRecord.id.desc()).first()
        assert vital is not None
        photo = Photo.query.filter_by(
            record_type="vital", record_id=vital.id, kind="care_evidence"
        ).first()
        assert photo is not None
        assert "/care-records/" in f"/{photo.filename}"
        assert f"/vital/record-{vital.id:06d}/" in f"/{photo.filename}"
        events = AbnormalEvent.query.filter_by(
            source_type="vital", source_id=vital.id
        ).order_by(AbnormalEvent.event_type).all()
        assert {event.event_type for event in events} == {
            "diastolic_high",
            "systolic_high",
        }
        assert all(photo in event.photos for event in events)
        assert all(event.threshold_value is not None for event in events)
        assert all(event.notification_status == "mail_not_configured" for event in events)
        event_id = next(
            event.id for event in events if event.event_type == "systolic_high"
        )
        vital_id = vital.id
        photo_id = photo.id

    login_as(client, ids["admin"])
    today = date.today().isoformat()
    abnormal_page = client.get(
        f"/admin/abnormal?event_type=systolic_high&date={today}&photo=yes"
    )
    abnormal_html = abnormal_page.get_data(as_text=True)
    assert abnormal_page.status_code == 200
    assert f'href="/admin/abnormal/{event_id}"' in abnormal_html
    assert "收縮壓偏高" in abnormal_html
    assert "181" in abnormal_html

    detail = client.get(f"/admin/abnormal/{event_id}")
    detail_html = detail.get_data(as_text=True)
    assert detail.status_code == 200
    assert f"#A{event_id:06d}" in detail_html
    assert f"/media/photos/{photo_id}/thumbnail" in detail_html

    update = client.post(
        f"/admin/abnormal/{event_id}/status",
        data={"status": "tracking", "handling_note": "已通知家屬並重新量測"},
        follow_redirects=True,
    )
    assert update.status_code == 200
    assert "追蹤中" in update.get_data(as_text=True)
    with app.app_context():
        event = db.session.get(AbnormalEvent, event_id)
        assert event.status == "tracking"
        assert event.acknowledged_by == ids["admin"]
        assert "重新量測" in event.handling_note

    library = client.get(
        f"/admin/photos?type=vital&record_id={vital_id}&date={today}&abnormal=1"
    )
    library_html = library.get_data(as_text=True)
    assert library.status_code == 200
    assert f"P{photo_id:06d}" in library_html
    assert "健康數據" in library_html


def test_audit_filters_by_user_type_and_date(app, client):
    ids = _ids(app)
    with app.app_context():
        log_action(
            ids["worker"],
            "create",
            "vital",
            901,
            "worker-filter-marker",
            elder_id=ids["elder"],
            event_code="vital.test",
        )
        log_action(
            ids["admin"],
            "update",
            "parameter",
            0,
            "admin-hidden-marker",
            event_code="parameters.test",
        )
        db.session.commit()

    login_as(client, ids["admin"])
    today = date.today().isoformat()
    response = client.get(
        f"/admin/audit?user={ids['worker']}&role=worker&type=vital&date={today}"
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "worker-filter-marker" in html
    assert "admin-hidden-marker" not in html
    assert "共 1 筆，第" in html


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
            items={
                "vitals": True,
                "meds": True,
                "meals": True,
                "water": True,
                "bowel": True,
            },
        )
        assert "最低" in html
        assert "最高" in html
        assert "150 mmHg" in html


def test_schema_upgrade_is_idempotent(app):
    with app.app_context():
        first = ensure_schema_compatibility(create_missing=True)
        second = ensure_schema_compatibility(create_missing=True)
        assert isinstance(first, list)
        assert second == []


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
        "/admin/parameters",
        "/admin/notify",
        "/admin/audit",
        "/admin/photos",
        "/admin/abnormal",
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
