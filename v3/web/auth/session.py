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
