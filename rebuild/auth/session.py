"""Keeping the signed-in person in the browser session."""

# === What's in this file ===
# After a successful Microsoft sign-in we remember who the person is in Flask's
# signed session cookie (just their email/name/role -- never a token). These
# helpers are the only place that reads or writes that session slot.
#
# login_user() -- store the principal in the session (fresh session id)
# logout_user() -- forget the signed-in person
# current_principal() -- the signed-in Principal for this request, or None

from __future__ import annotations

from typing import Optional

from flask import session

from .principal import Principal

_PRINCIPAL_KEY = "principal"


def login_user(principal: Principal) -> None:
    session.clear()
    session[_PRINCIPAL_KEY] = principal.to_dict()
    session.permanent = True


def logout_user() -> None:
    session.clear()


def current_principal() -> Optional[Principal]:
    return Principal.from_dict(session.get(_PRINCIPAL_KEY))
