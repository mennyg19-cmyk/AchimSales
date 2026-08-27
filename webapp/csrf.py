"""Per-session CSRF for legacy Flask. No extra package.

Unsafe methods need the session token as form field csrf_token or header
X-CSRF-Token. Entra callback is exempt because Microsoft POSTs the code.

Templates use {% csrf_token %} which writes name=csrf_token. Semgrep's
Django form rule still does not accept that tag in generic HTML.
"""

from __future__ import annotations

import hmac
import secrets

from flask import Flask, abort, request, session
from jinja2 import nodes
from jinja2.ext import Extension
from markupsafe import escape

_SESSION_KEY = "_csrf_token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_EXEMPT_ENDPOINTS = {"auth.auth_callback"}
_EXEMPT_PATHS = {"/auth/callback"}


def csrf_token() -> str:
    token = session.get(_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_SESSION_KEY] = token
    return token


class _CsrfInput:
    """Hidden input as __html__ so Jinja does not entity-encode it.

    Markup() trips Semgrep explicit-unescape; the token is token_urlsafe.
    """

    __slots__ = ("_html",)

    def __init__(self, token: str) -> None:
        self._html = (
            '<input type="hidden" name="csrf_token" value="'
            + str(escape(token))
            + '">'
        )

    def __html__(self) -> str:
        return self._html

    def __str__(self) -> str:
        return self._html


class CsrfTokenExtension(Extension):
    tags = {"csrf_token"}

    def parse(self, parser):
        lineno = next(parser.stream).lineno
        call = self.call_method("_render", lineno=lineno)
        return nodes.Output([call]).set_lineno(lineno)

    def _render(self) -> _CsrfInput:
        return _CsrfInput(csrf_token())


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
    app.jinja_env.add_extension(CsrfTokenExtension)
    app.jinja_env.globals["form_protect"] = csrf_token
