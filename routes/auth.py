from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import User, db, log_action
from translations import LANGUAGES, normalize_lang, tr
from utils import get_lang


bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    lang = get_lang()
    workers = (
        User.query.filter(
            User.role == "worker",
            User.active.is_(True),
            User.deleted_at.is_(None),
        )
        .order_by(User.name)
        .all()
    )

    if request.method == "POST":
        mode = request.form.get("mode")
        user = None
        attempted_identity = ""
        if mode == "worker":
            user_id = request.form.get("worker_id", type=int)
            pin = (request.form.get("pin") or "").strip()
            candidate = db.session.get(User, user_id) if user_id else None
            attempted_identity = candidate.username if candidate else f"worker:{user_id}"
            if (
                candidate
                and candidate.role == "worker"
                and candidate.active
                and candidate.deleted_at is None
                and candidate.pin
                and candidate.pin == pin
            ):
                user = candidate
        else:
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            attempted_identity = username
            candidate = User.query.filter_by(username=username, active=True).first()
            if (
                candidate
                and candidate.deleted_at is None
                and candidate.role in ("admin", "family")
                and candidate.check_password(password)
            ):
                user = candidate
        if user:
            log_action(
                user.id,
                "login",
                "auth",
                user.id,
                "login success",
                event_code="auth.login_success",
            )
            db.session.commit()
            session.clear()
            session["user_id"] = user.id
            session["lang"] = normalize_lang(user.lang)
            session.permanent = True
            if user.role == "worker":
                return redirect(url_for("front.home"))
            if user.role == "family":
                return redirect(url_for("family.dashboard"))
            return redirect(url_for("admin.index"))
        log_action(
            None,
            "login",
            "auth",
            0,
            f"login failed: {attempted_identity}",
            event_code="auth.login_failed",
            metadata={"mode": mode, "identity": attempted_identity},
        )
        db.session.commit()
        flash(tr(lang, "login_failed"), "error")

    return render_template(
        "auth/login.html", workers=workers, lang=lang, languages=LANGUAGES
    )


@bp.route("/logout")
def logout():
    user_id = session.get("user_id")
    if user_id:
        log_action(
            user_id,
            "logout",
            "auth",
            user_id,
            "logout",
            event_code="auth.logout",
        )
        db.session.commit()
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/lang/<code>")
def switch_lang(code):
    code = normalize_lang(code)
    if code in LANGUAGES:
        session["lang"] = code
        user_id = session.get("user_id")
        if user_id:
            user = db.session.get(User, user_id)
            if user and user.deleted_at is None:
                user.lang = code
                db.session.commit()
    return redirect(request.referrer or url_for("auth.login"))
