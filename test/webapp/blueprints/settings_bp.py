"""Settings blueprint.

The page itself is rendered at ``/settings``. Everything interactive is
driven by XHR through the ``/api/settings/*`` endpoints so the page can be
loaded lightweight and the save-buttons never round-trip a form post.

Sections:
  * Appearance      -- theme (dark/light) + landing page + default reports tab
  * Customer excl.  -- per-user customer account blocklist
  * Admin           -- report run log, master schedules link, users & permissions

Admin tools require admin/developer privilege.
"""

from __future__ import annotations

import logging

from flask import Blueprint, abort, jsonify, render_template, request

from test.config.reports import REPORTS
from test.webapp.auth import current_user, is_admin as user_is_admin, require_admin, require_login
from test.webapp.db import (
    DEFAULT_PREFERENCES,
    VALID_ROLES,
    add_app_user,
    clear_user_report_override,
    delete_app_user,
    delete_salesman_record,
    get_report_run_log,
    get_user_exclusions,
    get_user_preferences,
    get_users_permission_grid,
    list_app_users,
    list_feature_flags,
    list_master_schedules,
    list_salesman_map,
    set_feature_flag,
    set_user_exclusions,
    set_user_preferences,
    set_user_report_override,
    set_user_salesman_access,
    update_app_user,
    upsert_salesman_record,
)
from test.webapp.services import reporting_api

log = logging.getLogger(__name__)

settings_bp = Blueprint("settings", __name__)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


@settings_bp.route("/settings")
@require_login
def index():
    user = current_user() or {}
    prefs = get_user_preferences(user.get("email", ""))
    exclusions = get_user_exclusions(user.get("email", ""))
    is_admin = user_is_admin(user)

    # Reports the perm grid should show. We use the full registry (incl.
    # disabled ones) so admins can pre-grant access ahead of go-live.
    report_keys = [r.key for r in REPORTS.values()]
    report_meta = [{"key": r.key, "name": r.name} for r in REPORTS.values()]

    admin_ctx = {}
    if is_admin:
        admin_ctx = {
            "feature_flags":    list_feature_flags(),
            "users":            list_app_users(),
            "master_schedules": list_master_schedules(),
            "reports":          [{"key": k, "name": r.name} for k, r in REPORTS.items()],
            "salesmen":         list_salesman_map(),
            "perm_grid":        get_users_permission_grid(report_keys),
            "report_meta":      report_meta,
            "valid_roles":      list(VALID_ROLES),
        }

    # Pull the customer list from the reporting API (cached). If the API
    # is unreachable, fall back to whatever exclusions the user has
    # already saved so the UI still renders rows for them.
    all_customers: list[dict] = []
    if reporting_api.is_configured():
        try:
            all_customers = reporting_api.list_customers()
        except Exception:
            log.exception("settings: list_customers from reporting API failed")
    if not all_customers and exclusions:
        all_customers = [{"key": c, "name": c} for c in exclusions]

    return render_template(
        "settings.html",
        active_tab="settings",
        prefs=prefs,
        exclusions=exclusions,
        all_customers=all_customers,
        is_admin=is_admin,
        admin=admin_ctx,
    )


# ---------------------------------------------------------------------------
# API: Preferences
# ---------------------------------------------------------------------------


@settings_bp.get("/api/settings/preferences")
@require_login
def api_get_prefs():
    u = current_user() or {}
    return jsonify(get_user_preferences(u.get("email", "")))


@settings_bp.post("/api/settings/preferences")
@require_login
def api_set_prefs():
    u = current_user() or {}
    body = request.get_json(silent=True) or {}
    allowed = set(DEFAULT_PREFERENCES.keys())
    prefs = {k: v for k, v in body.items() if k in allowed and v is not None}
    if "theme" in prefs and prefs["theme"] not in ("light", "dark"):
        return jsonify({"error": "invalid theme"}), 400
    if "landing_page" in prefs and prefs["landing_page"] not in ("reports", "dashboard", "schedules"):
        return jsonify({"error": "invalid landing_page"}), 400
    if "default_tab" in prefs and prefs["default_tab"] not in ("all", "presets"):
        return jsonify({"error": "invalid default_tab"}), 400
    set_user_preferences(u.get("email", ""), prefs)
    return jsonify({"ok": True, "prefs": get_user_preferences(u.get("email", ""))})


# ---------------------------------------------------------------------------
# API: Customer exclusions
# ---------------------------------------------------------------------------


@settings_bp.get("/api/settings/exclusions")
@require_login
def api_get_exclusions():
    u = current_user() or {}
    return jsonify({"exclusions": get_user_exclusions(u.get("email", ""))})


