"""
Dashboard blueprint.

Routes: /dashboard, /customer/<account>, /order/<order_number>
"""

import logging
from datetime import timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from webapp.helpers import get_current_user, require_login
from webapp.user_map import get_salesman_key, is_admin
from webapp.db import (
    get_excluded_customers, get_notifications, get_feature_flag, get_db,
    get_cached_orders, get_cached_order_detail,
)
from webapp.services.access import validate_odata_param, check_customer_access, check_order_access

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

    from webapp.db import get_db
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

    if salesman_key and not user_is_admin:
        from webapp.db import normalize_key
        if normalize_key(salesman_key) != normalize_key(cust_info.get("sales_group", "")):
            flash("You do not have access to this customer.", "error")
            return redirect(url_for("dashboard.dashboard"))

    try:
        from core.dates import D365_GO_LIVE, get_today_eastern
        today = get_today_eastern()

        days_param = request.args.get("days", type=int)
        last_param = request.args.get("last", type=int)

        if last_param:
            start_date = D365_GO_LIVE.isoformat()
            active_period = f"last{last_param}"
        elif days_param:
            start_date = (today - timedelta(days=days_param)).isoformat()
            active_period = str(days_param)
        else:
            start_date = (today - timedelta(days=7)).isoformat()
            active_period = "7"

        cached_rows = get_cached_orders(
            account, start_date=start_date,
            end_date=today.isoformat(), last_n=last_param,
        )
        orders = [
            {
                "order_number": r.get("sales_order_number", ""),
                "order_date": r.get("order_date", ""),
                "status": r.get("order_status", ""),
                "processing_status": r.get("processing_status", ""),
                "customer_req": r.get("customer_requisition", ""),
                "order_name": r.get("sales_order_name", ""),
            }
            for r in cached_rows
        ]

    except Exception:
        log.exception("Failed to load cached orders for %s", account)
        flash("Could not load order data.", "error")

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

    header_dict = {"order_number": order_number}
    lines = []
    customer_account = ""

    try:
        cached_header, cached_lines = get_cached_order_detail(order_number)

        if cached_header:
            customer_account = cached_header.get("customer_account", "")
            header_dict = {
                "order_number": cached_header.get("sales_order_number", order_number),
                "order_date": cached_header.get("order_date", ""),
                "status": cached_header.get("order_status", ""),
                "processing_status": cached_header.get("processing_status", ""),
                "customer_account": customer_account,
                "customer_name": cached_header.get("customer_name", ""),
                "customer_req": cached_header.get("customer_requisition", ""),
                "order_name": cached_header.get("sales_order_name", ""),
                "salesman": cached_header.get("salesman", ""),
            }
            lines = [
                {
                    "item_number": ln.get("item_number", ""),
                    "description": ln.get("line_description", ""),
                    "qty": ln.get("qty_ordered", 0),
                    "price": ln.get("sales_price", 0),
                    "total": ln.get("line_total", 0),
                    "status": ln.get("line_status", ""),
                }
                for ln in cached_lines
            ]

        if customer_account and not check_order_access(salesman_key, customer_account, is_admin=user_is_admin):
            flash("You do not have access to this order.", "error")
            return redirect(url_for("dashboard.dashboard"))

    except Exception:
        log.exception("Failed to load cached order detail for %s", order_number)
        flash("Could not load order data.", "error")

    return render_template(
        "order.html", user=user, header=header_dict, lines=lines,
        customer_account=customer_account, active_tab="dashboard",
    )
