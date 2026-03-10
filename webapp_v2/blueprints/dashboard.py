"""
Dashboard blueprint.

Routes: /dashboard, /customer/<account>, /order/<order_number>
"""

import logging
from datetime import date as _date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from webapp_v2.helpers import get_current_user, require_login
from webapp_v2.user_map import get_salesman_key, is_admin
from webapp_v2.db import get_excluded_customers, get_notifications
from webapp_v2.services.access import validate_odata_param, check_customer_access, check_order_access
from webapp_v2.services.d365 import (
    fetch_customer_info, fetch_customer_orders, fetch_order_with_lines,
)

log = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@require_login
def dashboard():
    user = get_current_user()
    from webapp_v2.dashboard_data import (
        get_dashboard_data, get_dashboard_summary, get_refresh_status,
    )

    salesman_key = get_salesman_key(user)
    email = user.get("email", "")
    excluded = get_excluded_customers(email)
    customers = get_dashboard_data(salesman_key=salesman_key, exclude_accounts=excluded)
    summary = get_dashboard_summary(customers)
    refresh = get_refresh_status(salesman_key=salesman_key)

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
    salesman_key = get_salesman_key(user)
    user_is_admin = is_admin(user)

    from webapp_v2.db import get_db
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

    if not check_customer_access(salesman_key, account, is_admin=user_is_admin):
        flash("You do not have access to this customer.", "error")
        return redirect(url_for("dashboard.dashboard"))

    cust_info = {"account": account, "name": account}
    orders = []
    active_period = "7"

    try:
        cust_info = fetch_customer_info(account)

        if salesman_key and not user_is_admin:
            from webapp_v2.db import normalize_key
            if normalize_key(salesman_key) != normalize_key(cust_info.get("sales_group", "")):
                flash("You do not have access to this customer.", "error")
                return redirect(url_for("dashboard.dashboard"))

        if cached:
            cust_info["status"] = cached.get("status", "")
            cust_info["days_since_last"] = cached.get("days_since_last")
            cust_info["avg_gap_days"] = cached.get("avg_gap_days")
            cust_info["overdue_threshold"] = cached.get("overdue_threshold")

        from core.dates import get_today_eastern
        today = get_today_eastern()

        days_param = request.args.get("days", type=int)
        last_param = request.args.get("last", type=int)

        if last_param:
            start_date = _date(2000, 1, 1)
            active_period = f"last{last_param}"
        elif days_param:
            start_date = today - timedelta(days=days_param)
            active_period = str(days_param)
        else:
            start_date = today - timedelta(days=7)
            active_period = "7"

        orders = fetch_customer_orders(account, start_date, today, last_n=last_param)

    except Exception:
        log.exception("Failed to load customer detail for %s", account)
        flash("Could not load customer data from D365.", "error")

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
    salesman_key = get_salesman_key(user)
    user_is_admin = is_admin(user)

    header = {"order_number": order_number}
    lines = []
    customer_account = ""

    try:
        header, lines, customer_account = fetch_order_with_lines(order_number)

        if customer_account and not check_order_access(salesman_key, customer_account, is_admin=user_is_admin):
            flash("You do not have access to this order.", "error")
            return redirect(url_for("dashboard.dashboard"))

    except Exception:
        log.exception("Failed to load order detail for %s", order_number)
        flash("Could not load order data from D365.", "error")

    return render_template(
        "order.html", user=user, header=header, lines=lines,
        customer_account=customer_account, active_tab="dashboard",
    )
