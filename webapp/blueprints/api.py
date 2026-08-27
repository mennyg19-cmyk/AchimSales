"""
API blueprint.

All ``/api/...`` endpoints: notifications, settings, users, saved reports,
dashboard refresh, customer list, and reload-users.
"""

import logging
import sqlite3
import threading

from flask import Blueprint, jsonify, request, session

from webapp.helpers import get_current_user, require_login
from webapp.services.access import user_can_access_customer, visible_salesman_keys
from webapp.user_map import get_salesman_key, is_admin, is_developer
from webapp.db import (
    normalize_key,
    get_notification_counts, get_notifications,
    dismiss_notification, dismiss_notifications_by_type,
    dismiss_all_notifications,
    get_excluded_customers, set_excluded_customers,
    get_all_users,
    add_user as db_add_user,
    update_user as db_update_user,
    delete_user as db_delete_user,
    get_saved_reports, add_saved_report, delete_saved_report,
    set_setting,
    get_all_salesmen_db, update_salesman_db, add_salesman_db, delete_salesman_db,
    get_report_config_all, set_report_enabled,
    set_user_report_override, delete_user_report_override,
    get_all_feature_flags, set_feature_flag,
    set_user_dashboard,
    set_user_test_access,
    set_user_beta_access,
    get_user_salesman_access, set_user_salesman_access,
    create_draft_order, get_draft_orders, get_draft_order,
    update_draft_order, delete_draft_order,
    get_draft_order_lines, add_draft_order_line,
    update_draft_order_line, delete_draft_order_line,
    get_customer_addresses, add_customer_address,
    get_cached_customer_list,
)
from webapp.services.d365 import (
    fetch_customers_for_api, fetch_items_for_order, fetch_item_by_upc,
    fetch_item_variants, fetch_customer_price, fetch_ship_methods,
)

log = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


# -- Customers ------------------------------------------------------------

@api_bp.route("/api/customers")
@require_login
def api_customers():
    user = get_current_user()
    keys = visible_salesman_keys(user, request.args.get("salesman"))
    if keys is not None and not keys:
        return jsonify([])

    salesman_key = next(iter(keys)) if keys is not None and len(keys) == 1 else None
    cached = get_cached_customer_list(salesman_key)
    if keys is not None and len(keys) > 1:
        cached = [
            c for c in cached
            if normalize_key(c.get("sales_group") or "") in keys
        ]
    if cached:
        return jsonify([
            {"account": c["customer_account"], "name": c["customer_name"]}
            for c in cached
        ])

    try:
        customers = fetch_customers_for_api(salesman_key)
        if keys is not None and len(keys) > 1:
            customers = [
                c for c in customers
                if normalize_key(c.get("sales_group") or "") in keys
            ]
        return jsonify([{"account": c["account"], "name": c["name"]} for c in customers])
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

    if data.get("all"):
        dismiss_all_notifications(email)
    elif "id" in data:
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
    is_external = bool(data.get("is_external", False))

    if not email or "@" not in email:
        return jsonify({"error": "Valid email is required"}), 400
    if role not in ("admin", "salesman", "developer", "manager"):
        return jsonify({"error": "Role must be admin, salesman, manager, or developer"}), 400
    if role == "salesman" and not salesman_key:
        return jsonify({"error": "Salesman key is required for salesman role"}), 400
    if is_external and role != "salesman":
        return jsonify({"error": "External (magic-link) login is only for salesmen"}), 400

    ok = db_add_user(email, role, salesman_key, display_name, is_external=is_external)
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
    new_email = (data.get("new_email") or "").strip().lower() or None
    is_external = data.get("is_external")
    if is_external is not None:
        is_external = bool(is_external)

    if role not in ("admin", "salesman", "developer", "manager"):
        return jsonify({"error": "Role must be admin, salesman, manager, or developer"}), 400
    if role == "salesman" and not salesman_key:
        return jsonify({"error": "Salesman key is required for salesman role"}), 400
    if is_external and role != "salesman":
        return jsonify({"error": "External (magic-link) login is only for salesmen"}), 400
    if new_email and "@" not in new_email:
        return jsonify({"error": "New email must be a valid address"}), 400

    try:
        ok = db_update_user(email, role, salesman_key, display_name,
                            is_external=is_external, new_email=new_email)
    except sqlite3.IntegrityError as exc:
        return jsonify({"error": str(exc)}), 409
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
    result = db_delete_user(email)
    if not result.get("existed"):
        return jsonify({"error": "User not found"}), 404
    return jsonify({"success": True, "deleted_rows": result.get("deleted_rows", {})})


