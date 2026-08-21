import os
from datetime import timedelta

import click
from flask import Flask, redirect, url_for

from config import Config
from models import db, User, Elder, MedPlan
from security import csrf_token, validate_csrf
from translations import LANGUAGES, normalize_lang, tr, tr_format
from utils import current_user, get_lang


def create_app(test_config=None):
    """Application factory used by Flask CLI, Waitress, tests, and ``python app.py``."""
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    app.permanent_session_lifetime = timedelta(days=14)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    db.init_app(app)
    app.before_request(validate_csrf)

    # Lightweight compatibility migration for databases created by older releases.
    # SQLite create_all() creates missing tables but does not add columns to existing tables.
    with app.app_context():
        try:
            from sqlalchemy import inspect, text

            if inspect(db.engine).has_table("meal_records"):
                cols = [
                    row[1]
                    for row in db.session.execute(text("PRAGMA table_info(meal_records)"))
                ]
                if "supplement" not in cols:
                    db.session.execute(
                        text("ALTER TABLE meal_records ADD COLUMN supplement BOOLEAN")
                    )
                    db.session.execute(
                        text("ALTER TABLE meal_records ADD COLUMN supplement_cc INTEGER")
                    )
                    db.session.commit()
        except Exception as exc:
            app.logger.warning("auto-migrate skipped: %s", exc)

    from routes.auth import bp as auth_bp
    from routes.front import bp as front_bp
    from routes.family import bp as family_bp
    from routes.admin import bp as admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(front_bp)
    app.register_blueprint(family_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_ui_globals():
        lang = normalize_lang(get_lang())
        return {
            "user": current_user(),
            "lang": lang,
            "languages": LANGUAGES,
            "lang_info": LANGUAGES[lang],
            "t": lambda key: tr(lang, key),
            "tf": lambda key, **values: tr_format(lang, key, **values),
            "csrf_token": csrf_token,
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


def _start_scheduler(app):
    """Start one scheduler for this application instance."""
    if "carelog_scheduler" in app.extensions:
        return

    # Avoid a duplicate scheduler in the Flask development reloader parent process.
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
        except Exception as exc:  # Scheduler failure must not stop the website.
            app.logger.warning("Scheduler not started: %s", exc)


def _register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """建立資料表與預設管理者帳號 (admin / care1234)。"""
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            user = User(username="admin", name="系統管理者", role="admin")
            user.set_password("care1234")
            db.session.add(user)
            db.session.commit()
            click.echo("已建立管理者帳號 admin / care1234（請登入後盡快修改密碼）")
        click.echo("資料庫初始化完成。")

    @app.cli.command("seed-demo")
    def seed_demo():
        """建立示範資料：長輩、照顧者、家屬、用藥計畫。"""
        db.create_all()
        if not Elder.query.first():
            elder = Elder(name="王奶奶", notes="高血壓、糖尿病", water_goal=1500)
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
            db.session.add(
                User(username="siti", name="Siti", role="worker", pin="1234", lang="id")
            )
        if not User.query.filter_by(username="family").first():
            family = User(username="family", name="王小明（家屬）", role="family")
            family.set_password("family1234")
            db.session.add(family)
        db.session.commit()
        click.echo("示範資料建立完成：照顧者 Siti（PIN 1234）、家屬 family / family1234")


if __name__ == "__main__":
    application = create_app()
    port = int(os.environ.get("CARELOG_PORT", 8500))
    application.run(host="0.0.0.0", port=port, debug=False)
