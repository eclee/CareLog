from flask import Blueprint, abort, send_file

from models import Elder, Photo, db
from services.media import file_path
from utils import can_access_elder, current_user, login_required


bp = Blueprint("media", __name__, url_prefix="/media")


def _authorised_photo(photo_id: int) -> Photo:
    photo = db.session.get(Photo, photo_id)
    if photo is None or photo.deleted_at is not None:
        abort(404)
    user = current_user()
    if user is None:
        abort(401)
    if user.role != "admin" and not can_access_elder(photo.elder_id):
        abort(404)
    return photo


@bp.route("/photos/<int:photo_id>")
@login_required()
def photo_file(photo_id):
    photo = _authorised_photo(photo_id)
    path = file_path(photo)
    if not path.exists():
        abort(404)
    response = send_file(
        path,
        mimetype=photo.mime_type or "image/jpeg",
        conditional=True,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.route("/photos/<int:photo_id>/thumbnail")
@login_required()
def photo_thumbnail(photo_id):
    photo = _authorised_photo(photo_id)
    path = file_path(photo, thumbnail=True)
    if not path.exists():
        path = file_path(photo)
    if not path.exists():
        abort(404)
    response = send_file(path, mimetype="image/jpeg", conditional=True)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
