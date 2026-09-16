"""Route guards: who has to be signed in, who has to be privileged."""

# === What's in this file ===
# Put @require_login on any route that needs a signed-in person, and
# @require_privileged on admin/developer-only routes. Both go through the
# session helpers, so there's one consistent way to protect a route.
#
# require_login -- redirect to the login page (remembering where they wanted to go)
# require_privileged -- signed in AND admin/developer, else 403

from __future__ import annotations

from functools import wraps

from flask import abort, redirect, request, url_for

from .session import current_principal


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_principal() is None:
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapped


def require_privileged(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        principal = current_principal()
        if principal is None:
            return redirect(url_for("auth.login", next=request.full_path))
        if not principal.is_privileged:
            abort(403)
        return view(*args, **kwargs)

    return wrapped
