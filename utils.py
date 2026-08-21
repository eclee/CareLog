import os
import uuid
from datetime import date
from functools import wraps

from flask import abort, current_app, redirect, request, session, url_for
from PIL import Image, ImageOps

from models import db, User, Elder, Photo, log_action
from translations import normalize_lang


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    user = db.session.get(User, uid)
    if user is None or not user.active:
        session.clear()
        return None
    return user


def login_required(*roles):
    """@login_required() accepts any logged-in user; pass roles to restrict access."""

    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return redirect(url_for("auth.login", next=request.path))
            if roles and user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return deco


def get_lang():
    return normalize_lang(session.get("lang", "zh"))


def active_elders():
    return Elder.query.filter_by(active=True).order_by(Elder.id).all()


def current_elder():
    elders = active_elders()
    if not elders:
        return None
    eid = session.get("elder_id")
    for elder in elders:
        if elder.id == eid:
            return elder
    session["elder_id"] = elders[0].id
    return elders[0]


def save_photos(files, record_type, record_id, elder_id):
    """Compress and store uploaded photos; return the number successfully saved."""
    saved = 0
    day_dir = os.path.join(str(elder_id), date.today().isoformat())
    abs_dir = os.path.join(current_app.config["UPLOAD_DIR"], day_dir)
    os.makedirs(abs_dir, exist_ok=True)
    for uploaded in files:
        if not uploaded or not uploaded.filename:
            continue
        try:
            image = Image.open(uploaded.stream)
            image = ImageOps.exif_transpose(image)
            if image.mode != "RGB":
                image = image.convert("RGB")
            max_width = current_app.config["PHOTO_MAX_WIDTH"]
            if image.width > max_width:
                image.thumbnail((max_width, max_width * 4))
            filename = f"{record_type}_{uuid.uuid4().hex[:12]}.jpg"
            image.save(
                os.path.join(abs_dir, filename),
                "JPEG",
                quality=current_app.config["PHOTO_QUALITY"],
                optimize=True,
            )
            db.session.add(
                Photo(
                    record_type=record_type,
                    record_id=record_id,
                    elder_id=elder_id,
                    filename=os.path.join(day_dir, filename),
                )
            )
            saved += 1
        except Exception:
            current_app.logger.exception("Photo upload failed for %s", record_type)
    if saved:
        db.session.commit()
        log_action(
            session.get("user_id"),
            "create",
            "photo",
            record_id,
            f"{record_type} +{saved} photo(s)",
        )
        db.session.commit()
    return saved


def photos_for(record_type, record_id):
    return Photo.query.filter_by(record_type=record_type, record_id=record_id).all()
