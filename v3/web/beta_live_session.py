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
    """Live login URL (Live sits at /legacy; Entra callback stays /auth/callback)."""
    safe = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
    return f"/legacy/login?next={quote(safe, safe='/?=&')}"


def adopt_live_identity():
    """If Live session has a user and Beta has none, adopt it. Returns principal."""
    from flask import current_app, session

    from web.auth.principal import VALID_ROLES, Principal
    from web.auth.session import current_principal, login
    from web.data.repositories.users import UserRepository

    existing = current_principal()
    if existing is not None:
        return existing

    live = session.get(_LIVE_USER_KEY)
    if not isinstance(live, dict) or not live.get("email"):
        return None

    email = str(live["email"]).strip().lower()
    name = str(live.get("name") or email)
    role = str(live.get("role") or "salesman").strip().lower()
    if role not in VALID_ROLES:
        role = "salesman"
    is_dev = bool(live.get("_dev")) or role == "developer"

    db = current_app.config["DB"]
    users = UserRepository(db)
    # create() upserts role so Live promotions show up on Beta without re-seed.
    user = users.create(email, role=role, display_name=name)
    _sync_salesman_scope(users, user.id, live, email, role)

    principal = Principal(email=email, name=name, role=role, is_dev=is_dev)
    login(principal)
    log.info("beta adopted live session for %s role=%s", email, role)
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
