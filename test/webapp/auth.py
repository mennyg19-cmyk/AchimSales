"""v2 authentication: session helpers + MSAL flow.

Completely independent of the live app's ``webapp/auth.py``. Uses the
Flask session (cookie ``v2_session``) with two modes:

* ``V2_AUTH_MODE=dev``  -- self-serve dev picker (local development)
* ``V2_AUTH_MODE=msal`` -- Microsoft Entra ID via auth-code flow

All protected routes use ``@require_login``. The background scheduler
doesn't have a request context, so it falls back to the schedule's owner
row in the database instead of the session.
"""

from __future__ import annotations

import functools
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from flask import abort, jsonify, redirect, request, session, url_for
from werkzeug.wrappers import Response

from test.config.settings import (
    ADMIN_EMAILS,
    AUTH_MODE,
    AUTH_REDIRECT_PATH,
    AZURE_CLIENT_ID,
    AZURE_CLIENT_SECRET,
    AZURE_TENANT_ID,
    DEV_USER_EMAIL,
)
from test.webapp.db import connect

log = logging.getLogger(__name__)

SESSION_KEY = "v2_user"
AUTH_FLOW_KEY = "v2_auth_flow"


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def current_user() -> dict[str, Any] | None:
    """Return the user dict stored in the session, or None if not logged in."""
    user = session.get(SESSION_KEY)
    if not isinstance(user, dict) or not user.get("email"):
        return None
    return user


def current_user_email() -> str:
    """Return the logged-in email, or DEV_USER_EMAIL when no session exists.

    Used by the scheduler, which has no request context. Blueprints should
    prefer ``require_login`` so this fallback only ever applies server-side.
    """
    user = current_user()
    if user:
        return user["email"]
    return DEV_USER_EMAIL


def is_admin(user: dict[str, Any] | None = None) -> bool:
    u = user or current_user()
    if not u:
        return False
    return bool(u.get("is_admin"))


def has_sharepoint_access(user: dict[str, Any] | None = None) -> bool:
    """True when the user is admin OR has the sharepoint_access_enabled flag."""
    u = user or current_user()
    if not u:
        return False
    if u.get("is_admin"):
        return True
    email = (u.get("email") or "").strip().lower()
    if not email:
        return False
    with connect() as conn:
        row = conn.execute(
            "SELECT sharepoint_access_enabled FROM app_users WHERE email = ?",
            (email,),
        ).fetchone()
    return bool(row and row["sharepoint_access_enabled"])


def _wants_json() -> bool:
    """Heuristic: XHR / JSON API clients get 401 instead of a redirect."""
    if request.path.startswith("/api/"):
        return True
    accept = (request.headers.get("Accept") or "").lower()
    return "application/json" in accept and "text/html" not in accept


def require_login(view: Callable) -> Callable:
    """Decorator: reject the request if there is no authenticated session."""

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            if _wants_json():
                return (
                    jsonify({"error": "Unauthorized",
                             "description": "Sign in required",
                             "status": 401}),
                    401,
                )
            login_url = url_for("auth.login", next=request.full_path.rstrip("?"))
            return redirect(login_url)
        return view(*args, **kwargs)

    return wrapper


def require_admin(view: Callable) -> Callable:
    """Decorator: additionally requires ``is_admin``."""

    @functools.wraps(view)
    @require_login
    def wrapper(*args, **kwargs):
        if not is_admin():
            if _wants_json():
                return (
                    jsonify({"error": "Forbidden",
                             "description": "Admin role required",
                             "status": 403}),
                    403,
                )
            abort(403, description="Admin role required")
        return view(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Sign-in: writes the session and upserts the user row
# ---------------------------------------------------------------------------


def _upsert_user(email: str, display_name: str | None) -> None:
    email = email.strip().lower()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    admin = 1 if email in ADMIN_EMAILS else 0
    with connect() as conn:
        existing = conn.execute(
            "SELECT email FROM app_users WHERE email = ?", (email,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO app_users
                  (email, display_name, is_admin, first_login_utc, last_login_utc)
                VALUES (?, ?, ?, ?, ?)
                """,
                (email, display_name, admin, now, now),
            )
        else:
            conn.execute(
                """
                UPDATE app_users
                   SET display_name   = COALESCE(?, display_name),
                       is_admin       = ?,
                       last_login_utc = ?
                 WHERE email = ?
                """,
                (display_name, admin, now, email),
            )


def _sign_in(email: str, display_name: str | None, *, dev_bypass: bool) -> dict[str, Any]:
    email = email.strip().lower()
    _upsert_user(email, display_name)
    user = {
        "email": email,
        "name": display_name or email,
        "is_admin": email in ADMIN_EMAILS,
        "dev_bypass": bool(dev_bypass),
        "logged_in_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    session[SESSION_KEY] = user
    session.permanent = True
    return user


def sign_in_dev(email: str, display_name: str | None = None) -> dict[str, Any]:
    """Local-dev bypass sign-in. Does not contact Microsoft."""
    if AUTH_MODE != "dev":
        abort(403, description="Dev login is disabled in this environment")
    if not email or "@" not in email:
        abort(400, description="email is required")
    return _sign_in(email, display_name, dev_bypass=True)


def sign_out() -> None:
    session.pop(SESSION_KEY, None)
    session.pop(AUTH_FLOW_KEY, None)


# ---------------------------------------------------------------------------
# MSAL flow (only used when AUTH_MODE == "msal")
# ---------------------------------------------------------------------------


def msal_configured() -> bool:
    return bool(AZURE_TENANT_ID and AZURE_CLIENT_ID and AZURE_CLIENT_SECRET)


def _build_msal_app():
    import msal
    authority = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
    return msal.ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=authority,
        client_credential=AZURE_CLIENT_SECRET,
    )


def _redirect_uri() -> str:
    root = request.url_root.rstrip("/")
    if request.headers.get("X-Forwarded-Proto") == "https" and root.startswith("http://"):
        root = "https://" + root[7:]
    return root + AUTH_REDIRECT_PATH


def build_login_url() -> str:
    if not msal_configured():
        abort(500, description="MSAL auth is not configured (V2_AZURE_* missing)")
    app = _build_msal_app()
    flow = app.initiate_auth_code_flow(
        scopes=["User.Read"],
        redirect_uri=_redirect_uri(),
    )
    session[AUTH_FLOW_KEY] = flow
    return flow["auth_uri"]


def complete_msal_login() -> Response | dict[str, Any]:
    """Finish the MSAL redirect. Signs the user in or returns an error payload."""
    flow = session.pop(AUTH_FLOW_KEY, None)
    if not flow:
        return {"error": "No auth flow in session. Start login again."}
    auth_response = request.values.to_dict()
    try:
        result = _build_msal_app().acquire_token_by_auth_code_flow(flow, auth_response)
    except Exception as e:
        log.exception("acquire_token_by_auth_code_flow failed")
        return {"error": f"Microsoft rejected the sign-in: {e}"}

    if "error" in result:
        return {"error": result.get("error_description") or result["error"]}

    claims = result.get("id_token_claims") or {}
    email = (
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("upn")
        or ""
    ).strip().lower()
    name = claims.get("name") or email
    if not email:
        return {"error": "Microsoft did not return an email claim."}

    _sign_in(email, name, dev_bypass=False)
    return {"ok": True, "email": email}
