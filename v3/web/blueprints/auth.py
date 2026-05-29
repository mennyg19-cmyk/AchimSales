"""Auth routes: MSAL login/callback, dev login + role picker, logout.

Thin: delegates to web.auth.*. The login/role-picker UI is intentionally minimal
here; the pixel-matched templates land in the front-end phase. Dev login is hard
-refused unless AUTH_MODE=dev (rule 6).
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, redirect, request, session, url_for
from markupsafe import escape

from web.auth import msal_flow
from web.auth.principal import VALID_ROLES, Principal
from web.auth.session import login, logout
from web.data.repositories.users import User, UserRepository

auth_bp = Blueprint("auth", __name__)

_NEXT_KEY = "v3_login_next"


def _cfg():
    return current_app.config["APP_CONFIG"]


def _db():
    return current_app.config["DB"]


def _safe_next() -> str:
    """Only allow same-app relative redirects (no open redirect). Reads args+form."""
    nxt = request.values.get("next") or ""
    if nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return url_for("health.healthz")


def _login_or_403(user: User, *, name: str, is_dev: bool) -> None:
    """Sign the user in, refusing disabled accounts (fail closed)."""
    if not user.is_active:
        abort(403, description="This account is disabled")
    login(Principal(email=user.email, name=name, role=user.role, is_dev=is_dev))


@auth_bp.get("/login")
def login_page():
    cfg = _cfg()
    if cfg.auth_mode == "msal":
        session[_NEXT_KEY] = _safe_next()  # carry intended destination across the redirect
        return redirect(msal_flow.build_login_url(cfg))
    # dev mode: minimal picker (replaced by the live-styled template in FE phase)
    from web.extensions import csrf_token

    next_val = escape(_safe_next())
    return (
        "<form method='post' action='" + url_for("auth.login_dev") + "'>"
        f"<input type='hidden' name='csrf_token' value='{csrf_token()}'>"
        f"<input type='hidden' name='next' value='{next_val}'>"
        "<input name='email' placeholder='email' required>"
        "<select name='role'>"
        + "".join(f"<option value='{r}'>{r}</option>" for r in VALID_ROLES)
        + "</select><button type='submit'>Dev sign in</button></form>"
    ), 200


@auth_bp.post("/login/dev")
def login_dev():
    cfg = _cfg()
    if cfg.auth_mode != "dev":
        abort(403, description="Dev login is disabled in this environment")
    email = (request.form.get("email") or "").strip().lower()
    role = (request.form.get("role") or "salesman").strip().lower()
    if "@" not in email:
        abort(400, description="valid email required")
    if role not in VALID_ROLES:
        role = "salesman"
    user = UserRepository(_db()).upsert(email, display_name=email, role=role)
    _login_or_403(user, name=user.display_name or email, is_dev=True)
    return redirect(_safe_next())


@auth_bp.route("/auth/callback", methods=["GET", "POST"])
def callback():
    cfg = _cfg()
    result = msal_flow.complete_login(cfg)
    if "error" in result:
        abort(400, description=result["error"])
    user = UserRepository(_db()).upsert(result["email"], display_name=result["name"])
    _login_or_403(user, name=user.display_name or result["email"], is_dev=False)
    dest = session.pop(_NEXT_KEY, None) or url_for("health.healthz")
    return redirect(dest)


@auth_bp.post("/logout")
def logout_route():
    logout()
    return redirect(url_for("auth.login_page"))
