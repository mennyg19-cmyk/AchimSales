"""Auth routes: MSAL login/callback, dev login + role picker, logout.

Thin: delegates to web.auth.*. The login/role-picker UI is intentionally minimal
here; the pixel-matched templates land in the front-end phase. Dev login is hard
-refused unless AUTH_MODE=dev (rule 6).
"""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

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
    if cfg.is_beta:
        # Beta shares Live login — never start a second MSAL round-trip.
        from web.auth.session import current_principal
        from web.beta_live_session import adopt_live_identity, live_login_redirect

        if adopt_live_identity() is not None or current_principal() is not None:
            return redirect(url_for("reports.reports_list"))
        mount = (request.script_root or "").rstrip("/")
        dest = f"{mount}/" if mount else "/"
        return redirect(live_login_redirect(dest))
    if cfg.auth_mode == "msal":
        session[_NEXT_KEY] = _safe_next()  # carry intended destination across the redirect
        return redirect(msal_flow.build_login_url(cfg))
    return render_template("login.html", next_val=_safe_next(), roles=VALID_ROLES)


@auth_bp.post("/login/dev")
def login_dev():
    cfg = _cfg()
    if cfg.is_beta:
        abort(403, description="Beta uses Live login; open /legacy/login")
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
    if cfg.is_beta:
        # No separate Entra redirect URI for /beta — Live owns the callback.
        from web.beta_live_session import live_login_redirect

        return redirect(live_login_redirect("/"))
    result = msal_flow.complete_login(cfg)
    if "error" in result:
        abort(400, description=result["error"])
    user = UserRepository(_db()).upsert(result["email"], display_name=result["name"])
    _login_or_403(user, name=user.display_name or result["name"], is_dev=False)
    dest = session.pop(_NEXT_KEY, None) or url_for("health.healthz")
    return redirect(dest)


@auth_bp.post("/logout")
def logout_route():
    cfg = _cfg()
    logout()
    if cfg.is_beta:
        # Shared cookie: clear Live identity too, then Live login page.
        session.pop("user", None)
        session.clear()
        return redirect("/legacy/login")
    return redirect(url_for("auth.login_page"))


# --- Impersonation (developer-only, production-safe) ----------------------- #

@auth_bp.get("/impersonate")
def impersonate_page():
    """User picker for developer impersonation. Shows all users (incl. inactive)."""
    from web.auth.session import current_principal

    p = current_principal()
    if p is None:
        return redirect(url_for("auth.login_page"))
    if p.impersonating:
        abort(400, description="Cannot nest impersonation; end the current session first")
    authz = current_app.config["AUTHZ"]
    if not authz.is_privileged(p):
        abort(403, description="Impersonation is developer/admin only")

    users = UserRepository(_db())
    all_users = users.all_users(include_inactive=True)
    grouped: dict[str, list] = {}
    for u in all_users:
        grouped.setdefault(u.role, []).append(u)
    return render_template("impersonate.html", grouped_users=grouped, principal=p)


@auth_bp.post("/impersonate")
def impersonate_start():
    """Start impersonating a target user (developer-only)."""
    from web.auth.session import current_principal

    p = current_principal()
    if p is None:
        return redirect(url_for("auth.login_page"))
    if p.impersonating:
        abort(400, description="Cannot nest impersonation")
    authz = current_app.config["AUTHZ"]
    if not authz.is_privileged(p):
        abort(403, description="Impersonation is developer/admin only")

    target_email = (request.form.get("email") or "").strip().lower()
    if not target_email:
        abort(400, description="Target email required")

    target = UserRepository(_db()).get_by_email(target_email)
    if target is None:
        abort(404, description="User not found")

    display = target.display_name or target.email
    impersonated = Principal(
        email=target.email,
        name=f"{display} (as {p.name})",
        role=target.role,
        is_dev=p.is_dev,
        impersonating=True,
        real_email=p.email,
        real_name=p.name,
    )
    login(impersonated)
    return redirect(url_for("reports.reports_list"))


@auth_bp.post("/impersonate/end")
def impersonate_end():
    """End impersonation, restoring the developer's own session."""
    from web.auth.session import current_principal

    p = current_principal()
    if p is None or not p.impersonating:
        return redirect(url_for("reports.reports_list"))
    real_user = UserRepository(_db()).get_by_email(p.real_email)
    if real_user is None or not real_user.is_active:
        logout()
        return redirect(url_for("auth.login_page"))
    login(Principal(
        email=real_user.email, name=p.real_name or real_user.display_name or real_user.email,
        role=real_user.role, is_dev=p.is_dev,
    ))
    return redirect(url_for("reports.reports_list"))
