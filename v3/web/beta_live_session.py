"""Bridge Live's session identity into Beta (shared cookie, no second login).

The home app is v3 with is_beta, but uses Live's `session` cookie + the same
signing secret. After Live sign-in, `session["user"]` is present; this module
turns that into a v3 Principal and mirrors role/salesman scope into Beta's DB
so Authorization keeps working.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from web.auth.principal import ROLE_DEVELOPER, Principal

log = logging.getLogger(__name__)

_LIVE_USER_KEY = "user"


def live_login_redirect(next_path: str = "/") -> str:
    """Home login URL. Microsoft still starts on Live at /legacy/login/start."""
    safe = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
    return f"/login?next={quote(safe, safe='/?=&')}"


def adopt_live_identity():
    """If Live session has a user, adopt it (or refresh if they switched user)."""
    from flask import current_app, session

    from web.auth.authorization import Authorization
    from web.auth.session import current_principal, login, logout
    from web.data.repositories.users import UserRepository

    live = session.get(_LIVE_USER_KEY)
    if not isinstance(live, dict) or not live.get("email"):
        return current_principal()

    email = str(live["email"]).strip().lower()
    cookie_dev = bool(live.get("_dev")) or live.get("role") == ROLE_DEVELOPER
    dev_email = str(live.get("_dev_email") or "").strip().lower()

    db = current_app.config["DB"]
    users = UserRepository(db)
    actor = users.get_by_email(dev_email) if dev_email else None
    still_dev = Authorization.is_active_developer_row(actor)
    is_dev = still_dev
    impersonating = still_dev and email != dev_email
    if cookie_dev and not still_dev:
        # Leftover impersonation after demotion/disable: never keep the
        # target's identity. Unknown actors cannot retain a Live identity.
        own_cookie = (not dev_email) or (email == dev_email)
        if actor is None and not own_cookie:
            session.pop(_LIVE_USER_KEY, None)
            logout()
            return None
        if actor is not None:
            email = actor.email
            live = {
                "email": email,
                "name": actor.display_name or actor.email,
                "role": actor.role,
                "salesman_key": None,
            }
            session[_LIVE_USER_KEY] = live
            is_dev = False
            impersonating = False

    user = users.get_by_email(email)
    if user is None or not user.is_active:
        session.pop(_LIVE_USER_KEY, None)
        logout()
        return None

    session_role = user.role
    display = (user.display_name or user.email).strip() or user.email
    if impersonating and actor is not None:
        actor_name = (actor.display_name or actor.email).strip() or actor.email
        session_name = f"{display} (as {actor_name})"
        real_name = actor_name
    else:
        session_name = display
        real_name = ""

    existing = current_principal()
    if (
        existing is not None
        and existing.email == email
        and existing.name == session_name
        and existing.role == session_role
        and existing.is_dev == is_dev
        and existing.impersonating == impersonating
    ):
        return existing

    principal = Principal(
        email=email,
        name=session_name,
        role=session_role,
        is_dev=is_dev,
        impersonating=impersonating,
        real_email=dev_email if impersonating else "",
        real_name=real_name,
    )
    login(principal)
    log.info("beta adopted live session for %s role=%s impersonating=%s", email, session_role, impersonating)
    return principal
