"""Persistent, reverse-proxy-safe login attempt limits.

Only request.remote_addr is trusted; forwarded headers require separately
configured trusted proxy handling. Keys are hashed to avoid storing identities.
"""

from datetime import datetime, timedelta
from hashlib import sha256

from flask import request

from models import LoginAttempt, db


def _keys(mode, identity):
    ip = request.remote_addr or "unknown"
    key = f"{mode}:{identity.strip().lower()}:{ip}"
    return sha256(key.encode()).hexdigest(), sha256(ip.encode()).hexdigest()


def blocked(mode, identity):
    identity_key, ip_key = _keys(mode, identity)
    since = datetime.now() - timedelta(minutes=15)
    personal = LoginAttempt.query.filter(
        LoginAttempt.identity_key == identity_key, LoginAttempt.created_at >= since
    ).count()
    network = LoginAttempt.query.filter(
        LoginAttempt.ip_key == ip_key, LoginAttempt.created_at >= since
    ).count()
    return personal >= 5 or network >= 30


def record_failure(mode, identity):
    identity_key, ip_key = _keys(mode, identity)
    LoginAttempt.query.filter(
        LoginAttempt.created_at < datetime.now() - timedelta(days=30)
    ).delete(synchronize_session=False)
    db.session.add(LoginAttempt(identity_key=identity_key, ip_key=ip_key))
    db.session.commit()
