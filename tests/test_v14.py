from datetime import date, timedelta

from models import Elder, LoginAttempt, MedPlan, User, UserElderAccess, db
from services.reports import collect_period
from tests.conftest import login_as


def _ids(app):
    with app.app_context():
        return (User.query.filter_by(username="admin").one().id,
                User.query.filter_by(username="worker").one().id,
                Elder.query.first().id)


def test_two_decimal_weight_and_fluid_composition_in_custom_period(app, client):
    admin, _, elder = _ids(app)
    login_as(client, admin)
    today = date.today().isoformat()
    assert client.post("/care/vitals", data={"weight": "55.27"}).status_code == 302
    assert client.post("/care/vitals", data={"weight": "55.271"}).status_code == 302
    assert client.post("/care/meal/morning", data={"intake": "all", "supplement": "yes", "supplement_cc": "180"}).status_code == 302
    assert client.post("/care/water", data={"amount": "250"}).status_code == 302
    assert client.post("/care/bowel", data={"bristol_type": "4"}).status_code == 302
    assert client.post("/care/bowel", data={"bristol_type": "7"}).status_code == 302
    response = client.get(f"/family/data?elder={elder}&start={today}&end={today}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["vital_summary"]["weight"] == {"avg": 55.27, "min": 55.27, "max": 55.27, "count": 1}
    assert data["water_summary"]["avg"] == 430
    assert data["water_summary"]["water_ml"] == 250
    assert data["water_summary"]["supplement_ml"] == 180
    assert data["water"][0]["water"] == 250 and data["water"][0]["supplement"] == 180
    assert data["bowel_chart"][0]["types"] == [0, 0, 0, 1, 0, 0, 1]
    with app.app_context():
        elder_obj = db.session.get(Elder, elder)
        report = collect_period(elder_obj, date.today(), date.today())
        assert report["water_avg"] == 430 and report["water_plain_ml"] == 250
    page = client.get(f"/family/?elder={elder}&start={today}&end={today}")
    assert page.status_code == 200 and b'ch-bowel' in page.data
    invalid = client.get(f"/family/data?elder={elder}&start={today}&end=2020-01-01")
    assert invalid.status_code == 400


def test_unassigned_elder_is_invisible_to_worker_and_family_api(app, client):
    admin, worker, elder = _ids(app)
    with app.app_context():
        second = Elder(name="Private elder", water_goal=1500)
        db.session.add(second)
        db.session.commit()
        private_id = second.id
    login_as(client, worker)
    assert client.get(f"/family/data?elder={private_id}&days=7").status_code == 404
    assert client.get(f"/family/data?elder={elder}&days=7").status_code == 200
    client.get(f"/care/elder/{private_id}")
    with client.session_transaction() as session:
        assert session.get("elder_id") != private_id
    login_as(client, admin)
    with app.app_context():
        assert UserElderAccess.query.filter_by(user_id=worker, elder_id=private_id).first() is None


def test_login_limit_blocks_guessing_and_accepts_existing_pin(app, client):
    _, worker, _ = _ids(app)
    for _ in range(5):
        assert client.post("/login", data={"mode": "worker", "worker_id": worker, "pin": "0000"}).status_code == 200
    blocked = client.post("/login", data={"mode": "worker", "worker_id": worker, "pin": "1234"})
    assert blocked.status_code == 429
    with app.app_context():
        assert LoginAttempt.query.count() == 5
        user = db.session.get(User, worker)
        assert user.pin is None and user.check_pin("1234")


def test_password_limit_and_unknown_supplement_are_not_reported_as_zero(app, client):
    admin, _, elder = _ids(app)
    for _ in range(5):
        assert client.post("/login", data={"mode": "account", "username": "admin", "password": "wrong"}).status_code == 200
    assert client.post("/login", data={"mode": "account", "username": "admin", "password": "admin-password"}).status_code == 429
    login_as(client, admin)
    assert client.post("/care/meal/morning", data={"intake": "all", "supplement": "yes"}).status_code == 302
    today = date.today().isoformat()
    data = client.get(f"/family/data?elder={elder}&start={today}&end={today}").get_json()
    assert data["water_summary"]["unknown_supplements"] == 1
    assert data["water_summary"]["avg"] is None
    assert data["water"][0]["water"] is None


def test_custom_period_includes_endpoints_and_uses_weekly_buckets(app, client):
    admin, _, elder = _ids(app)
    with app.app_context():
        from models import WaterRecord
        db.session.add_all([
            WaterRecord(elder_id=elder, record_date=date.today() - timedelta(days=100), amount=100, created_by=admin),
            WaterRecord(elder_id=elder, record_date=date.today(), amount=200, created_by=admin),
        ])
        db.session.commit()
    login_as(client, admin)
    first = (date.today() - timedelta(days=100)).isoformat()
    last = date.today().isoformat()
    data = client.get(f"/family/data?elder={elder}&start={first}&end={last}").get_json()
    assert data["water_summary"]["water_ml"] == 300
    assert data["water_summary"]["recorded_days"] == 2
    assert data["period"] == {"start": first, "end": last}
    assert len(data["water"]) < 30


def test_plan_adherence_separates_missing_from_not_given(app, client):
    admin, worker, elder = _ids(app)
    login_as(client, admin)
    created = client.post("/admin/medplans", data={"elder_id": elder, "name": "Sample", "timeslot": "morning", "meal_relation": "after", "dose_note": "1"})
    assert created.status_code == 302
    today = date.today().isoformat()
    unreported = client.get(f"/family/data?elder={elder}&start={today}&end={today}").get_json()["plan_adherence"]
    assert (unreported["scheduled"], unreported["unreported"], unreported["not_given"]) == (1, 1, 0)
    with app.app_context():
        plan_id = MedPlan.query.filter_by(name="Sample").one().id
    login_as(client, worker)
    response = client.post("/care/med/morning/after", data={f"given_{plan_id}": "no", f"reason_{plan_id}": "not available"})
    assert response.status_code == 302
    reported = client.get(f"/family/data?elder={elder}&start={today}&end={today}").get_json()["plan_adherence"]
    assert (reported["unreported"], reported["not_given"], reported["given"]) == (0, 1, 0)
