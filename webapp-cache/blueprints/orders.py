"""
Orders blueprint.

Routes: /orders, /orders/new, /orders/<id>
"""

import logging

from flask import Blueprint, flash, redirect, render_template, url_for

from webapp.helpers import get_current_user, require_login
from webapp.user_map import is_admin
from webapp.db import (
    get_feature_flag, get_draft_orders, get_draft_order,
    get_draft_order_lines,
)

log = logging.getLogger(__name__)

orders_bp = Blueprint("orders", __name__)


def _check_order_entry_access(user: dict) -> bool:
    """Return True if the user may access order entry, False otherwise."""
    if is_admin(user):
        return True
    return get_feature_flag("order_entry_enabled", False)


@orders_bp.route("/orders")
@require_login
def orders_list():
    user = get_current_user()
    if not _check_order_entry_access(user):
        flash("Order entry is currently disabled.", "info")
        return redirect(url_for("reports.reports_list"))

    email = user.get("email", "")
    drafts = get_draft_orders(email)
    return render_template(
        "orders.html", user=user, drafts=drafts, active_tab="orders",
    )


@orders_bp.route("/orders/new")
@require_login
def order_new():
    user = get_current_user()
    if not _check_order_entry_access(user):
        flash("Order entry is currently disabled.", "info")
        return redirect(url_for("reports.reports_list"))

    from webapp.config import GOOGLE_MAPS_API_KEY
    return render_template(
        "order_entry.html", user=user, order=None, lines=[],
        active_tab="orders", google_maps_key=GOOGLE_MAPS_API_KEY,
    )


@orders_bp.route("/orders/<int:order_id>")
@require_login
def order_edit(order_id):
    user = get_current_user()
    if not _check_order_entry_access(user):
        flash("Order entry is currently disabled.", "info")
        return redirect(url_for("reports.reports_list"))

    email = user.get("email", "")
    order = get_draft_order(order_id, user_email=email)
    if not order:
        flash("Order not found.", "error")
        return redirect(url_for("orders.orders_list"))

    lines = get_draft_order_lines(order_id)
    from webapp.config import GOOGLE_MAPS_API_KEY
    return render_template(
        "order_entry.html", user=user, order=order, lines=lines,
        active_tab="orders", google_maps_key=GOOGLE_MAPS_API_KEY,
    )
