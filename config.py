import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Docker deployment uses CARELOG_DATA=/data so the database and photos share one volume.
DATA_DIR = os.environ.get("CARELOG_DATA", BASE_DIR)


def _env_bool(name, default=True):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


class Config:
    SECRET_KEY = os.environ.get("CARELOG_SECRET", "change-me-in-production")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(DATA_DIR, "carelog.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
    FONT_PATH = os.path.join(BASE_DIR, "fonts", "NotoSansTC-Regular.ttf")
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32 MB per request
    PHOTO_MAX_WIDTH = 1280
    PHOTO_QUALITY = 82
    START_SCHEDULER = _env_bool("CARELOG_START_SCHEDULER", True)
    CSRF_ENABLED = _env_bool("CARELOG_CSRF_ENABLED", True)
