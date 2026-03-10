"""
Settings blueprint.

Routes: /settings
"""

import logging

from flask import Blueprint, render_template

from webapp_v2.helpers import get_current_user, require_login
from webapp_v2.user_map import get_salesman_key, is_admin
from webapp_v2.db import (
    get_cached_customer_list, get_excluded_customers,
    get_excluded_salesmen, get_all_users, get_setting,
)

log = logging.getLogger(__name__)

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings")
@require_login
def settings_page():
    user = get_current_user()
    salesman_key = get_salesman_key(user)
    email = user.get("email", "")
    excluded = get_excluded_customers(email)
    customers = get_cached_customer_list(salesman_key=salesman_key)

    show_admin_settings = is_admin(user)
    app_users = get_all_users() if show_admin_settings else []

    all_salesmen = []
    excluded_salesmen = []
    if show_admin_settings:
        try:
            from config.salesman_map import SALESMAN_MAP
            all_salesmen = [
                {"key": k, "name": v[1]}
                for k, v in SALESMAN_MAP.items()
                if v[0] != "?unassigned"
            ]
            all_salesmen.sort(key=lambda x: x["name"])
        except Exception:
            pass
        excluded_salesmen = get_excluded_salesmen(email)

    theme = get_setting(email, "theme", "light")

    return render_template(
        "settings.html", user=user, customers=customers,
        excluded=excluded, active_tab="settings",
        show_user_mgmt=show_admin_settings, app_users=app_users,
        show_admin_settings=show_admin_settings,
        all_salesmen=all_salesmen, excluded_salesmen=excluded_salesmen,
        theme=theme,
    )
