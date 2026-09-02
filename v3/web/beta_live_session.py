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
    role = str(live.get("role") or "salesman").strip().lower()
    if role not in VALID_ROLES:
        role = "salesman"
    cookie_dev = bool(live.get("_dev")) or role == "developer"
    dev_email = str(live.get("_dev_email") or "").strip().lower()

    db = current_app.config["DB"]
    users = UserRepository(db)
    actor = users.get_by_email(dev_email) if dev_email else None
    still_dev = bool(actor and actor.is_active and actor.role == "developer")
    is_dev = still_dev
    impersonating = still_dev and bool(dev_email) and email != dev_email
    if cookie_dev and not still_dev:
        # Leftover impersonation after demotion/disable: never keep the
        # target's identity. A developer's own first Live login has no v3
        # row yet — that must still create, not log them out of Live.
        own_cookie = (not dev_email) or (email == dev_email)
        if actor is None and not own_cookie:
            from web.auth.session import logout
            session.pop(_LIVE_USER_KEY, None)
            logout()
            return None
        if actor is not None:
            email = actor.email
            raw_name = actor.display_name or actor.email
            display = raw_name
            role = actor.role
            live = {
                "email": email,
                "name": raw_name,
                "role": role,
                "salesman_key": None,
            }
            session[_LIVE_USER_KEY] = live
            is_dev = False
            impersonating = False

    user = users.get_by_email(email)
    if user is None:
        persist_role = role if role in VALID_ROLES else "salesman"
        user = users.create(email, role=persist_role, display_name=display)
        if persist_role not in ("admin", "developer"):
            _sync_salesman_scope(users, user.id, live, email, persist_role)
    elif not impersonating and not (user.display_name or "").strip() and display.strip():
        users.update(user.id, display_name=display)
        user = users.get_by_id(user.id) or user

    session_role = role if impersonating else user.role
    existing = current_principal()
    if (
        existing is not None
        and existing.email == email
        and existing.role == session_role
        and existing.is_dev == is_dev
        and existing.impersonating == impersonating
    ):
        return existing

    principal = Principal(
        email=email,
        name=raw_name,
        role=session_role,
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