# -- User-salesman access (manager role) -----------------------------------

@api_bp.route("/api/admin/user-salesman-access/<path:email>", methods=["GET"])
@require_login
def api_get_user_salesman_access(email):
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    keys = get_user_salesman_access(email)
    return jsonify({"email": email.lower().strip(), "salesman_keys": keys})


@api_bp.route("/api/admin/user-salesman-access", methods=["POST"])
@require_login
def api_set_user_salesman_access():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    email = (data.get("email") or "").lower().strip()
    keys = data.get("salesman_keys", [])
    if not email:
        return jsonify({"error": "Email is required"}), 400
    set_user_salesman_access(email, keys)
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
    from webapp.dashboard_data import (
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
    from webapp.dashboard_data import get_refresh_status
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


# -- Admin: Salesmen management --------------------------------------------

@api_bp.route("/api/admin/salesmen")
@require_login
def api_admin_salesmen():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    return jsonify({"salesmen": get_all_salesmen_db()})


@api_bp.route("/api/admin/salesmen", methods=["POST"])
@require_login
def api_admin_add_salesman():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    key = (data.get("key") or "").strip().lower()
    number = (data.get("number") or "").strip()
    full_name = (data.get("full_name") or "").strip()
    display_name = (data.get("display_name") or "").strip() or full_name
    if not key or not number or not full_name:
        return jsonify({"error": "key, number, and full_name are required"}), 400
    ok = add_salesman_db(key, number, full_name, display_name)
    if not ok:
        return jsonify({"error": "Salesman key already exists"}), 409
    return jsonify({"success": True})


@api_bp.route("/api/admin/salesmen/<path:key>", methods=["PUT"])
@require_login
def api_admin_update_salesman(key):
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    ok = update_salesman_db(key, **data)
    if not ok:
        return jsonify({"error": "Not found or no changes"}), 404
    return jsonify({"success": True})


@api_bp.route("/api/admin/salesmen/<path:key>", methods=["DELETE"])
@require_login
def api_admin_delete_salesman(key):
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    ok = delete_salesman_db(key)
    if not ok:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


# -- Admin: Report visibility ----------------------------------------------

@api_bp.route("/api/admin/reports/visibility", methods=["POST"])
@require_login
def api_admin_set_report_visibility():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    report_key = data.get("report_key", "")
    enabled = data.get("enabled", True)
    if not report_key:
        return jsonify({"error": "report_key is required"}), 400
    set_report_enabled(report_key, enabled)
    return jsonify({"success": True})


# -- Admin: Per-user report overrides --------------------------------------

@api_bp.route("/api/admin/user-report-access", methods=["POST"])
@require_login
def api_admin_set_user_report_access():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    report_key = data.get("report_key", "")
    allowed = data.get("allowed")
    if not email or not report_key:
        return jsonify({"error": "email and report_key are required"}), 400
    if allowed is None:
        delete_user_report_override(email, report_key)
    else:
        set_user_report_override(email, report_key, bool(allowed))
    return jsonify({"success": True})


# -- Admin: Feature flags --------------------------------------------------

@api_bp.route("/api/admin/feature-flags")
@require_login
def api_admin_feature_flags():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    return jsonify({"flags": get_all_feature_flags()})


@api_bp.route("/api/admin/feature-flags", methods=["POST"])
@require_login
def api_admin_set_feature_flag():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    flag_key = data.get("flag_key", "")
    enabled = data.get("enabled", True)
    if not flag_key:
        return jsonify({"error": "flag_key is required"}), 400
    set_feature_flag(flag_key, bool(enabled))
    return jsonify({"success": True})


# -- Admin: Per-user dashboard toggle --------------------------------------

@api_bp.route("/api/admin/user-dashboard", methods=["POST"])
@require_login
def api_admin_set_user_dashboard():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    enabled = data.get("enabled", True)
    if not email:
        return jsonify({"error": "email is required"}), 400
    set_user_dashboard(email, bool(enabled))
    return jsonify({"success": True})


@api_bp.route("/api/admin/user-test-access", methods=["POST"])
@require_login
def api_admin_set_user_test_access():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    enabled = data.get("enabled", False)
    if not email:
        return jsonify({"error": "email is required"}), 400
    set_user_test_access(email, bool(enabled))
    return jsonify({"success": True})


@api_bp.route("/api/admin/user-beta-access", methods=["POST"])
@require_login
def api_admin_set_user_beta_access():
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    enabled = data.get("enabled", False)
    if not email:
        return jsonify({"error": "email is required"}), 400
    set_user_beta_access(email, bool(enabled))
    return jsonify({"success": True})


@api_bp.route("/api/dev/beta-sources", methods=["GET", "POST"])
@require_login
def api_dev_beta_sources():
    """Dev-only: read/write the Beta per-report SQL vs OData switch."""
    user = get_current_user()
    if not is_developer(user):
        return jsonify({"error": "forbidden"}), 403
    try:
        from pathlib import Path
        import importlib.util

        path = Path(__file__).resolve().parents[2] / "v3" / "web" / "beta_sources.py"
        spec = importlib.util.spec_from_file_location("beta_sources", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"beta_sources unavailable: {exc}"}), 500

    if request.method == "GET":
        return jsonify({"sources": mod.get_sources()})

    data = request.get_json() or {}
    sources = data.get("sources")
    if isinstance(sources, dict):
        return jsonify({"sources": mod.set_sources(sources)})
    report_key = (data.get("report_key") or "").strip()
    source = (data.get("source") or "").strip().lower()
    if not report_key or source not in ("sql", "odata"):
        return jsonify({"error": "report_key and source (sql|odata) required"}), 400
    try:
        mod.set_source(report_key, source)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"sources": mod.get_sources()})


