"""
API blueprint.

All ``/api/...`` endpoints: notifications, settings, users, saved reports,
dashboard refresh, customer list, and reload-users.
"""

import logging
import threading

from flask import Blueprint, jsonify, request, session

from webapp_v2.helpers import get_current_user, require_login
from webapp_v2.user_map import get_salesman_key, is_admin, is_salesman, reload_map
from webapp_v2.db import (
    get_notification_counts, get_notifications,
    dismiss_notification, dismiss_notifications_by_type,
    get_excluded_customers, set_excluded_customers,
    get_excluded_salesmen, set_excluded_salesmen,
    get_all_users,
    add_user as db_add_user,
    update_user as db_update_user,
    delete_user as db_delete_user,
    get_saved_reports, add_saved_report, delete_saved_report,
    set_setting,
)
from webapp_v2.services.d365 import fetch_customers_for_api

log = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


# -- Customers ------------------------------------------------------------

@api_bp.route("/api/customers")
@require_login
def api_customers():
    user = get_current_user()
    salesman_key = None
    if is_salesman(user):
        salesman_key = user.get("salesman_key")
    elif is_admin(user) and request.args.get("salesman"):
        salesman_key = request.args.get("salesman")

    try:
        customers = fetch_customers_for_api(salesman_key)
        return jsonify(customers)
    except Exception:
        log.exception("Failed to fetch customers")
        return jsonify([]), 500


# -- Notifications --------------------------------------------------------

@api_bp.route("/api/notifications")
@require_login
def api_notifications():
    user = get_current_user()
    email = user.get("email", "")
    counts = get_notification_counts(email)
    items = get_notifications(email, dismissed=False)
    return jsonify({
        "report_ready_count": counts.get("report_ready", 0),
        "overdue_count": counts.get("overdue_customer", 0),
        "total": counts.get("total", 0),
        "items": items,
    })


@api_bp.route("/api/notifications/dismiss", methods=["POST"])
@require_login
def api_notifications_dismiss():
    user = get_current_user()
    email = user.get("email", "")
    data = request.get_json() or {}

    if "id" in data:
        try:
            nid = int(data["id"])
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid notification id"}), 400
        dismiss_notification(nid, user_email=email)
    elif "type" in data:
        dismiss_notifications_by_type(email, data["type"])

    return jsonify({"success": True})


# -- Settings: customer exclusions ----------------------------------------

@api_bp.route("/api/settings/excluded-customers", methods=["POST"])
@require_login
def api_excluded_customers():
    user = get_current_user()
    data = request.get_json() or {}
    accounts = data.get("accounts", [])
    set_excluded_customers(user.get("email", ""), accounts)
    return jsonify({"success": True})


@api_bp.route("/api/settings/toggle-customer-exclusion", methods=["POST"])
@require_login
def api_toggle_customer_exclusion():
    user = get_current_user()
    data = request.get_json() or {}
    account = data.get("account", "")
    include = data.get("include", True)
    email = user.get("email", "")

    excluded = get_excluded_customers(email)
    if include:
        excluded = [a for a in excluded if a != account]
    else:
        if account not in excluded:
            excluded.append(account)
    set_excluded_customers(email, excluded)
    return jsonify({"success": True})


# -- Settings: salesman exclusions ----------------------------------------

@api_bp.route("/api/settings/excluded-salesmen", methods=["POST"])
@require_login
def api_excluded_salesmen():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    keys = data.get("keys", [])
    set_excluded_salesmen(user.get("email", ""), keys)
    return jsonify({"success": True})


# -- Settings: theme ------------------------------------------------------

@api_bp.route("/api/settings/theme", methods=["POST"])
@require_login
def api_set_theme():
    user = get_current_user()
    data = request.get_json() or {}
    theme = data.get("theme", "light")
    set_setting(user.get("email", ""), "theme", theme)
    session["theme"] = theme
    return jsonify({"success": True})


# -- User management ------------------------------------------------------

@api_bp.route("/api/users", methods=["GET"])
@require_login
def api_list_users():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    return jsonify({"users": get_all_users()})