@settings_bp.post("/api/settings/exclusions")
@require_login
def api_set_exclusions():
    u = current_user() or {}
    body = request.get_json(silent=True) or {}
    accounts = body.get("accounts") or []
    if not isinstance(accounts, list):
        return jsonify({"error": "accounts must be a list"}), 400
    set_user_exclusions(u.get("email", ""), [str(a).strip() for a in accounts if str(a).strip()])
    return jsonify({"ok": True, "exclusions": get_user_exclusions(u.get("email", ""))})


@settings_bp.post("/api/settings/toggle-customer-exclusion")
@require_login
def api_toggle_customer_exclusion():
    u = current_user() or {}
    body = request.get_json(silent=True) or {}
    account = str(body.get("account") or "").strip()
    include = bool(body.get("include", True))
    if not account:
        return jsonify({"error": "account is required"}), 400

    exclusions = get_user_exclusions(u.get("email", ""))
    if include:
        exclusions = [a for a in exclusions if a != account]
    elif account not in exclusions:
        exclusions.append(account)
    set_user_exclusions(u.get("email", ""), exclusions)
    return jsonify({"success": True, "exclusions": get_user_exclusions(u.get("email", ""))})


# ---------------------------------------------------------------------------
# API: Admin -- feature flags
# ---------------------------------------------------------------------------


@settings_bp.post("/api/settings/admin/feature-flag")
@require_admin
def api_set_flag():
    body = request.get_json(silent=True) or {}
    key = (body.get("key") or "").strip()
    enabled = bool(body.get("enabled"))
    if not key:
        return jsonify({"error": "key is required"}), 400
    set_feature_flag(key, enabled)
    return jsonify({"ok": True, "flags": list_feature_flags()})


# ---------------------------------------------------------------------------
# API: Admin -- users & permissions
# ---------------------------------------------------------------------------


def _perm_grid_payload() -> dict:
    """Common payload returned after any user/permission mutation so the
    UI can re-render the table without a second round-trip."""
    report_keys = [r.key for r in REPORTS.values()]
    return {
        "users":      list_app_users(),
        "perm_grid":  get_users_permission_grid(report_keys),
        "salesmen":   list_salesman_map(),
        "report_meta":[{"key": r.key, "name": r.name} for r in REPORTS.values()],
    }


@settings_bp.get("/api/settings/admin/users")
@require_admin
def api_list_users():
    return jsonify({"ok": True, **_perm_grid_payload()})


@settings_bp.post("/api/settings/admin/users/add")
@require_admin
def api_add_user():
    """Add an admin / developer / manager user.

    Salesman users come in via ``/api/settings/admin/salesmen`` (which
    creates the salesman row + the linked user in one shot). Calling
    this endpoint with ``role='salesman'`` and no ``salesman_key`` is
    explicitly an error.
    """
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"error": "Valid email is required"}), 400
    role = (body.get("role") or "salesman").strip().lower()
    if role not in VALID_ROLES:
        return jsonify({"error": f"Role must be one of {VALID_ROLES}"}), 400
    salesman_key = (body.get("salesman_key") or "").strip() or None
    is_external = bool(body.get("is_external", False))
    display_name = (body.get("display_name") or "").strip() or None

    try:
        ok = add_app_user(
            email, role=role, salesman_key=salesman_key,
            display_name=display_name, is_external=is_external,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        # PersistSnapshotFailed (or any unexpected error) -- the
        # row is in /tmp but didn't make it to durable storage.
        # Tell the admin clearly instead of pretending it worked.
        from test.webapp.db import PersistSnapshotFailed
        if isinstance(e, PersistSnapshotFailed):
            log.error("add_app_user persisted to /tmp but snapshot to /home/data failed: %s", e)
            return jsonify({
                "error": (
                    "User added in memory but durable save failed -- the row "
                    "won't survive a restart. Check /test/diag/api/snapshot-status. "
                    f"Details: {e}"
                ),
                "stage": "persist",
            }), 500
        raise
    if not ok:
        return jsonify({"error": "User already exists"}), 409
    return jsonify({"ok": True, **_perm_grid_payload()})


@settings_bp.post("/api/settings/admin/users")
@require_admin
def api_update_user():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400

    kwargs: dict = {}
    if "display_name" in body:
        kwargs["display_name"] = (body.get("display_name") or None)
    if "role" in body:
        role = (body.get("role") or "").strip().lower()
        if role not in VALID_ROLES:
            return jsonify({"error": f"Role must be one of {VALID_ROLES}"}), 400
        kwargs["role"] = role
    if "salesman_key" in body:
        kwargs["salesman_key"] = (body.get("salesman_key") or "").strip() or None
    for f in ("is_admin", "sharepoint_access_enabled", "is_external",
              "active", "dashboard_enabled", "test_access_enabled"):
        if f in body:
            kwargs[f] = bool(body[f])
    if "new_email" in body:
        new_email = (body.get("new_email") or "").strip().lower() or None
        if new_email and "@" not in new_email:
            return jsonify({"error": "new_email must be a valid email"}), 400
        kwargs["new_email"] = new_email

    if not kwargs:
        return jsonify({"error": "no fields to update"}), 400

    me = (current_user() or {}).get("email", "").lower()
    if email == me:
        # Don't let an admin lock themselves out by demoting their own role
        # or clearing the admin flag.
        if kwargs.get("role") == "salesman":
            return jsonify({"error": "You cannot change your own role to salesman."}), 400
        if "is_admin" in kwargs and not kwargs["is_admin"]:
            return jsonify({"error": "You cannot remove your own admin access."}), 400

    if kwargs.get("role") == "salesman":
        # If they aren't simultaneously assigning a salesman_key, require
        # that one already exists.
        if "salesman_key" in kwargs:
            sk = kwargs["salesman_key"]
        else:
            from test.webapp.db import get_app_user as _g
            sk = (_g(email) or {}).get("salesman_key")
        if not sk:
            return jsonify({"error": "Salesman key is required for salesman role"}), 400

    try:
        update_app_user(email, **kwargs)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, **_perm_grid_payload()})


