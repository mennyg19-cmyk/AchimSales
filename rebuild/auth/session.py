"""Keeping the signed-in person in the browser session."""

# === What's in this file ===
# After a successful Microsoft sign-in we remember WHO the person is in Flask's
# signed session cookie -- only their email and display name, never a token and
# never their role. The role (and what they're allowed to see) is re-decided on
# every request from the server's config, so a stale or tampered cookie can't
# grant privileges.
#
# login_user() -- start a fresh session holding just the person's identity
# logout_user() -- forget the signed-in person
# current_principal() -- the signed-in Principal for this request, role resolved
#                        server-side, or None if not signed in

from __future__ import annotations

from typing import Optional

from flask import session

from ..data.connection import normalize_email
from .principal import Principal

_USER_KEY = "user"


def login_user(principal: Principal) -> None:
    # Clearing first rotates the session so a pre-login session id can't be
    # reused after sign-in (guards against session fixation).
    session.clear()
    session[_USER_KEY] = {"email": principal.email, "name": principal.name}
    session.permanent = True


def logout_user() -> None:
    session.clear()


def current_principal() -> Optional[Principal]:
    session_user = session.get(_USER_KEY)
    if not isinstance(session_user, dict) or not session_user.get("email"):
        return None
    # Role is never trusted from the cookie; resolve it from server config now.
    from ..app import get_config
    from .authorization import resolve_role

    email = normalize_email(str(session_user["email"]))
    name = str(session_user.get("name") or email)
    return Principal(email=email, name=name, role=resolve_role(get_config(), email))
