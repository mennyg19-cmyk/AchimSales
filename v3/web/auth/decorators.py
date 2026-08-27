"""Route decorators built on the session principal + authorization layer."""

from __future__ import annotations

import functools
from typing import Callable

from flask import abort, current_app, jsonify, redirect, request, url_for

from web.auth.session import current_principal, logout


def _wants_json() -> bool:
    if request.path.startswith("/api/"):
        return True
    accept = (request.headers.get("Accept") or "").lower()
    return "application/json" in accept and "text/html" not in accept


def _deny(status: int, message: str):
    if _wants_json():
        return jsonify({"error": message, "status": status}), status
    if status == 401:
        return redirect(url_for("auth.login_page", next=request.full_path.rstrip("?")))
    abort(status, description=message)


def require_login(view: Callable) -> Callable:
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        p = current_principal()
        if p is None:
            return _deny(401, "Sign in required")
        if not current_app.config["AUTHZ"].session_allowed(p):
            logout()
            return _deny(401, "Sign in required")
        return view(*args, **kwargs)

    return wrapper


def require_privileged(view: Callable) -> Callable:
    """admin or developer only (diagnostics, admin hub, API probe)."""

    @functools.wraps(view)
    @require_login
    def wrapper(*args, **kwargs):
        p = current_principal()
        if not current_app.config["AUTHZ"].is_privileged(p):
            return _deny(403, "Admin or developer role required")
        return view(*args, **kwargs)

    return wrapper
