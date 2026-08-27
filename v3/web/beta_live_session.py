"""Bridge Live's session identity into Beta (shared cookie, no second login).

The home app is v3 with is_beta, but uses Live's `session` cookie + the same
signing secret. After Live sign-in, `session["user"]` is present; this module
turns that into a v3 Principal and mirrors role/salesman scope into Beta's DB
so Authorization keeps working.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

log = logging.getLogger(__name__)

_LIVE_USER_KEY = "user"


def _live_directory_row(email: str) -> dict | None:
    """Live app_users row, or None when Live DB is missing or the email is unknown."""
    try:
        from webapp.db import get_user_by_email
        return get_user_by_email(email)
    except Exception:  # noqa: BLE001 - Beta still works from its own users table
        log.exception("beta: could not read live user directory for %s", email)
        return None


def live_login_redirect(next_path: str = "/") -> str:
    """Home login URL. Microsoft still starts on Live at /legacy/login/start."""
    safe = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
    return f"/login?next={quote(safe, safe='/?=&')}"


def adopt_live_identity():
    """If Live session has a user, adopt it (or refresh if they switched user)."""
    from flask import current_app, session

    from web.auth.principal import VALID_ROLES, Principal
    from web.auth.session import current_principal, login
    from web.data.repositories.users import UserRepository

    live = session.get(_LIVE_USER_KEY)
    if not isinstance(live, dict) or not live.get("email"):
        return current_principal()

    email = str(live["email"]).strip().lower()
    raw_name = str(live.get("name") or email)
    display = raw_name.split(" (as ")[0] if " (as " in raw_name else raw_name
    session_role = str(live.get("role") or "salesman").strip().lower()
    if session_role not in VALID_ROLES:
        session_role = "salesman"
    is_dev = bool(live.get("_dev")) or session_role == "developer"
    dev_email = str(live.get("_dev_email") or "").strip().lower()
    impersonating = is_dev and bool(dev_email) and email != dev_email

    live_row = _live_directory_row(email)
    if live_row:
        role = str(live_row.get("role") or "salesman").strip().lower()
        if role not in VALID_ROLES:
            role = "salesman"
        display = (live_row.get("display_name") or display or email)
    else:
        role = session_role

    existing = current_principal()
    if (
        existing is not None
        and existing.email == email
        and existing.role == role
        and existing.is_dev == is_dev
        and existing.impersonating == impersonating
    ):
        return existing

    db = current_app.config["DB"]
    users = UserRepository(db)
    if live_row:
        user = users.create(email, role=role, display_name=display)
    else:
        user = users.get_by_email(email)
        if user is None:
            persist_role = "developer" if is_dev and email == (dev_email or email) else role
            user = users.create(email, role=persist_role, display_name=display)
        elif not impersonating:
            role = user.role
    _sync_salesman_scope(users, user.id, live, email, role)

    principal = Principal(
        email=email,
        name=raw_name,
        role=role,
        is_dev=is_dev,
        impersonating=impersonating,
        real_email=dev_email if impersonating else "",
        real_name=str(live.get("_dev_name") or "") if impersonating else "",
    )
    login(principal)
    log.info("beta adopted live session for %s role=%s impersonating=%s", email, role, impersonating)
    return principal


def _sync_salesman_scope(users, user_id: int, live: dict, email: str, role: str) -> None:
    """Copy Live salesman visibility into Beta's user_salesman_access."""
    if role in ("admin", "developer"):
        return
    keys: list[str] = []
    sm = (live.get("salesman_key") or "").strip()
    if sm:
        keys.append(sm)
    try:
        from webapp.db import get_user_salesman_access

        for key in get_user_salesman_access(email):
            if key and key not in keys:
                keys.append(key)
    except Exception:  # noqa: BLE001 - Beta still works; scope may be empty until next hit
        log.exception("beta: could not read live salesman access for %s", email)
    users.set_salesman_access(user_id, keys)
