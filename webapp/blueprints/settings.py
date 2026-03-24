"""
Settings blueprint.

Routes: /settings
"""

import logging

from flask import Blueprint, render_template

from webapp.helpers import get_current_user, require_login
from webapp.user_map import get_salesman_key, is_admin
from webapp.db import (
    get_cached_customer_list, get_excluded_customers,
    get_all_users, get_setting,
    get_all_salesmen_db,
    get_report_config_all, get_all_feature_flags,
    get_users_permission_grid,
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
    perm_grid = []
    report_visibility = {}
    feature_flags = []
    if show_admin_settings:
        all_salesmen_rows = get_all_salesmen_db()
        all_salesmen = [
            {"key": s["key"], "name": s["full_name"], "number": s["number"],
             "display_name": s["display_name"], "active": s["active"]}
            for s in all_salesmen_rows
            if s["number"] != "?unassigned"
        ]
        all_salesmen.sort(key=lambda x: x["name"])
        perm_grid = get_users_permission_grid()
        report_visibility = get_report_config_all()
        feature_flags = get_all_feature_flags()

    from webapp.user_map import REPORTS_CONFIG
    theme = get_setting(email, "theme", "light")

    report_keys = list(REPORTS_CONFIG.keys())

    return render_template(
        "settings.html", user=user, customers=customers,
        excluded=excluded, active_tab="settings",
        show_user_mgmt=show_admin_settings, app_users=app_users,
        show_admin_settings=show_admin_settings,
        all_salesmen=all_salesmen,
        perm_grid=perm_grid,
        theme=theme, report_visibility=report_visibility,
        reports_config=REPORTS_CONFIG, feature_flags=feature_flags,
        report_keys=report_keys,
    )