@api_bp.route("/api/users", methods=["POST"])
@require_login
def api_add_user():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    email = (data.get("email") or "").lower().strip()
    role = data.get("role", "salesman")
    salesman_key = data.get("salesman_key", "").strip() or None
    display_name = data.get("display_name", "").strip() or None

    if not email or "@" not in email:
        return jsonify({"error": "Valid email is required"}), 400
    if role not in ("admin", "salesman", "developer"):
        return jsonify({"error": "Role must be admin, salesman, or developer"}), 400
    if role == "salesman" and not salesman_key:
        return jsonify({"error": "Salesman key is required for salesman role"}), 400

    ok = db_add_user(email, role, salesman_key, display_name)
    if not ok:
        return jsonify({"error": "User already exists"}), 409
    return jsonify({"success": True})


@api_bp.route("/api/users/<path:email>", methods=["PUT"])
@require_login
def api_update_user(email):
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    role = data.get("role", "salesman")
    salesman_key = data.get("salesman_key", "").strip() or None
    display_name = data.get("display_name", "").strip() or None

    if role not in ("admin", "salesman", "developer"):
        return jsonify({"error": "Role must be admin, salesman, or developer"}), 400
    if role == "salesman" and not salesman_key:
        return jsonify({"error": "Salesman key is required for salesman role"}), 400

    ok = db_update_user(email, role, salesman_key, display_name)
    if not ok:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"success": True})


@api_bp.route("/api/users/<path:email>", methods=["DELETE"])
@require_login
def api_delete_user(email):
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    if email.lower().strip() == user.get("email", "").lower().strip():
        return jsonify({"error": "Cannot delete yourself"}), 400
    ok = db_delete_user(email)
    if not ok:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"success": True})


# -- Saved reports (presets) -----------------------------------------------

@api_bp.route("/api/saved-reports", methods=["GET"])
@require_login
def api_list_saved_reports():
    user = get_current_user()
    return jsonify({"presets": get_saved_reports(user.get("email", ""))})


@api_bp.route("/api/saved-reports", methods=["POST"])
@require_login
def api_save_report():
    user = get_current_user()
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    report_key = data.get("report_key", "")
    report_name = data.get("report_name", "")
    params = data.get("params", {})
    for_user_email = (data.get("for_user_email") or "").strip()

    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not report_key:
        return jsonify({"error": "Report key is required"}), 400

    target_email = user.get("email", "")
    if for_user_email and for_user_email != target_email:
        if not is_admin(user):
            return jsonify({"error": "Only admins/devs can save presets for other users"}), 403
        target_email = for_user_email

    preset_id = add_saved_report(target_email, name, report_key, report_name, params)
    return jsonify({"success": True, "id": preset_id})


@api_bp.route("/api/saved-reports/<int:preset_id>", methods=["DELETE"])
@require_login
def api_delete_saved_report(preset_id):
    user = get_current_user()
    ok = delete_saved_report(preset_id, user.get("email", ""))
    if not ok:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


# -- Dashboard refresh -----------------------------------------------------

@api_bp.route("/api/dashboard/refresh", methods=["POST"])
@require_login
def api_dashboard_refresh():
    from webapp_v2.dashboard_data import (
        refresh_cache, get_last_refresh, mark_refresh_requested,
    )
    user = get_current_user()
    salesman_key = get_salesman_key(user)
    before = get_last_refresh() or ""
    requested_at = mark_refresh_requested()

    def _do_refresh():
        try:
            refresh_cache(salesman_key=salesman_key)
        except Exception:
            log.exception("Manual dashboard refresh failed")

    threading.Thread(target=_do_refresh, daemon=True).start()
    return jsonify({
        "success": True, "started": True,
        "before": before, "requested_at": requested_at,
    })


@api_bp.route("/api/dashboard/refresh-status")
@require_login
def api_dashboard_refresh_status():
    from webapp_v2.dashboard_data import get_refresh_status
    user = get_current_user()
    salesman_key = get_salesman_key(user)
    before = request.args.get("before", "")
    status = get_refresh_status(salesman_key=salesman_key)
    current = status["last_completed"] or ""
    done = bool(current and current != before)
    return jsonify({
        "done": done,
        "running": status["running"],
        "step": status.get("step", ""),
        "last_requested": status["last_requested"],
        "last_completed": current,
    })


# -- Reload users ----------------------------------------------------------

@api_bp.route("/api/reload-users", methods=["POST"])
@require_login
def api_reload_users():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "Admin only"}), 403
    reload_map()
    return jsonify({"success": True})