# -- Order entry -----------------------------------------------------------

@api_bp.route("/api/orders", methods=["POST"])
@require_login
def api_create_order():
    user = get_current_user()
    data = request.get_json() or {}
    order_id = create_draft_order(
        user.get("email", ""),
        customer_account=data.get("customer_account"),
        customer_name=data.get("customer_name"),
        ship_date=data.get("ship_date"),
        delivery_address_id=data.get("delivery_address_id"),
        delivery_address_text=data.get("delivery_address_text"),
        ship_method=data.get("ship_method"),
        po_number=data.get("po_number"),
    )
    return jsonify({"success": True, "id": order_id})


@api_bp.route("/api/orders/<int:order_id>", methods=["PUT"])
@require_login
def api_update_order(order_id):
    user = get_current_user()
    data = request.get_json() or {}
    ok = update_draft_order(order_id, user.get("email", ""), **data)
    if not ok:
        return jsonify({"error": "Order not found or no changes"}), 404
    return jsonify({"success": True})


@api_bp.route("/api/orders/<int:order_id>", methods=["DELETE"])
@require_login
def api_delete_order(order_id):
    user = get_current_user()
    ok = delete_draft_order(order_id, user.get("email", ""))
    if not ok:
        return jsonify({"error": "Order not found"}), 404
    return jsonify({"success": True})


