"""
Authentication blueprint.

Routes: /, /login, /login/start, /dev-login, /auth/callback,
        /dev/role-picker, /logout
"""

import logging
import os
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from webapp.config import _dev_bypass_enabled
from webapp.helpers import get_current_user, get_salesmen_list, require_login
from webapp.user_map import get_user, is_developer

log = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

_LOGIN_NEXT_KEY = "login_next"


def _safe_next(raw: str | None) -> str | None:
    """Same-site relative path only (supports /legacy and leftover /beta next)."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw.startswith("/") or raw.startswith("//") or raw.startswith("/\\"):
        return None
    parts = urlsplit(raw)
    if parts.scheme or parts.netloc:
        return None
    return raw


def _remember_next(raw: str | None = None) -> None:
    nxt = _safe_next(raw if raw is not None else request.args.get("next"))
    if nxt:
        session[_LOGIN_NEXT_KEY] = nxt


def _redirect_after_login():
    nxt = _safe_next(session.pop(_LOGIN_NEXT_KEY, None))
    if nxt:
        return redirect(nxt)
    return redirect("/")


@auth_bp.route("/")
def index():
    if get_current_user():
        return redirect(url_for("reports.reports_list"))
    return redirect("/login")


@auth_bp.route("/login")
def login():
    _remember_next()
    if get_current_user():
        return _redirect_after_login()
    if _dev_bypass_enabled():
        return render_template("login_dev.html")
    return render_template("login.html")


@auth_bp.route("/login/start")
def login_start():
    """Redirect to Microsoft login."""
    _remember_next()
    if _dev_bypass_enabled():
        return redirect(url_for("auth.dev_login"))
    try:
        from webapp.auth import build_login_url
        auth_url = build_login_url()
        return redirect(auth_url)
    except Exception:
        log.exception("Failed to build login URL")
        flash("Could not connect to Microsoft login. Please try again.", "error")
        return redirect("/login")


@auth_bp.route("/dev-login", methods=["GET", "POST"])
def dev_login():
    """Dev-only: bypass Microsoft login, pick a role to sign in as."""
    if not _dev_bypass_enabled():
        return redirect("/login")

    if request.method == "POST":
        role = request.form.get("role", "admin")
        if role == "admin":
            session["user"] = {
                "email": "dev-admin@localhost",
                "name": "Dev Admin",
                "role": "admin",
                "salesman_key": None,
            }
        else:
            sm_key = request.form.get("salesman_key", "mkolko")
            from config.salesman_map import lookup_salesman
            _, full_name, display_name = lookup_salesman(sm_key)
            session["user"] = {
                "email": f"dev-{sm_key}@localhost",
                "name": full_name,
                "role": "salesman",
                "salesman_key": sm_key,
            }
        return _redirect_after_login()

    return render_template("login_dev.html", salesmen=get_salesmen_list())


@auth_bp.route("/auth/callback", methods=["GET", "POST"])
def auth_callback():
    """Handle the redirect from Microsoft after login."""
    from webapp.auth import complete_login
    ms_user = complete_login()
    if not ms_user:
        flash("Login failed. Please try again.", "error")
        return redirect("/login")

    email = ms_user.get("email", "")
    user_info = get_user(email)
    if not user_info:
        return render_template("unauthorized.html", email=email)

    if is_developer(user_info):
        dev_name = ms_user.get("name", email)
        session["user"] = {
            "email": email,
            "name": dev_name,
            "role": "developer",
            "salesman_key": None,
            "_dev": True,
            "_dev_name": dev_name,
            "_dev_email": email,
        }
        from webapp.db import get_setting
        session["theme"] = get_setting(email, "theme", "light")
        return redirect(url_for("auth.role_picker"))

    session["user"] = {
        "email": email,
        "name": ms_user.get("name", email),
        "role": user_info["role"],
        "salesman_key": user_info.get("salesman_key"),
    }
    from webapp.db import get_setting
    session["theme"] = get_setting(email, "theme", "light")
    return _redirect_after_login()


@auth_bp.route("/dev/role-picker", methods=["GET", "POST"])
@require_login
def role_picker():
    """Let authenticated developers impersonate any registered user."""
    user = get_current_user()
    if not is_developer(user) and not user.get("_dev"):
        return _redirect_after_login()

    dev_email = user.get("_dev_email") or user.get("email", "")
    raw_name = user.get("_dev_name") or user.get("name", dev_email)
    dev_name = raw_name.split(" (as ")[0] if " (as " in raw_name else raw_name

    if request.method == "POST":
        from webapp.db import get_setting, get_user_by_email
        target_email = request.form.get("target_email", "").strip()

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
            session["theme"] = get_setting(dev_email, "theme", "light")
            return _redirect_after_login()

        target = get_user_by_email(target_email)
        if not target:
            flash("User not found.", "error")
            return redirect(url_for("auth.role_picker"))

        display = target.get("display_name") or target["email"]
        session["user"] = {
            "email": target["email"],
            "name": f"{display} (as {dev_name})",
            "role": target["role"],
            "salesman_key": target.get("salesman_key"),
            "_dev": True,
            "_dev_name": dev_name,
            "_dev_email": dev_email,
        }
        session["theme"] = get_setting(target["email"], "theme", "light")
        return _redirect_after_login()

    from webapp.db import get_all_users
    all_users = get_all_users()
    grouped = {"admin": [], "developer": [], "manager": [], "salesman": []}
    for u in all_users:
        r = u.get("role", "salesman")
        grouped.setdefault(r, []).append(u)

    return render_template("role_picker.html", user=user,
                           grouped_users=grouped, dev_email=dev_email)


@auth_bp.route("/login/magic-link", methods=["POST"])
def request_magic_link():
    """Email an external sales rep a one-time sign-in link.

    Always shows the same generic flash message regardless of whether the
    email is in our system, so attackers can't enumerate registered users.
    """
    email = (request.form.get("email") or "").strip().lower()
    if not email or "@" not in email:
        flash("Please enter a valid email address.", "error")
        return redirect("/login")

    user = get_user(email)
    if user and user.get("role") == "salesman":
        from webapp.db import get_user_by_email, create_magic_link_token
        from webapp.services.magic_link import send_magic_link_email, MagicLinkError

        row = get_user_by_email(email) or {}
        if row.get("is_external"):
            try:
                token = create_magic_link_token(email)
                link_path = url_for("auth.consume_magic_link", token=token)
                public_base_url = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
                link_url = f"{public_base_url}{link_path}" if public_base_url else url_for(
                    "auth.consume_magic_link", token=token, _external=True)
                send_magic_link_email(email, link_url)
                log.info("Magic-link sent to %s", email)
            except MagicLinkError:
                log.exception("Magic-link send failed for %s", email)
            except Exception:
                log.exception("Unexpected magic-link error for %s", email)

    # Generic response: don't reveal whether the email is registered.
    flash("If that email is registered as an external sales rep, "
          "you'll get a sign-in link in a minute.", "info")
    return redirect("/login")


@auth_bp.route("/login/magic-link/<token>")
def consume_magic_link(token):
    """Consume a one-time login token and sign the user in."""
    from webapp.db import consume_magic_link_token, get_setting

    email = consume_magic_link_token(token)
    if not email:
        flash("That sign-in link is invalid or has expired. "
              "Please request a new one.", "error")
        return redirect("/login")

    user_info = get_user(email)
    if not user_info:
        log.warning("Magic-link token consumed for unknown email %s", email)
        flash("Account not found.", "error")
        return redirect("/login")

    session["user"] = {
        "email": email,
        "name": user_info.get("display_name") or email,
        "role": user_info["role"],
        "salesman_key": user_info.get("salesman_key"),
    }
    session["theme"] = get_setting(email, "theme", "light")
    log.info("Magic-link sign-in: %s", email)
    return _redirect_after_login()


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login")
