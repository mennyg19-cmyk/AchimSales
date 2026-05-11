"""Notification API endpoints for the v2 app."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from test.webapp.auth import current_user, require_login
from test.webapp.db import (
    dismiss_all_notifications,
    dismiss_notification,
    dismiss_notifications_by_type,
    get_notification_counts,
    get_notifications,
)

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.get("/api/notifications")
@require_login
def api_notifications():
    user = current_user() or {}
    email = user.get("email", "")
    counts = get_notification_counts(email)
    items = get_notifications(email, dismissed=False)
    return jsonify({
        "report_ready_count": counts.get("report_ready", 0),
        "overdue_count": counts.get("overdue_customer", 0),
        "total": counts.get("total", 0),
        "items": items,
    })


@notifications_bp.post("/api/notifications/dismiss")
@require_login
def api_notifications_dismiss():
    user = current_user() or {}
    email = user.get("email", "")
    data = request.get_json(silent=True) or {}

    if data.get("all"):
        dismiss_all_notifications(email)
    elif "id" in data:
        try:
            notification_id = int(data["id"])
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid notification id"}), 400
        dismiss_notification(notification_id, user_email=email)
    elif "type" in data:
        dismiss_notifications_by_type(email, str(data["type"]))

    return jsonify({"success": True})
