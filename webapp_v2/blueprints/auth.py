"""
Authentication blueprint.

Routes: /, /login, /login/start, /dev-login, /auth/callback,
        /dev/role-picker, /logout
"""

import logging

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from webapp_v2.config import DEV_BYPASS_AUTH
from webapp_v2.helpers import get_current_user, get_salesmen_list, require_login
from webapp_v2.user_map import get_user, is_developer

log = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def index():
    if get_current_user():
        return redirect(url_for("reports.reports_list"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login")
def login():
    if get_current_user():
        return redirect(url_for("reports.reports_list"))
    if DEV_BYPASS_AUTH:
        return render_template("login_dev.html")
    return render_template("login.html")


@auth_bp.route("/login/start")
def login_start():
    """Redirect to Microsoft login."""
    if DEV_BYPASS_AUTH:
        return redirect(url_for("auth.dev_login"))
    try:
        from webapp_v2.auth import build_login_url
        auth_url = build_login_url()
        return redirect(auth_url)
    except Exception:
        log.exception("Failed to build login URL")
        flash("Could not connect to Microsoft login. Please try again.", "error")
        return redirect(url_for("auth.login"))


@auth_bp.route("/dev-login", methods=["GET", "POST"])
def dev_login():
    """Dev-only: bypass Microsoft login, pick a role to sign in as."""
    if not DEV_BYPASS_AUTH:
        return redirect(url_for("auth.login"))

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
        return redirect(url_for("reports.reports_list"))

    return render_template("login_dev.html", salesmen=get_salesmen_list())


@auth_bp.route("/auth/callback", methods=["GET", "POST"])
def auth_callback():
    """Handle the redirect from Microsoft after login."""
    from webapp_v2.auth import complete_login
    ms_user = complete_login()
    if not ms_user:
        flash("Login failed. Please try again.", "error")
        return redirect(url_for("auth.login"))

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
        }
        from webapp_v2.db import get_setting
        session["theme"] = get_setting(email, "theme", "light")
        return redirect(url_for("auth.role_picker"))

    session["user"] = {
        "email": email,
        "name": ms_user.get("name", email),
        "role": user_info["role"],
        "salesman_key": user_info.get("salesman_key"),
    }
    from webapp_v2.db import get_setting
    session["theme"] = get_setting(email, "theme", "light")
    return redirect(url_for("reports.reports_list"))


@auth_bp.route("/dev/role-picker", methods=["GET", "POST"])
@require_login
def role_picker():
    """Let authenticated developers pick a role to impersonate."""
    user = get_current_user()
    if not is_developer(user) and not user.get("_dev"):
        return redirect(url_for("reports.reports_list"))

    if request.method == "POST":
        role = request.form.get("role", "admin")
        real_email = user.get("email", "")
        raw_name = user.get("_dev_name") or user.get("name", real_email)
        dev_name = raw_name.split(" (as ")[0] if " (as " in raw_name else raw_name

        if role == "admin":
            session["user"] = {
                "email": real_email,
                "name": dev_name,
                "role": "admin",
                "salesman_key": None,
                "_dev": True,
                "_dev_name": dev_name,
            }
        else:
            sm_key = request.form.get("salesman_key", "")
            from config.salesman_map import lookup_salesman
            _, full_name, display_name = lookup_salesman(sm_key)
            session["user"] = {
                "email": real_email,
                "name": f"{full_name} (as {dev_name})",
                "role": "salesman",
                "salesman_key": sm_key,
                "_dev": True,
                "_dev_name": dev_name,
            }
        return redirect(url_for("reports.reports_list"))

    return render_template("role_picker.html", user=user,
                           salesmen=get_salesmen_list(user.get("email")))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
