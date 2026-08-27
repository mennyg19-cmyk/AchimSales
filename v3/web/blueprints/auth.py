"""Auth routes: MSAL login/callback, magic links, role picker, logout."""

from __future__ import annotations

import logging

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
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

log = logging.getLogger(__name__)

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


def _signed_in():
    from web.auth.session import current_principal
    from web.beta_live_session import adopt_live_identity

    return adopt_live_identity() or current_principal()


@auth_bp.get("/login")
def login_page():
    cfg = _cfg()
    if _signed_in() is not None:
        return redirect(url_for("reports.reports_list"))
    nxt = _safe_next()
    if cfg.is_beta:
        start = url_for("auth.login_start", next=nxt)
        return render_template("login.html", live_login=True, next_val=nxt, login_start=start)
    if cfg.auth_mode == "msal":
        session[_NEXT_KEY] = nxt
        return redirect(msal_flow.build_login_url(cfg))
    return render_template("login.html", live_login=False, next_val=nxt, roles=VALID_ROLES)


@auth_bp.get("/login/start")
def login_start():
    session[_NEXT_KEY] = _safe_next()
    return redirect(msal_flow.build_login_url(_cfg()))


@auth_bp.post("/login/dev")
def login_dev():
    cfg = _cfg()
    if cfg.is_beta:
        abort(403, description="Home site uses Microsoft or magic-link login")
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
    is_dev = user.role == "developer"
    _login_or_403(user, name=user.display_name or result["name"], is_dev=is_dev)
    dest = session.pop(_NEXT_KEY, None) or url_for("reports.reports_list")
    return redirect(dest)


@auth_bp.post("/logout")
def logout_route():
    logout()
    session.pop("user", None)
    session.clear()
    return redirect(url_for("auth.login_page"))


def _client_ip() -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or (request.remote_addr or "")


def _magic_link_url(token: str) -> str:
    from web.auth.public_origin import public_origin

    path = url_for("auth.consume_magic_link", token=token)
    return public_origin().rstrip("/") + path


@auth_bp.post("/login/magic-link")
def request_magic_link():
    email = (request.form.get("email") or "").strip().lower()
    if not email or "@" not in email:
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("auth.login_page"))

    from web.auth.magic_link_email import MagicLinkError, send_magic_link_email
    from web.data.repositories.magic_links import MagicLinkRepository

    tokens = MagicLinkRepository(_db())
    ip = _client_ip()
    if not tokens.ip_rate_limited(ip):
        tokens.record_attempt(email, ip)
        row = UserRepository(_db()).get_by_email(email)
        if row and row.role == "salesman" and row.is_external and row.is_active:
            try:
                token = tokens.create_token(email, request_ip=ip)
                if token:
                    send_magic_link_email(email, _magic_link_url(token))
                    log.info("Magic-link sent to %s", email)
            except MagicLinkError:
                log.exception("Magic-link send failed for %s", email)
            except Exception:
                log.exception("Unexpected magic-link error for %s", email)

    flash(
        "If that email is registered as an external sales rep, "
        "you'll get a sign-in link in a minute.",
        "info",
    )
    return redirect(url_for("auth.login_page"))


@auth_bp.get("/login/magic-link/<token>")
def consume_magic_link(token):
    from web.data.repositories.magic_links import MagicLinkRepository

    email = MagicLinkRepository(_db()).consume_token(token)
    if not email:
        flash("That sign-in link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("auth.login_page"))

    row = UserRepository(_db()).get_by_email(email)
    if row is None or row.role != "salesman" or not row.is_external or not row.is_active:
        log.warning("Magic-link refused for %s", email)
        flash("That sign-in link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("auth.login_page"))

    _login_or_403(row, name=row.display_name or email, is_dev=False)
    log.info("Magic-link sign-in: %s", email)
    return redirect(url_for("reports.reports_list"))


def _role_picker_users() -> list[dict]:
    return [
        {
            "email": u.email,
            "display_name": u.display_name,
            "role": u.role,
            "salesman_key": "",
        }
        for u in UserRepository(_db()).all_users(include_inactive=True)
    ]


def _group_users(rows: list[dict]) -> dict[str, list]:
    grouped: dict[str, list] = {"admin": [], "developer": [], "manager": [], "salesman": []}
    for u in rows:
        grouped.setdefault(u.get("role") or "salesman", []).append(u)
    return grouped


@auth_bp.route("/dev/role-picker", methods=["GET", "POST"])
def role_picker():
    """Developer impersonation: pick any user, or view as yourself."""
    p = _signed_in()
    if p is None:
        return redirect(url_for("auth.login_page"))
    authz = current_app.config["AUTHZ"]
    if not (p.is_dev or authz.is_privileged(p)):
        return redirect(url_for("reports.reports_list"))

    dev_email = (p.real_email or p.email).strip().lower()
    raw_name = p.real_name or p.name
    dev_name = raw_name.split(" (as ")[0] if " (as " in raw_name else raw_name

    if request.method == "POST":
        target_email = (request.form.get("target_email") or "").strip()
        users = UserRepository(_db())
        if target_email == "__self__":
            real = users.get_by_email(dev_email)
            if real is None or not real.is_active:
                logout()
                return redirect(url_for("auth.login_page"))
            login(Principal(
                email=real.email, name=dev_name, role=real.role, is_dev=True,
            ))
            session["user"] = {
                "email": real.email, "name": dev_name, "role": real.role,
                "salesman_key": None, "_dev": True,
                "_dev_name": dev_name, "_dev_email": dev_email,
            }
        else:
            row = users.get_by_email(target_email.lower())
            if row is None:
                abort(404, description="User not found")
            display = row.display_name or row.email
            login(Principal(
                email=row.email,
                name=f"{display} (as {dev_name})",
                role=row.role,
                is_dev=True,
                impersonating=True,
                real_email=dev_email,
                real_name=dev_name,
            ))
            session["user"] = {
                "email": row.email,
                "name": f"{display} (as {dev_name})",
                "role": row.role,
                "salesman_key": None,
                "_dev": True,
                "_dev_name": dev_name,
                "_dev_email": dev_email,
            }
        return redirect(url_for("reports.reports_list"))

    user = {
        "name": p.name,
        "role": p.role,
        "_dev": True,
        "_dev_name": dev_name,
        "_dev_email": dev_email,
    }
    return render_template(
        "role_picker.html",
        user=user,
        grouped_users=_group_users(_role_picker_users()),
        dev_email=dev_email,
    )


# --- Impersonation (developer-only) ---------------------------------------- #

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