@settings_bp.post("/api/settings/admin/users/delete")
@require_admin
def api_delete_user():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400
    me = (current_user() or {}).get("email", "").lower()
    if email == me:
        return jsonify({"error": "You cannot delete your own account."}), 400
    delete_app_user(email)
    return jsonify({"ok": True, **_perm_grid_payload()})


# ---------------------------------------------------------------------------
# API: Admin -- per-user report access overrides
# ---------------------------------------------------------------------------


@settings_bp.post("/api/settings/admin/users/report-access")
@require_admin
def api_set_user_report_access():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    report_key = (body.get("report_key") or "").strip()
    if not email or not report_key:
        return jsonify({"error": "email and report_key are required"}), 400
    if "allowed" not in body:
        clear_user_report_override(email, report_key)
    else:
        set_user_report_override(email, report_key, bool(body.get("allowed")))
    return jsonify({"ok": True, **_perm_grid_payload()})


@settings_bp.post("/api/settings/admin/users/salesman-access")
@require_admin
def api_set_user_salesman_access():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    keys = body.get("keys") or []
    if not email:
        return jsonify({"error": "email is required"}), 400
    if not isinstance(keys, list):
        return jsonify({"error": "keys must be a list"}), 400
    set_user_salesman_access(email, [str(k) for k in keys])
    return jsonify({"ok": True, **_perm_grid_payload()})


# ---------------------------------------------------------------------------
# API: Admin -- salesman map (replaces salesman_map.xlsx for the test app)
# ---------------------------------------------------------------------------


@settings_bp.get("/api/settings/admin/salesmen")
@require_admin
def api_list_salesmen():
    return jsonify({"ok": True, "salesmen": list_salesman_map()})


@settings_bp.post("/api/settings/admin/salesmen")
@require_admin
def api_upsert_salesman():
    """Create or update a salesman row.

    Returns the merged perm_grid + salesmen list because adding a
    salesman implicitly creates/renames a user row and the UI needs
    both to re-render.
    """
    body = request.get_json(silent=True) or {}
    if not (body.get("key") or "").strip():
        return jsonify({"error": "key is required"}), 400
    try:
        upsert_salesman_record(body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, **_perm_grid_payload()})


@settings_bp.post("/api/settings/admin/salesmen/delete")
@require_admin
def api_delete_salesman():
    """Delete a salesman row + cascade-delete the linked user."""
    body = request.get_json(silent=True) or {}
    key = (body.get("key") or "").strip()
    if not key:
        return jsonify({"error": "key is required"}), 400
    ok = delete_salesman_record(key)
    if not ok:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"ok": True, **_perm_grid_payload()})


# ---------------------------------------------------------------------------
# API: Admin -- report run log
# ---------------------------------------------------------------------------


@settings_bp.get("/api/settings/admin/report-log")
@require_admin
def api_report_log():
    try:
        limit = max(1, min(int(request.args.get("limit", "200")), 2000))
    except ValueError:
        limit = 200
    user_filter = (request.args.get("user") or "").strip().lower() or None
    rows = get_report_run_log(limit=limit, user_email=user_filter)
    return jsonify({"rows": rows})
