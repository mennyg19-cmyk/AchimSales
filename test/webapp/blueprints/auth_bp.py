"""Auth blueprint for the v2 app.

Routes:
    GET  /login                 -- login landing page
    POST /login/dev             -- dev-mode sign in (AUTH_MODE=dev only)
    GET  /login/start           -- redirect to Microsoft (AUTH_MODE=msal)
    GET  /auth/callback         -- MSAL redirect target
    GET  /logout                -- clear session
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse, urlunparse

from flask import Blueprint, flash, redirect, render_template, request, url_for

from test.config.settings import AUTH_MODE
from test.webapp.auth import (
    build_login_url,
    complete_msal_login,
    current_user,
    msal_configured,
    sign_in_dev,
    sign_out,
)

log = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


def _safe_next(candidate: str | None) -> str:
    """Only allow same-origin relative redirect targets."""
    if not candidate:
        return url_for("index")
    parsed = urlparse(candidate)
    if parsed.netloc or parsed.scheme:
        return url_for("index")
    path = parsed.path or url_for("index")
    return urlunparse(("", "", path, parsed.params, parsed.query, ""))


@auth_bp.get("/login")
def login():
    if current_user():
        return redirect(_safe_next(request.args.get("next")))
    return render_template(
        "login.html",
        auth_mode=AUTH_MODE,
        msal_configured=msal_configured(),
        next_url=request.args.get("next") or "",
    )


@auth_bp.post("/login/dev")
def login_dev():
    if AUTH_MODE != "dev":
        return redirect(url_for("auth.login"))
    email = (request.form.get("email") or "").strip().lower()
    name  = (request.form.get("name")  or "").strip() or None
    if not email or "@" not in email:
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("auth.login"))
    sign_in_dev(email, name)
    return redirect(_safe_next(request.form.get("next")))


@auth_bp.get("/login/start")
def login_start():
    if AUTH_MODE != "msal":
        return redirect(url_for("auth.login"))
    try:
        url = build_login_url()
    except Exception as e:
        log.exception("MSAL login start failed")
        flash(f"Could not start Microsoft sign-in: {e}", "error")
        return redirect(url_for("auth.login"))
    return redirect(url)


@auth_bp.route("/auth/callback", methods=["GET", "POST"])
def auth_callback():
    result = complete_msal_login()
    if isinstance(result, dict) and result.get("error"):
        flash(result["error"], "error")
        return redirect(url_for("auth.login"))
    return redirect(url_for("index"))


@auth_bp.get("/logout")
def logout():
    sign_out()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
