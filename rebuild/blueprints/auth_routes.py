"""Sign-in, callback, and sign-out routes."""

# === What's in this file ===
# The login page and the Microsoft sign-in round trip.
#   /login          -- the page with the "Sign in with Microsoft" button
#   /login/start    -- kicks off the Microsoft redirect
#   /auth/callback  -- Microsoft sends the person back here; we finish sign-in
#   /logout         -- forget the session
#   /login/dev      -- pick a test user, ONLY when running in dev mode
# On success we resolve the person's role, record the login, and store the
# principal in the session. "next" is validated so it can only be a local path
# (no open redirect to another site).
#
# _safe_next() -- keep redirects on this site only
# login() / start() / callback() / logout() / dev_login()

from __future__ import annotations

from urllib.parse import urlsplit

from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..app import get_config, get_db
from ..auth.authorization import build_principal
from ..auth.msal_flow import build_login_url, complete_login
from ..auth.session import current_principal, login_user, logout_user
from ..data.repositories.users import UsersRepository

auth_bp = Blueprint("auth", __name__)


def _safe_next(raw: str | None) -> str:
    """Only allow redirecting to a path INSIDE this mounted app.

    Two traps to avoid: an absolute URL to another site (open redirect), and a
    path that looks local but lands outside our mount. Because the app runs under
    a path prefix, an app-local path like "/reports" must get the mount prefix
    re-added ("/test-next/reports"); without that, redirecting to "/" would
    escape into the live app.
    """
    fallback = url_for("main.index")
    if not raw or not raw.startswith("/") or raw.startswith("//") or raw.startswith("/\\"):
        return fallback
    parts = urlsplit(raw)
    if parts.scheme or parts.netloc:
        return fallback
    root = request.script_root or ""
    if root and raw != root and not raw.startswith(root + "/"):
        return root + raw
    return raw


def _sign_in(email: str, name: str, next_url: str):
    config = get_config()
    principal = build_principal(config, email, name)
    UsersRepository(get_db()).record_login(principal)
    login_user(principal)
    return redirect(_safe_next(next_url))


@auth_bp.get("/login")
def login():
    if current_principal() is not None:
        return redirect(_safe_next(request.args.get("next")))
    return render_template(
        "login.html",
        next=request.args.get("next", ""),
        dev_mode=(get_config().auth_mode == "dev"),
        error=request.args.get("error"),
    )


@auth_bp.get("/login/start")
def start():
    # Microsoft redirects back to a bare callback URL, so remember where the
    # person was headed before we send them off to sign in.
    session["login_next"] = _safe_next(request.args.get("next"))
    return redirect(build_login_url(get_config()))


@auth_bp.get("/auth/callback")
def callback():
    result = complete_login(get_config())
    next_url = session.pop("login_next", None)
    if "error" in result:
        return redirect(url_for("auth.login", error=result["error"]))
    return _sign_in(result["email"], result["name"], next_url)


@auth_bp.post("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.post("/login/dev")
def dev_login():
    if get_config().auth_mode != "dev":
        abort(404)
    email = (request.form.get("email") or "").strip().lower()
    if not email:
        return redirect(url_for("auth.login", error="Enter an email to sign in as."))
    return _sign_in(email, request.form.get("name") or email, request.form.get("next"))
