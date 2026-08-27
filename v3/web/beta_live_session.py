"""Adopt a leftover Live `session["user"]` cookie after the webapp tree is gone.

Home still uses the `session` cookie name and FLASK_SECRET_KEY, so people who
were signed in on the old Live app keep working for one deploy without a
second Entra trip. New logins write `v3_user` only.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

log = logging.getLogger(__name__)

_LIVE_USER_KEY = "user"


def live_login_redirect(next_path: str = "/") -> str:
    safe = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
    return f"/login?next={quote(safe, safe='/?=&')}"


def adopt_live_identity():
    """If the old Live cookie is present, turn it into a v3 Principal."""
    from flask import current_app, session

    from web.auth.principal import VALID_ROLES, Principal
    from web.auth.session import current_principal, login
    from web.data.repositories.users import UserRepository

    existing = current_principal()
    live = session.get(_LIVE_USER_KEY)
    if not isinstance(live, dict) or not live.get("email"):
        return existing

    email = str(live["email"]).strip().lower()
    raw_name = str(live.get("name") or email)
    display = raw_name.split(" (as ")[0] if " (as " in raw_name else raw_name
    session_role = str(live.get("role") or "salesman").strip().lower()
    if session_role not in VALID_ROLES:
        session_role = "salesman"
    is_dev = bool(live.get("_dev")) or session_role == "developer"
    dev_email = str(live.get("_dev_email") or "").strip().lower()
    impersonating = is_dev and bool(dev_email) and email != dev_email

    db = current_app.config["DB"]
    users = UserRepository(db)
    row = users.get_by_email(email)
    if row is not None:
        role = row.role if row.role in VALID_ROLES else "salesman"
        display = row.display_name or display or email
    else:
        persist_role = "developer" if is_dev and email == (dev_email or email) else session_role
        row = users.create(email, role=persist_role, display_name=display)
        role = row.role

    if (
        existing is not None
        and existing.email == email
        and existing.role == role
        and existing.is_dev == is_dev
        and existing.impersonating == impersonating
    ):
        return existing

    _sync_salesman_scope(users, row.id, live, role)

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
    log.info("adopted leftover live cookie for %s role=%s impersonating=%s", email, role, impersonating)
    return principal


def _sync_salesman_scope(users, user_id: int, live: dict, role: str) -> None:
    if role in ("admin", "developer"):
        return
    keys: list[str] = []
    sm = (live.get("salesman_key") or "").strip()
    if sm:
        keys.append(sm)
    if keys:
        users.set_salesman_access(user_id, keys)
