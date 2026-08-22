from functools import wraps

from flask import abort, redirect, request, session, url_for

from models import Elder, User, db
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
    return normalize_lang(session.get("lang", "zh"))


def active_elders():
    return Elder.query.filter_by(active=True).order_by(Elder.id).all()


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
    "current_user",
    "get_lang",
    "login_required",
    "photos_for",
    "save_photos",
]
