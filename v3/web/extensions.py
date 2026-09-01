"""Cross-cutting Flask extensions. Currently: CSRF protection.

Minimal, dependency-free CSRF (rule 6) so we don't pull flask-wtf just for this.
A per-session token is required on every state-changing request (POST/PUT/PATCH/
DELETE) either as form field `csrf_token` or header `X-CSRF-Token`.
"""

from __future__ import annotations

import hmac
import secrets

from flask import Flask, abort, request, session

_SESSION_KEY = "_csrf_token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_EXEMPT_ENDPOINTS = {"health.healthz", "auth.callback"}
_EXEMPT_PATHS = {"/auth/callback"}


def csrf_token() -> str:
    """Return (creating if needed) the current session's CSRF token."""
    token = session.get(_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_SESSION_KEY] = token
    return token


def _validate() -> None:
    if request.method in _SAFE_METHODS:
        return
    if (request.endpoint or "") in _EXEMPT_ENDPOINTS:
        return
    if request.path.rstrip("/") in _EXEMPT_PATHS:
        return
    expected = session.get(_SESSION_KEY)
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    if not expected or not sent or not hmac.compare_digest(str(expected), str(sent)):
        abort(400, description="Invalid or missing CSRF token")


def init_csrf(app: Flask) -> None:
    app.before_request(_validate)
    app.jinja_env.globals["csrf_token"] = csrf_token
