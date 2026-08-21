"""Small security helpers that avoid adding a form-library dependency."""

from __future__ import annotations

import hmac
import secrets

from flask import abort, current_app, request, session

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def csrf_token() -> str:
    """Return the current session's CSRF token, creating it when needed."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf() -> None:
    """Reject unsafe requests that do not carry the session CSRF token."""
    if not current_app.config.get("CSRF_ENABLED", True):
        return
    if request.method in _SAFE_METHODS:
        return

    expected = session.get("_csrf_token")
    supplied = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
    if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
        abort(400, description="CSRF token validation failed")
