"""Auth routes: MSAL login/callback, dev login + role picker, logout.

Thin: delegates to web.auth.*. The login/role-picker UI is intentionally minimal
here; the pixel-matched templates land in the front-end phase. Dev login is hard
-refused unless AUTH_MODE=dev (rule 6).
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

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
from web.auth.authorization import Authorization
from web.auth.session import login, logout
from web.data.repositories.users import User, UserRepository
from web.delivery.graph_mail import GraphMailError, GraphMailer

auth_bp = Blueprint("auth", __name__)

_NEXT_KEY = "v3_login_next"
_MAGIC_LINK_TTL_MINUTES = 15
log = logging.getLogger(__name__)


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


def _create_magic_link_token(email: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with _db().precious() as conn:
        conn.execute("DELETE FROM magic_link_tokens WHERE email = ?", (email,))
        conn.execute(
            "INSERT INTO magic_link_tokens(token_hash, email, expires_at) VALUES (?, ?, ?)",
            (
                hashlib.sha256(token.encode("utf-8")).hexdigest(),
                email,
                (now + timedelta(minutes=_MAGIC_LINK_TTL_MINUTES)).isoformat(),
            ),
        )
    return token


def _consume_magic_link_token(token: str) -> str | None:
    if len(token) < 16:
        return None
    with _db().precious() as conn:
        row = conn.execute(
            """UPDATE magic_link_tokens SET used = 1
               WHERE token_hash = ? AND used = 0 AND expires_at >= ?
               RETURNING email""",
            (
                hashlib.sha256(token.encode("utf-8")).hexdigest(),
                datetime.now(timezone.utc).isoformat(),
            ),
        ).fetchone()
    return row["email"] if row else None


def _magic_link_url(token: str) -> str:
    path = url_for("auth.consume_magic_link", token=token)
    public_base_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    return f"{public_base_url}{path}" if public_base_url else url_for(
        "auth.consume_magic_link", token=token, _external=True)


@auth_bp.get("/login")
def login_page():
    cfg = _cfg()
    if cfg.is_beta:
        from urllib.parse import quote

        from web.auth.session import current_principal
        from web.beta_live_session import adopt_live_identity

        if adopt_live_identity() is not None or current_principal() is not None:
            return redirect(url_for("reports.reports_list"))
        nxt = request.args.get("next") or "/"
        if not nxt.startswith("/") or nxt.startswith("//"):
            nxt = "/"
        start = f"/legacy/login/start?next={quote(nxt, safe='/?=&')}"
        return render_template("login.html", live_login=True, next_val=nxt, login_start=start)
    if cfg.auth_mode == "msal":
        session[_NEXT_KEY] = _safe_next()  # carry intended destination across the redirect
        return redirect(msal_flow.build_login_url(cfg))
    return render_template("login.html", live_login=False, next_val=_safe_next(), roles=VALID_ROLES)


@auth_bp.post("/login/magic-link")
def request_magic_link():
    """Request a v3 external-account sign-in link without revealing account state."""
    email = (request.form.get("email") or "").strip().lower()
    user = UserRepository(_db()).get_by_email(email) if "@" in email else None
    if user is not None and user.is_active and user.is_external:
        try:
            token = _create_magic_link_token(user.email)
            GraphMailer(_cfg().tenant_id, _cfg().client_id, _cfg().client_secret).send(
                sender=_cfg().email_from,
                to=[user.email],
                subject="Your Sales Reports sign-in link",
                body_text=(
                    "Use this one-time link to sign in to Sales Reports. "
                    f"It expires in {_MAGIC_LINK_TTL_MINUTES} minutes.\n\n{_magic_link_url(token)}"
                ),
            )
        except GraphMailError:
            log.exception("Could not send external magic-link email")
        except Exception:
            log.exception("Unexpected external magic-link error")
    flash("If that email is registered as an active external account, you'll get a sign-in link in a minute.", "info")
    return redirect(url_for("auth.login_page"))


@auth_bp.get("/login/magic-link/<token>")
def consume_magic_link(token: str):
    """Consume one token and re-check the v3 account before granting a session."""
    email = _consume_magic_link_token(token)
    user = UserRepository(_db()).get_by_email(email) if email else None
    if user is None or not user.is_active or not user.is_external:
        flash("That sign-in link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("auth.login_page"))
    _login_or_403(user, name=user.display_name or user.email, is_dev=user.role == "developer")
    return redirect(url_for("reports.reports_list"))


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
    user = UserRepository(_db()).get_by_email(result["email"])
    if user is None or not user.is_active:
        return render_template("unauthorized.html"), 403
    is_dev = user.role == "developer"
    _login_or_403(user, name=user.display_name or result["name"], is_dev=is_dev)
    dest = session.pop(_NEXT_KEY, None) or url_for("health.healthz")
    return redirect(dest)


@auth_bp.post("/logout")
def logout_route():
    cfg = _cfg()
    logout()
    if cfg.is_beta:
        # Shared cookie: clear Live identity too, then the home login page.
        session.pop("user", None)
        session.clear()
        return redirect("/login")
    return redirect(url_for("auth.login_page"))


def _role_picker_users() -> list[dict]:
    """Active v3 users only — POST impersonation requires an active v3 row."""
    return [
        {
            "email": user.email,
            "display_name": user.display_name or user.email,
            "role": user.role,
            "salesman_key": "",
        }
        for user in UserRepository(_db()).all_users(include_inactive=False)
    ]


def _group_users(rows: list[dict]) -> dict[str, list]:
    grouped: dict[str, list] = {"admin": [], "developer": [], "manager": [], "salesman": []}
    for u in rows:
        grouped.setdefault(u.get("role") or "salesman", []).append(u)
    return grouped


@auth_bp.route("/dev/role-picker", methods=["GET", "POST"])
def role_picker():
    """Live-style impersonation: pick any user, or view as yourself."""
    from web.auth.session import current_principal
    from web.beta_live_session import adopt_live_identity

    p = adopt_live_identity() or current_principal()
    if p is None:
        return redirect(url_for("auth.login_page"))

    live = session.get("user") if isinstance(session.get("user"), dict) else {}
    dev_email = str(live.get("_dev_email") or p.real_email or p.email).strip().lower()
    actor = UserRepository(_db()).get_by_email(dev_email)
    if not Authorization.is_active_developer_row(actor):
        return redirect(url_for("reports.reports_list"))
    raw_name = str(live.get("_dev_name") or p.real_name or p.name)
    dev_name = raw_name.split(" (as ")[0] if " (as " in raw_name else raw_name

    if request.method == "POST":
        target_email = (request.form.get("target_email") or "").strip()
        get_setting = None
        try:
            from webapp.db import get_setting as _gs
            get_setting = _gs
        except ImportError:
            pass
        except Exception:  # noqa: BLE001 - Beta DB is enough if Live isn't on path
            current_app.logger.exception("role picker: Live db helpers unavailable")

        if target_email == "__self__":
            session["user"] = {
                "email": dev_email,
                "name": dev_name,
                "role": "admin",
                "salesman_key": None,
                "_dev": True,
                "_dev_name": dev_name,
                "_dev_email": dev_email,
            }
            if get_setting is not None:
                try:
                    session["theme"] = get_setting(dev_email, "theme", "light")
                except Exception:  # noqa: BLE001 - theme is optional
                    pass
        else:
            row = UserRepository(_db()).get_by_email(target_email.lower())
            if row is None or not row.is_active:
                abort(404, description="User not found")
            display = row.display_name or row.email
            session["user"] = {
                "email": row.email,
                "name": f"{display} (as {dev_name})",
                "role": row.role,
                "salesman_key": None,
                "_dev": True,
                "_dev_name": dev_name,
                "_dev_email": dev_email,
            }
            if get_setting is not None:
                try:
                    session["theme"] = get_setting(row.email, "theme", "light")
                except Exception:  # noqa: BLE001 - theme is optional
                    pass
        session.pop("v3_user", None)
        adopt_live_identity()
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


# --- Impersonation (developer-only, /test; home uses /dev/role-picker) ----- #

@auth_bp.get("/impersonate")
def impersonate_page():
    """User picker for developer impersonation on /test."""
    from web.auth.session import current_principal

    p = current_principal()
    if p is None:
        return redirect(url_for("auth.login_page"))
    if p.impersonating:
        abort(400, description="Cannot nest impersonation; end the current session first")
    authz = current_app.config["AUTHZ"]
    if not authz.is_developer(p):
        abort(403, description="Impersonation is developer only")

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
    if not authz.is_developer(p):
        abort(403, description="Impersonation is developer only")

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
