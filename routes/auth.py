from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import db, User
from translations import LANGUAGES, normalize_lang, tr
from utils import get_lang

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    lang = get_lang()
    workers = User.query.filter_by(role="worker", active=True).order_by(User.name).all()

    if request.method == "POST":
        mode = request.form.get("mode")
        user = None
        if mode == "worker":
            uid = request.form.get("worker_id", type=int)
            pin = (request.form.get("pin") or "").strip()
            candidate = db.session.get(User, uid) if uid else None
            if (
                candidate
                and candidate.role == "worker"
                and candidate.active
                and candidate.pin
                and candidate.pin == pin
            ):
                user = candidate
        else:
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            candidate = User.query.filter_by(username=username, active=True).first()
            if (
                candidate
                and candidate.role in ("admin", "family")
                and candidate.check_password(password)
            ):
                user = candidate
        if user:
            session.clear()
            session["user_id"] = user.id
            session["lang"] = normalize_lang(user.lang)
            session.permanent = True
            if user.role == "worker":
                return redirect(url_for("front.home"))
            if user.role == "family":
                return redirect(url_for("family.dashboard"))
            return redirect(url_for("admin.index"))
        flash(tr(lang, "login_failed"), "error")

    return render_template("auth/login.html", workers=workers, lang=lang, languages=LANGUAGES)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/lang/<code>")
def switch_lang(code):
    code = normalize_lang(code)
    if code in LANGUAGES:
        session["lang"] = code
        uid = session.get("user_id")
        if uid:
            user = db.session.get(User, uid)
            if user:
                user.lang = code
                db.session.commit()
    return redirect(request.referrer or url_for("auth.login"))
