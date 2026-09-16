"""Stops other sites from making your browser submit our forms (CSRF)."""

# === What's in this file ===
# Every request that changes something (POST/PUT/PATCH/DELETE) must carry a
# secret token that only our own pages know. A form on another site can make
# your browser send a request to us, but it can't read this token, so the
# request is rejected. The token lives in the session and is dropped into every
# template as csrf_token().
#
# init_csrf() -- turn on the check for the whole app + expose csrf_token() to templates
# _issue_token() -- make-or-reuse the per-session token
# _check() -- reject unsafe requests whose token is missing or wrong

from __future__ import annotations

import hmac
import secrets

from flask import Flask, abort, request, session

_TOKEN_KEY = "csrf_token"
_FORM_FIELD = "csrf_token"
_HEADER = "X-CSRF-Token"
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _issue_token() -> str:
    token = session.get(_TOKEN_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_TOKEN_KEY] = token
    return token


def _submitted_token() -> str:
    return request.form.get(_FORM_FIELD) or request.headers.get(_HEADER) or ""


def init_csrf(app: Flask) -> None:
    @app.before_request
    def _check():
        if request.method not in _UNSAFE_METHODS:
            return None
        expected = session.get(_TOKEN_KEY) or ""
        provided = _submitted_token()
        if not expected or not provided or not hmac.compare_digest(expected, provided):
            abort(400, description="The form session expired or the security token was missing. Please try again.")
        return None

    @app.context_processor
    def _inject():
        return {"csrf_token": _issue_token}
