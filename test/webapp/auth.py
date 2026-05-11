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
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from flask import abort, jsonify, redirect, has_request_context, request, session, url_for
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
# Admin resolution: env list + test-app DB + live-app DB
# ---------------------------------------------------------------------------


def _live_app_db_path() -> Path | None:
    """Where is the live app's app.db on this host?

    On Azure App Service the live app writes to /home/data/app.db.
    Locally it sits next to the live webapp module.
    Override via V2_LIVE_APP_DB env var.
    """
    explicit = os.environ.get("V2_LIVE_APP_DB")
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None

    if os.environ.get("WEBSITE_SITE_NAME"):
        p = Path("/home/data/app.db")
        return p if p.exists() else None

    repo_root = Path(__file__).resolve().parents[2]
    p = repo_root / "webapp" / "app.db"
    return p if p.exists() else None


def _is_admin_in_test_db(email: str) -> bool:
    """Check the test app's own app_users table.

    A user is admin on the test site if either:
      * legacy ``is_admin`` flag is on, OR
      * ``role`` is admin or developer (the live-app convention).
    """
    if not email:
        return False
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT is_admin, role FROM app_users WHERE email = ?",
                (email,),
            ).fetchone()
        if not row:
            return False
        if row["is_admin"]:
            return True
        return (row["role"] or "").strip().lower() in ("admin", "developer")
    except Exception:
        log.exception("is_admin: test db lookup failed for %s", email)
        return False


def _is_admin_in_live_db(email: str) -> bool:
    """Check the live app's app_users table (read-only, opportunistic).

    The live app uses a `role` column with values like 'admin', 'developer',
    'manager', 'salesman'. We treat admin + developer as admins on the
    test site. Failures are silently ignored (returns False) so a missing
    or locked live DB never breaks the test app.
    """
    if not email:
        return False
    db_path = _live_app_db_path()
    if db_path is None:
        return False
    try:
        # Read-only URI so we never lock the live DB.
        uri = f"file:{db_path}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=2) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT role FROM app_users WHERE lower(email) = ?",
                (email.strip().lower(),),
            ).fetchone()
        if not row:
            return False
        return (row["role"] or "").strip().lower() in {"admin", "developer"}
    except Exception:
        log.debug("is_admin: live db lookup failed for %s", email, exc_info=True)
        return False


def resolve_admin(email: str | None) -> bool:
    """True if the email should be treated as an admin on the test site.

    Resolution order:
      1. V2_ADMIN_EMAILS env var (legacy)
      2. test app's own app_users.is_admin = 1
      3. live app's app_users.role IN ('admin', 'developer')
    """
    if not email:
        return False
    e = email.strip().lower()
    if e in ADMIN_EMAILS:
        return True
    if _is_admin_in_test_db(e):
        return True
    if _is_admin_in_live_db(e):
        return True
    return False


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
    """Authoritative admin check.

    Trusts the live state, not the (potentially stale) session cookie:
    we always re-resolve via env-list / test-db / live-db. The result is
    cached back into the session for the duration of the request so
    subsequent calls don't re-hit the database.
    """
    u = user if user is not None else current_user()
    if not u:
        return False
    email = (u.get("email") or "").strip().lower()
    if not email:
        return False

    flag = resolve_admin(email)
    # Update the session in place so templates/blueprints that already
    # read user["is_admin"] see the fresh value without a re-login.
    if u.get("is_admin") != flag:
        u["is_admin"] = flag
        if has_request_context():
            session_user = current_user()
            if session_user and session_user.get("email", "").strip().lower() == email:
                session[SESSION_KEY] = u
    return flag


def has_sharepoint_access(user: dict[str, Any] | None = None) -> bool:
    """True when the user is admin OR has the sharepoint_access_enabled flag."""
    u = user or current_user()
    if not u:
        return False
    if is_admin(u):
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
    """Insert or update the test app's app_users row.

    On first insert we seed `is_admin` from the env list / live DB so a
    brand-new admin doesn't have to be promoted manually. On update we
    leave the existing flag alone (so admins can manage it via the
    settings UI without sign-in resetting it).
    """
    email = email.strip().lower()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    seed_admin = 1 if resolve_admin(email) else 0
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
                (email, display_name, seed_admin, now, now),
            )
        else:
            conn.execute(
                """
                UPDATE app_users
                   SET display_name   = COALESCE(?, display_name),
                       last_login_utc = ?
                 WHERE email = ?
                """,
                (display_name, now, email),
            )


def _sign_in(email: str, display_name: str | None, *, dev_bypass: bool) -> dict[str, Any]:
    email = email.strip().lower()
    _upsert_user(email, display_name)
    user = {
        "email": email,
        "name": display_name or email,
        "is_admin": resolve_admin(email),
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