@api_bp.route("/api/orders/<int:order_id>/lines")
@require_login
def api_get_order_lines(order_id):
    user = get_current_user()
    order = get_draft_order(order_id, user_email=user.get("email", ""))
    if not order:
        return jsonify({"error": "Order not found"}), 404
    lines = get_draft_order_lines(order_id)
    return jsonify({"lines": lines})


@api_bp.route("/api/orders/<int:order_id>/lines", methods=["POST"])
@require_login
def api_add_order_line(order_id):
    user = get_current_user()
    order = get_draft_order(order_id, user_email=user.get("email", ""))
    if not order:
        return jsonify({"error": "Order not found"}), 404
    data = request.get_json() or {}
    line_id = add_draft_order_line(order_id, **data)
    return jsonify({"success": True, "id": line_id})


@api_bp.route("/api/orders/<int:order_id>/lines/<int:line_id>", methods=["PUT"])
@require_login
def api_update_order_line(order_id, line_id):
    user = get_current_user()
    order = get_draft_order(order_id, user_email=user.get("email", ""))
    if not order:
        return jsonify({"error": "Order not found"}), 404
    data = request.get_json() or {}
    ok = update_draft_order_line(line_id, order_id, **data)
    if not ok:
        return jsonify({"error": "Line not found or no changes"}), 404
    return jsonify({"success": True})


@api_bp.route("/api/orders/<int:order_id>/lines/<int:line_id>", methods=["DELETE"])
@require_login
def api_delete_order_line(order_id, line_id):
    user = get_current_user()
    order = get_draft_order(order_id, user_email=user.get("email", ""))
    if not order:
        return jsonify({"error": "Order not found"}), 404
    ok = delete_draft_order_line(line_id, order_id)
    if not ok:
        return jsonify({"error": "Line not found"}), 404
    return jsonify({"success": True})


@api_bp.route("/api/orders/<int:order_id>/submit", methods=["POST"])
@require_login
def api_submit_order(order_id):
    user = get_current_user()
    email = user.get("email", "")
    order = get_draft_order(order_id, user_email=email)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    missing = []
    if not order.get("customer_account"):
        missing.append("Customer")
    if not order.get("ship_date"):
        missing.append("Ship date")
    if not order.get("delivery_address_text") and not order.get("delivery_address_id"):
        missing.append("Delivery address")
    if not order.get("ship_method"):
        missing.append("Ship method")
    if not order.get("po_number"):
        missing.append("PO number")

    lines = get_draft_order_lines(order_id)
    if not lines:
        missing.append("At least one line item")

    if missing:
        return jsonify({"error": "Missing required fields", "missing": missing}), 400

    update_draft_order(order_id, email, status="submitted")
    return jsonify({"success": True})


@api_bp.route("/api/items")
@require_login
def api_search_items():
    q = request.args.get("q", "").strip()
    customer = request.args.get("customer", "")
    items = fetch_items_for_order(q, customer_account=customer or None)
    return jsonify({"items": items})


@api_bp.route("/api/items/<path:item_number>/variants")
@require_login
def api_item_variants(item_number):
    data = fetch_item_variants(item_number)
    return jsonify(data)


@api_bp.route("/api/items/scan/<path:upc>")
@require_login
def api_scan_upc(upc):
    item = fetch_item_by_upc(upc)
    if not item:
        return jsonify({"error": "Item not found for this UPC"}), 404
    return jsonify(item)


@api_bp.route("/api/customer-addresses/<path:account>")
@require_login
def api_get_addresses(account):
    if not user_can_access_customer(get_current_user(), account):
        return jsonify({"error": "forbidden"}), 403
    addresses = get_customer_addresses(account)
    return jsonify({"addresses": addresses})


