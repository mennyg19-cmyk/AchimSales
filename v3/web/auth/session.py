"""Session-backed principal storage."""

from __future__ import annotations

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


def sync_role(role: str) -> None:
    """Refresh the cached role on the stored principal.

    The session is trusted only for identity; role/scope are re-resolved from the
    DB on every security check. But presentation (the role badge, the settings
    page sections, nav gating) reads the cached session role, which is captured
    at login. Without this, a role change (e.g. seeding someone to developer)
    only shows up after the user logs out and back in. We call this per-request
    so the UI reflects the live DB role immediately - no re-login needed.
    """
    data = session.get(_SESSION_KEY)
    if isinstance(data, dict) and data.get("role") != role:
        data = {**data, "role": role}
        session[_SESSION_KEY] = data
