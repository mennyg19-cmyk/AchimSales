"""Session-backed principal storage."""

from __future__ import annotations

from urllib.parse import quote

from flask import session

from web.auth.principal import Principal

_SESSION_KEY = "v3_user"


def current_principal() -> Principal | None:
    return Principal.from_dict(session.get(_SESSION_KEY) or {})


def login(principal: Principal) -> None:
    session[_SESSION_KEY] = principal.to_dict()
    session.permanent = True


def logout() -> None:
    session.pop(_SESSION_KEY, None)
    session.pop("user", None)


def login_redirect(next_path: str = "/") -> str:
    safe = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
    return f"/login?next={quote(safe, safe='/?=&')}"


def sync_role(role: str) -> None:
    """Refresh the cached role on the stored principal.

    The session is trusted only for identity; role/scope are re-resolved from the
    DB on every security check. Presentation (badge, settings, nav) reads the
    cached session role captured at login. Call this per-request so a promotion
    shows up without a re-login.
    """
    refresh_from_db(role=role, is_dev=None)


def refresh_from_db(*, role: str, is_dev: bool | None) -> None:
    data = session.get(_SESSION_KEY)
    if not isinstance(data, dict):
        return
    updated = {**data, "role": role}
    if is_dev is not None:
        updated["is_dev"] = is_dev
    if updated != data:
        session[_SESSION_KEY] = updated