@api_bp.route("/api/customer-addresses/<path:account>", methods=["POST"])
@require_login
def api_add_address(account):
    if not user_can_access_customer(get_current_user(), account):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    address_id = (data.get("address_id") or "").strip()[:5]
    label = (data.get("label") or "").strip()
    street = (data.get("street") or "").strip()
    city = (data.get("city") or "").strip()
    state = (data.get("state") or "").strip()
    zip_code = (data.get("zip_code") or "").strip()
    country = (data.get("country") or "").strip()
    address_text = (data.get("address_text") or "").strip()
    is_default = data.get("is_default", False)

    if not address_text and street:
        parts = [street, city, state, zip_code, country]
        address_text = ", ".join(p for p in parts if p)
    if not address_text:
        return jsonify({"error": "address_text or street is required"}), 400
    if not label:
        label = address_text[:60]

    row_id = add_customer_address(
        account, label, address_text, is_default,
        street=street, city=city, state=state,
        zip_code=zip_code, country=country, source="manual",
        address_id=address_id,
    )
    return jsonify({"success": True, "id": row_id, "address_id": address_id})


@api_bp.route("/api/customer-price/<path:account>/<item_number>")
@require_login
def api_customer_price(account, item_number):
    if not user_can_access_customer(get_current_user(), account):
        return jsonify({"error": "forbidden"}), 403
    qty = request.args.get("qty", 1.0, type=float)
    result = fetch_customer_price(account, item_number, qty)
    return jsonify(result)


@api_bp.route("/api/ship-methods")
@require_login
def api_ship_methods():
    methods = fetch_ship_methods()
    return jsonify({"methods": methods})


@api_bp.route("/api/orders/generate-po/<path:account>", methods=["POST"])
@require_login
def api_generate_po(account):
    """Auto-generate an easy-to-remember PO number for a customer."""
    if not user_can_access_customer(get_current_user(), account):
        return jsonify({"error": "forbidden"}), 403
    from datetime import datetime
    import random
    initials = "".join(
        w[0].upper() for w in account.split() if w
    ) if not account.isdigit() else account[:4]
    date_part = datetime.now().strftime("%m%d")
    seq = random.randint(10, 99)
    po = f"{initials}-{date_part}-{seq}"
    return jsonify({"po_number": po})


# -- Cache debug (admin only) ---------------------------------------------

@api_bp.route("/api/admin/cache-status")
@require_login
def api_cache_status():
    """Show counts and sample rows from all cache tables."""
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "Admin only"}), 403

    from webapp.db import get_db, get_product_count, get_price_count
    conn = get_db()
    try:
        product_count = get_product_count()
        price_count = get_price_count()
        addr_count = conn.execute("SELECT COUNT(*) FROM customer_addresses").fetchone()[0]
        dashboard_count = conn.execute("SELECT COUNT(*) FROM dashboard_cache").fetchone()[0]

        product_sample = [dict(r) for r in conn.execute(
            "SELECT * FROM product_cache ORDER BY item_number LIMIT 10"
        ).fetchall()]

        price_sample = [dict(r) for r in conn.execute(
            "SELECT * FROM price_cache ORDER BY customer_account, item_number LIMIT 10"
        ).fetchall()]

        addr_sample = [dict(r) for r in conn.execute(
            "SELECT * FROM customer_addresses ORDER BY customer_account LIMIT 10"
        ).fetchall()]

        return jsonify({
            "counts": {
                "product_cache": product_count,
                "price_cache": price_count,
                "customer_addresses": addr_count,
                "dashboard_cache": dashboard_count,
            },
            "samples": {
                "product_cache": product_sample,
                "price_cache": price_sample,
                "customer_addresses": addr_sample,
            },
        })
    finally:
        conn.close()


# -- Order entry: refresh product/price cache on demand -------------------

