"""
Dashboard blueprint.

Routes: /dashboard, /customer/<account>, /order/<order_number>
"""

import logging
from datetime import timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from webapp.helpers import get_current_user, require_login
from webapp.user_map import get_salesman_key, is_admin, is_manager
from webapp.db import (
    get_excluded_customers, get_notifications, get_feature_flag, get_db,
    get_user_salesman_access, normalize_key,
)
from webapp.services.access import validate_odata_param, user_can_access_customer
from webapp.services.d365 import (
    fetch_customer_orders, fetch_order_with_lines,
)

log = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@require_login
def dashboard():
    user = get_current_user()
    if not is_admin(user):
        if not get_feature_flag("dashboard_enabled", True):
            flash("The dashboard is currently disabled.", "info")
            return redirect(url_for("reports.reports_list"))
        email = user.get("email", "").lower().strip()
        conn = get_db()
        try:
            row = conn.execute("SELECT dashboard_enabled FROM app_users WHERE email = ?", (email,)).fetchone()
            if row and not row["dashboard_enabled"]:
                flash("Dashboard is not enabled for your account.", "info")
                return redirect(url_for("reports.reports_list"))
        finally:
            conn.close()
    from webapp.dashboard_data import (
        get_dashboard_data, get_dashboard_summary, get_refresh_status,
    )

    salesman_key = get_salesman_key(user)
    email = user.get("email", "")
    excluded = get_excluded_customers(email)

    if is_manager(user):
        allowed_keys = get_user_salesman_access(email)
        all_customers = get_dashboard_data(salesman_key=None, exclude_accounts=excluded)
        norm_allowed = {normalize_key(k) for k in allowed_keys}
        customers = [
            c for c in all_customers
            if normalize_key(c.get("sales_group", "")) in norm_allowed
        ]
        refresh = get_refresh_status(salesman_key=None)
    else:
        customers = get_dashboard_data(salesman_key=salesman_key, exclude_accounts=excluded)
        refresh = get_refresh_status(salesman_key=salesman_key)

    summary = get_dashboard_summary(customers)

    alerts = get_notifications(email, dismissed=False)
    alerts = [a for a in alerts if a["type"] == "overdue_customer"]

    return render_template(
        "dashboard.html", user=user, customers=customers, summary=summary,
        refresh=refresh, alerts=alerts, active_tab="dashboard",
    )


@dashboard_bp.route("/customer/<account>")
@require_login
def customer_detail(account):
    try:
        validate_odata_param(account)
    except ValueError:
        flash("Invalid customer account.", "error")
        return redirect(url_for("dashboard.dashboard"))

    user = get_current_user()
    if not user_can_access_customer(user, account):
        flash("You do not have access to this customer.", "error")
        return redirect(url_for("dashboard.dashboard"))

    cached = None
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM dashboard_cache WHERE customer_account = ?", (account,)
        ).fetchone()
        if row:
            cached = dict(row)
    finally:
        conn.close()

    cust_info = {"account": account, "name": account}
    orders = []
    active_period = "7"

    if cached:
        cust_info = {
            "account": cached.get("customer_account", account),
            "name": cached.get("customer_name", account),
            "sales_group": cached.get("sales_group", ""),
            "status": cached.get("status", ""),
            "days_since_last": cached.get("days_since_last"),
            "avg_gap_days": cached.get("avg_gap_days"),
            "overdue_threshold": cached.get("overdue_threshold"),
        }

    try:
        from core.dates import D365_GO_LIVE, get_today_eastern
        today = get_today_eastern()

        days_param = request.args.get("days", type=int)
        last_param = request.args.get("last", type=int)

        if last_param:
            start_date = D365_GO_LIVE
            active_period = f"last{last_param}"
        elif days_param:
            start_date = today - timedelta(days=days_param)
            active_period = str(days_param)
        else:
            start_date = today - timedelta(days=7)
            active_period = "7"

        orders = fetch_customer_orders(account, start_date, today, last_n=last_param)

    except Exception:
        log.exception("Failed to load orders for %s", account)
        flash("Could not load order data from D365.", "error")

    email = user.get("email", "")
    excluded = get_excluded_customers(email)
    is_excluded = account in excluded

    return render_template(
        "customer.html", user=user, customer=cust_info, orders=orders,
        active_period=active_period, is_excluded=is_excluded,
        active_tab="dashboard",
    )


@dashboard_bp.route("/order/<order_number>")
@require_login
def order_detail(order_number):
    try:
        validate_odata_param(order_number)
    except ValueError:
        flash("Invalid order number.", "error")
        return redirect(url_for("dashboard.dashboard"))

    user = get_current_user()

    header = {"order_number": order_number}
    lines = []
    customer_account = ""

    try:
        header, _basic_lines, customer_account = fetch_order_with_lines(order_number)

        if not user_can_access_customer(user, customer_account):
            flash("You do not have access to this order.", "error")
            return redirect(url_for("dashboard.dashboard"))

        from webapp.services.d365 import fetch_order_lines_with_qty_breakdown
        try:
            lines = fetch_order_lines_with_qty_breakdown(order_number)
        except Exception:
            log.exception("qty-breakdown fetch failed for %s; falling back to basic lines", order_number)
            lines = _basic_lines

        # Normalize so the template doesn't crash when the fallback path
        # (basic lines without WHS / packing data) is in effect.
        for ln in lines:
            ln.setdefault("qty_shipped", 0)
            ln.setdefault("qty_cancelled", 0)
            ln.setdefault("total_ordered", ln.get("total") or 0)
            ln.setdefault("total_shipped", 0)

    except Exception:
        log.exception("Failed to load order detail for %s", order_number)
        flash("Could not load order data from D365.", "error")

    return render_template(
        "order.html", user=user, header=header, lines=lines,
        customer_account=customer_account, active_tab="dashboard",
    )
