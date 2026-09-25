from functools import wraps

from flask import abort, redirect, request, session, url_for

from models import Elder, User, UserElderAccess, db
from services.media import photos_for, save_images
from translations import normalize_lang


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = db.session.get(User, user_id)
    if user is None or not user.active or user.deleted_at is not None:
        session.clear()
        return None
    return user


def login_required(*roles):
    """@login_required() accepts any logged-in user; pass roles to restrict access."""

    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return redirect(url_for("auth.login", next=request.path))
            if roles and user.role not in roles:
                abort(403)
            return function(*args, **kwargs)

        return wrapper

    return decorator


def get_lang():
    """Return the active interface language.

    After login, the account's saved language is authoritative. This avoids a
    stale browser session overriding a caregiver's configured default language.
    The language switch route updates both the account and the session, so the
    selected language remains persistent.
    """

    user_id = session.get("user_id")
    if user_id:
        user = db.session.get(User, user_id)
        if user is not None and user.active and user.deleted_at is None:
            language = normalize_lang(user.lang)
            if session.get("lang") != language:
                session["lang"] = language
            return language
    return normalize_lang(session.get("lang", "zh"))


def active_elders():
    user = current_user()
    query = Elder.query.filter_by(active=True)
    if user is None:
        return []
    if user.role != "admin":
        query = query.join(UserElderAccess, UserElderAccess.elder_id == Elder.id).filter(
            UserElderAccess.user_id == user.id
        )
    return query.order_by(Elder.id).all()


def can_access_elder(elder_id):
    user = current_user()
    if user is None or elder_id is None:
        return False
    if user.role == "admin":
        return Elder.query.filter_by(id=elder_id, active=True).first() is not None
    return db.session.query(UserElderAccess.user_id).join(Elder).filter(
        UserElderAccess.user_id == user.id,
        UserElderAccess.elder_id == elder_id,
        Elder.active.is_(True),
    ).first() is not None


def current_elder():
    elders = active_elders()
    if not elders:
        return None
    elder_id = session.get("elder_id")
    for elder in elders:
        if elder.id == elder_id:
            return elder
    session["elder_id"] = elders[0].id
    return elders[0]


# Compatibility exports for extensions written against CareLog 1.1.
def save_photos(files, record_type, record_id, elder_id):
    result = save_images(
        files,
        kind="care_evidence",
        record_type=record_type,
        record_id=record_id,
        elder_id=elder_id,
        uploaded_by=session.get("user_id"),
    )
    db.session.commit()
    return result.saved_count


__all__ = [
    "active_elders",
    "current_elder",
    "can_access_elder",
    "current_user",
    "get_lang",
    "login_required",
    "photos_for",
    "save_photos",
]