@api_bp.route("/api/orders/refresh-cache", methods=["POST"])
@require_login
def api_refresh_order_cache():
    """Trigger a product + price cache refresh from D365 (runs in background)."""
    def _do_refresh():
        try:
            from config.settings import (
                get_client_id, get_client_secret, get_company_id,
                get_d365_env_url, get_tenant_id, validate_d365_config,
            )
            from core.auth import get_d365_token
            from webapp.dashboard_data import (
                _refresh_product_cache, _refresh_address_cache, _refresh_price_cache,
            )

            validate_d365_config()
            env_url = get_d365_env_url().rstrip("/")
            base_url = (
                f"{env_url}/data/"
                if "/data" not in env_url.lower()
                else (env_url if env_url.endswith("/") else f"{env_url}/")
            )
            token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), env_url)
            company = get_company_id() or None

            def _step(msg):
                log.info("Order cache refresh: %s", msg)

            _refresh_product_cache(base_url, token, company, _step)
            _refresh_address_cache(base_url, token, company, _step)
            _refresh_price_cache(base_url, token, company, _step)
            log.info("Order cache refresh completed successfully")
        except Exception:
            log.exception("Order cache refresh failed")

    threading.Thread(target=_do_refresh, daemon=True).start()
    return jsonify({"success": True, "message": "Refreshing product and pricing data from D365..."})


# -- Runbook history sync --------------------------------------------------

@api_bp.route("/api/admin/sync-runbook-history", methods=["POST"])
@require_login
def api_sync_runbook_history():
    """Sync runbook run history from Azure Automation + SharePoint run_log.csv."""
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "Admin only"}), 403

    def _do_sync():
        try:
            from webapp.dashboard_data import sync_runbook_history
            sync_runbook_history()
        except Exception:
            log.exception("Runbook history sync failed")

    threading.Thread(target=_do_sync, daemon=True).start()
    return jsonify({"success": True, "message": "Syncing runbook history..."})


@api_bp.route("/api/admin/runbook-history")
@require_login
def api_runbook_history():
    """Return runbook history as JSON (for the admin UI)."""
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "Admin only"}), 403
    from webapp.db import get_runbook_history, get_runbook_history_count
    count = get_runbook_history_count()
    rows = get_runbook_history(limit=500)
    return jsonify({"count": count, "rows": rows})


@api_bp.route("/api/admin/retry-job", methods=["POST"])
@require_login
def api_retry_job():
    """Retry a failed Azure Automation job with the same parameters."""
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "Admin only"}), 403

    data = request.get_json(silent=True) or {}
    report_name = data.get("report_name", "").strip()
    extra_args = data.get("extra_args", "").strip()

    if not report_name:
        return jsonify({"error": "Missing report_name"}), 400

    from webapp.user_map import REPORTS_CONFIG
    valid_reports = set(REPORTS_CONFIG.keys()) | {"all"}
    if report_name not in valid_reports:
        return jsonify({
            "error": (
                f"Unknown report '{report_name}'. This job was probably started by "
                f"an orphan Azure Automation schedule. Open Manage Schedules and "
                f"delete any entry whose Report shows '{report_name}'. "
                f"Valid reports: {', '.join(sorted(valid_reports))}"
            ),
        }), 400

    try:
        from webapp.services.azure_automation import start_job
        job_name = start_job(report_name=report_name, extra_args=extra_args)
        log.info("Retried job: report=%s args=%s -> new job %s", report_name, extra_args, job_name)
        return jsonify({"success": True, "job_name": job_name,
                        "message": f"Retry started as job {job_name[:8]}…"})
    except Exception as e:
        log.exception("Failed to retry job")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/admin/job-logs/<job_id>")
@require_login
def api_job_logs(job_id):
    """Fetch Azure Automation job logs on demand (not cached in DB).

    Returns {"output": str, "streams": [...]} so admins can inspect a run
    without bloating storage.
    """
    user = get_current_user()
    if not is_admin(user):
        return jsonify({"error": "Admin only"}), 403

    job_id = (job_id or "").strip()
    if not job_id:
        return jsonify({"error": "Missing job_id"}), 400

    try:
        from webapp.services.azure_automation import get_job_full_log
        result = get_job_full_log(job_id)
        return jsonify({"success": True, **result})
    except Exception as e:
        log.exception("Failed to fetch job logs for %s", job_id)
        return jsonify({"success": False, "error": str(e)}), 500
