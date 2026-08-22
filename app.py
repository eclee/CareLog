import os
from datetime import date, datetime, timedelta

import click
from flask import Flask, redirect, url_for
from sqlalchemy.exc import OperationalError

from config import Config
from models import (
    AbnormalEvent,
    BowelRecord,
    Elder,
    MealRecord,
    MedPlan,
    MedRecord,
    User,
    VitalRecord,
    db,
    get_care_parameters,
)
from security import csrf_token, validate_csrf
from translations import LANGUAGES, normalize_lang, tr, tr_format
from utils import current_user, get_lang


def create_app(test_config=None):
    """Application factory used by Flask CLI, Waitress, tests and python app.py."""

    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    app.permanent_session_lifetime = timedelta(days=14)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    db.init_app(app)
    app.before_request(validate_csrf)

    # Existing databases are upgraded before route code starts querying new columns.
    with app.app_context():
        try:
            from services.schema import ensure_schema_compatibility

            ensure_schema_compatibility(create_missing=True)
        except Exception:
            db.session.rollback()
            app.logger.exception("CareLog database compatibility migration failed")
            raise

    from routes.admin import bp as admin_bp
    from routes.auth import bp as auth_bp
    from routes.family import bp as family_bp
    from routes.front import bp as front_bp
    from routes.media import bp as media_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(front_bp)
    app.register_blueprint(family_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(media_bp)
    _register_database_error_handlers(app)

    @app.context_processor
    def inject_ui_globals():
        lang = normalize_lang(get_lang())
        user = current_user()
        pending_abnormal_count = 0
        if user and user.role == "admin":
            try:
                pending_abnormal_count = AbnormalEvent.query.filter(
                    AbnormalEvent.status.in_(("pending", "tracking"))
                ).count()
            except Exception:
                db.session.rollback()
        return {
            "user": user,
            "lang": lang,
            "languages": LANGUAGES,
            "lang_info": LANGUAGES[lang],
            "t": lambda key: tr(lang, key),
            "tf": lambda key, **values: tr_format(lang, key, **values),
            "csrf_token": csrf_token,
            "pending_abnormal_count": pending_abnormal_count,
        }

    @app.route("/")
    def root():
        user = current_user()
        if user is None:
            return redirect(url_for("auth.login"))
        if user.role == "worker":
            return redirect(url_for("front.home"))
        if user.role == "family":
            return redirect(url_for("family.dashboard"))
        return redirect(url_for("admin.index"))

    _register_cli(app)
    if app.config.get("START_SCHEDULER", True):
        _start_scheduler(app)
    return app


def _database_target_for_display(uri):
    """Return an operator-useful target without exposing future DB credentials."""

    value = str(uri or "")
    if value.startswith("sqlite:///"):
        return value.removeprefix("sqlite:///")
    if "://" in value:
        return value.split("://", 1)[0] + "://[hidden]"
    return value or "未設定"


def _register_database_error_handlers(app):
    """Translate legacy/partial SQLite schema failures into an actionable page."""

    @app.errorhandler(OperationalError)
    def handle_operational_error(exc):
        db.session.rollback()
        raw = str(getattr(exc, "orig", exc))
        lowered = raw.lower()
        schema_failure = any(
            marker in lowered
            for marker in (
                "no such table",
                "no such column",
                "has no column named",
                "database schema has changed",
            )
        )
        if schema_failure:
            try:
                from services.schema import schema_health, schema_health_message

                report = schema_health()
                diagnosis = schema_health_message(report)
            except Exception as health_exc:  # keep the diagnostic page renderable
                report = {"ok": False, "missing_tables": [], "missing_columns": {}}
                diagnosis = f"無法完成結構健檢：{health_exc}"
            app.logger.exception(
                "Database schema mismatch at request time; database=%s; diagnosis=%s",
                app.config.get("SQLALCHEMY_DATABASE_URI"),
                diagnosis,
            )
            template = app.jinja_env.get_template("errors/database_upgrade.html")
            return (
                template.render(
                    diagnosis=diagnosis,
                    database_error=raw,
                    report=report,
                    database_target=_database_target_for_display(
                        app.config.get("SQLALCHEMY_DATABASE_URI")
                    ),
                ),
                503,
                {"Content-Type": "text/html; charset=utf-8"},
            )

        app.logger.exception(
            "Database operational error; database=%s",
            app.config.get("SQLALCHEMY_DATABASE_URI"),
        )
        template = app.jinja_env.get_template("errors/database_unavailable.html")
        return (
            template.render(database_error=raw),
            503,
            {"Content-Type": "text/html; charset=utf-8"},
        )


def _start_scheduler(app):
    """Start one scheduler for this application instance."""

    if "carelog_scheduler" in app.extensions:
        return
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from services.scheduler_jobs import run_scheduled_tasks

            scheduler = BackgroundScheduler(daemon=True)
            scheduler.add_job(
                run_scheduled_tasks,
                "interval",
                minutes=1,
                args=[app],
                max_instances=1,
                coalesce=True,
            )
            scheduler.start()
            app.extensions["carelog_scheduler"] = scheduler
        except Exception as exc:
            app.logger.warning("Scheduler not started: %s", exc)


def _register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create tables, upgrade existing tables and create the default admin."""

        from services.schema import ensure_schema_compatibility

        db.create_all()
        actions = ensure_schema_compatibility(create_missing=True)
        if not User.query.filter_by(username="admin").first():
            user = User(
                username="admin",
                name="系統管理者",
                role="admin",
                pin="1234",
            )
            user.set_password("care1234")
            db.session.add(user)
            db.session.commit()
            click.echo(
                "已建立管理者帳號 admin / care1234，PIN 1234"
                "（請登入後立即修改密碼與 PIN）"
            )
        incomplete_accounts = [
            account.username
            for account in User.query.filter(
                User.active.is_(True), User.deleted_at.is_(None)
            ).all()
            if not account.pin or not account.password_hash
        ]
        if incomplete_accounts:
            click.echo(
                "注意：下列既有帳號尚未同時具備 PIN 與密碼，請至使用者管理補齊："
                + ", ".join(incomplete_accounts)
            )
        if actions:
            click.echo("資料庫已升級：" + ", ".join(actions))
        click.echo("資料庫初始化完成。")

    @app.cli.command("upgrade-db")
    def upgrade_db():
        """Upgrade an existing CareLog database in place."""

        from services.schema import ensure_schema_compatibility

        actions = ensure_schema_compatibility(create_missing=True)
        click.echo("資料庫升級完成。" if actions else "資料庫結構已是最新版本。")
        for action in actions:
            click.echo(f"- {action}")

    @app.cli.command("check-db")
    def check_db():
        """Validate that the configured database matches this CareLog release."""

        from services.schema import schema_health, schema_health_message

        report = schema_health()
        click.echo(f"資料庫：{app.config.get('SQLALCHEMY_DATABASE_URI')}")
        click.echo(f"目標結構版本：{report['current_version']}")
        click.echo(schema_health_message(report))
        if not report["ok"]:
            raise click.ClickException(
                "資料庫尚未完成升級；請先執行 CARELOG_START_SCHEDULER=0 "
                "flask --app app upgrade-db"
            )
        click.echo("資料庫結構檢查通過。")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Create a sample elder, caregiver, family account and medication plans."""

        from services.schema import ensure_schema_compatibility

        db.create_all()
        ensure_schema_compatibility(create_missing=True)
        params = get_care_parameters()
        birthday = datetime.strptime(
            params.get("default_elder_birthday", "1940-01-01"), "%Y-%m-%d"
        ).date()
        if not Elder.query.first():
            elder = Elder(
                name="王奶奶",
                birthday=birthday,
                notes="高血壓、糖尿病",
                water_goal=int(params.get("default_water_goal_ml", 1500)),
            )
            db.session.add(elder)
            db.session.flush()
            db.session.add_all(
                [
                    MedPlan(
                        elder_id=elder.id,
                        name="降血壓藥 Amlodipine 5mg",
                        timeslot="morning",
                        meal_relation="after",
                        dose_note="1 顆",
                    ),
                    MedPlan(
                        elder_id=elder.id,
                        name="血糖藥 Metformin 500mg",
                        timeslot="morning",
                        meal_relation="before",
                        dose_note="1 顆",
                    ),
                    MedPlan(
                        elder_id=elder.id,
                        name="血糖藥 Metformin 500mg",
                        timeslot="evening",
                        meal_relation="before",
                        dose_note="1 顆",
                    ),
                    MedPlan(
                        elder_id=elder.id,
                        name="安眠藥 Zolpidem 5mg",
                        timeslot="bedtime",
                        meal_relation="none",
                        dose_note="半顆",
                    ),
                ]
            )
        if not User.query.filter_by(username="siti").first():
            worker = User(
                username="siti",
                name="Siti",
                role="worker",
                pin="1234",
                lang="id",
            )
            worker.set_password("worker1234")
            db.session.add(worker)
        if not User.query.filter_by(username="family").first():
            family = User(
                username="family",
                name="王小明（家屬）",
                role="family",
                pin="5678",
            )
            family.set_password("family1234")
            db.session.add(family)
        db.session.commit()
        click.echo(
            "示範資料建立完成：照顧者 Siti（PIN 1234 / 密碼 worker1234）、"
            "家屬 family（PIN 5678 / 密碼 family1234）"
        )

    @app.cli.command("media-migrate")
    @click.option("--dry-run/--apply", default=True, help="Preview or apply legacy moves.")
    def media_migrate(dry_run):
        """Move legacy photos into the structured CareLog media layout."""

        from services.media import migrate_legacy_photos

        summary = migrate_legacy_photos(dry_run=dry_run)
        click.echo("預覽結果：" if dry_run else "搬移結果：")
        for key, value in summary.items():
            click.echo(f"- {key}: {value}")
        if dry_run:
            click.echo("確認結果後，執行 flask --app app media-migrate --apply")

    @app.cli.command("rebuild-abnormal-events")
    @click.option("--from-date", "from_date", type=click.DateTime(formats=["%Y-%m-%d"]))
    @click.option("--to-date", "to_date", type=click.DateTime(formats=["%Y-%m-%d"]))
    def rebuild_abnormal_events(from_date, to_date):
        """Re-evaluate historical records using the current abnormal rules."""

        from services.abnormal import (
            evaluate_bowel,
            evaluate_meal,
            evaluate_med_records,
            evaluate_vital,
        )

        start = from_date.date() if from_date else date.min
        end = to_date.date() if to_date else date.max
        counts = {"vital": 0, "meal": 0, "bowel": 0, "med": 0}
        for record in VitalRecord.query.filter(
            VitalRecord.record_date >= start, VitalRecord.record_date <= end
        ).yield_per(100):
            elder = db.session.get(Elder, record.elder_id)
            if elder:
                evaluate_vital(elder, record, send_notification=False)
                counts["vital"] += 1
        for record in MealRecord.query.filter(
            MealRecord.record_date >= start, MealRecord.record_date <= end
        ).yield_per(100):
            evaluate_meal(record)
            counts["meal"] += 1
        for record in BowelRecord.query.filter(
            BowelRecord.record_date >= start, BowelRecord.record_date <= end
        ).yield_per(100):
            evaluate_bowel(record)
            counts["bowel"] += 1
        for record in MedRecord.query.filter(
            MedRecord.record_date >= start, MedRecord.record_date <= end
        ).yield_per(100):
            evaluate_med_records([record])
            counts["med"] += 1
        click.echo("歷史異常重建完成：")
        for key, value in counts.items():
            click.echo(f"- {key}: {value}")


if __name__ == "__main__":
    application = create_app()
    port = int(os.environ.get("CARELOG_PORT", 8500))
    application.run(host="0.0.0.0", port=port, debug=False)
