"""Settings blueprint.

The page itself is rendered at ``/settings``. Everything interactive is
driven by XHR through the ``/api/settings/*`` endpoints so the page can be
loaded lightweight and the save-buttons never round-trip a form post.

Sections:
  * Appearance      -- theme (dark/light) + landing page + default reports tab
  * Customer excl.  -- per-user customer account blocklist
  * Admin           -- report run log, master schedules link, users & permissions

Admin tools require ``current_user().is_admin``.
"""

from __future__ import annotations

import logging

from flask import Blueprint, abort, jsonify, render_template, request

from test.webapp.auth import current_user, require_admin, require_login
from test.webapp.db import (
    DEFAULT_PREFERENCES,
    delete_app_user,
    get_report_run_log,
    get_user_exclusions,
    get_user_preferences,
    list_app_users,
    list_feature_flags,
    list_master_schedules,
    set_feature_flag,
    set_user_exclusions,
    set_user_preferences,
    update_app_user,
)
from test.webapp.services.mock_data import CUSTOMERS

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
    is_admin = bool(user.get("is_admin"))

    admin_ctx = {}
    if is_admin:
        admin_ctx = {
            "feature_flags":    list_feature_flags(),
            "users":            list_app_users(),
            "master_schedules": list_master_schedules(),
        }

    return render_template(
        "settings.html",
        active_tab="settings",
        prefs=prefs,
        exclusions=exclusions,
        all_customers=[{"key": c["key"], "name": c["name"]} for c in CUSTOMERS],
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


@settings_bp.get("/api/settings/admin/users")
@require_admin
def api_list_users():
    return jsonify({"users": list_app_users()})


@settings_bp.post("/api/settings/admin/users")
@require_admin
def api_update_user():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400

    kwargs = {}
    if "display_name" in body:
        kwargs["display_name"] = (body.get("display_name") or None)
    if "is_admin" in body:
        kwargs["is_admin"] = bool(body["is_admin"])
    if "sharepoint_access_enabled" in body:
        kwargs["sharepoint_access_enabled"] = bool(body["sharepoint_access_enabled"])

    if not kwargs:
        return jsonify({"error": "no fields to update"}), 400

    # Prevent an admin from removing their own admin flag by mistake.
    me = (current_user() or {}).get("email", "").lower()
    if email == me and "is_admin" in kwargs and not kwargs["is_admin"]:
        return jsonify({"error": "You cannot remove your own admin access."}), 400

    update_app_user(email, **kwargs)
    return jsonify({"ok": True, "users": list_app_users()})


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
    return jsonify({"ok": True, "users": list_app_users()})


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
