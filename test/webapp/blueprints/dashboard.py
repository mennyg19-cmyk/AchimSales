"""Dashboard blueprint.

Routes: /dashboard, /customer/<account>, /order/<order_number>, plus
refresh APIs used by the dashboard page.
"""

from __future__ import annotations

import logging
import re

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from test.webapp.auth import current_user, require_login
from test.webapp.db import (
    get_app_user,
    get_feature_flag,
    get_notifications,
    get_user_exclusions,
)
from test.webapp.services import dashboard_data
from test.webapp.services.report_access import get_user_profile

dashboard_bp = Blueprint("dashboard", __name__)
log = logging.getLogger(__name__)

_SAFE_PARAM_RE = re.compile(r"^[A-Za-z0-9\-_]+$")


def _validate_param(value: str) -> bool:
    return bool(value and _SAFE_PARAM_RE.match(value))


def _refresh_salesman_scope(email: str) -> str | None:
    profile = get_user_profile(email)
    if profile["role"] == "salesman":
        return profile.get("salesman_key")
    return None


def _dashboard_enabled_for_user(email: str) -> bool:
    profile = get_user_profile(email)
    if profile["role"] in {"admin", "developer"}:
        return True
    if not get_feature_flag("dashboard_enabled", True):
        return False
    row = get_app_user(email)
    return bool(row is None or row.get("dashboard_enabled", True))


def _dashboard_disabled_message(email: str) -> str:
    profile = get_user_profile(email)
    if profile["role"] in {"admin", "developer"}:
        return ""
    if not get_feature_flag("dashboard_enabled", True):
        return "The dashboard is currently disabled."
    return "Dashboard is not enabled for your account."


@dashboard_bp.route("/dashboard")
@require_login
def index():
    user = current_user() or {}
    email = user.get("email", "")
    if not _dashboard_enabled_for_user(email):
        flash(_dashboard_disabled_message(email), "info")
        return redirect(url_for("reports.list_all"))

    scope = dashboard_data.get_user_dashboard_scope(email)
    excluded = get_user_exclusions(email)
    customers = dashboard_data.get_dashboard_data(
        salesman_key=scope.get("salesman_key"),
        allowed_salesman_keys=scope.get("allowed_salesman_keys"),
        exclude_accounts=excluded,
    )
    cache_warning = dashboard_data.get_cache_quality_warning()
    if cache_warning:
        customers = []
    summary = dashboard_data.get_dashboard_summary(customers)
    refresh_scope = _refresh_salesman_scope(email)
    poll_refresh_before = None
    if dashboard_data.cache_needs_order_refresh():
        refresh_request = dashboard_data.request_background_refresh(refresh_scope)
        if refresh_request.get("started") or refresh_request.get("already_running"):
            poll_refresh_before = refresh_request.get("before") or ""
    refresh = dashboard_data.get_refresh_status(refresh_scope)

    return render_template(
        "dashboard.html",
        active_tab="dashboard",
        user=user,
        customers=customers,
        summary=summary,
        refresh=refresh,
        cache_warning=cache_warning,
        poll_refresh_before=poll_refresh_before,
        alerts=[
            alert for alert in get_notifications(email, dismissed=False)
            if alert.get("type") == "overdue_customer"
        ],
        mirror_window_days=dashboard_data.salesline_window_days(),
    )


@dashboard_bp.route("/customer/<account>")
@require_login
def customer_detail(account: str):
    if not _validate_param(account):
        flash("Invalid customer account.", "error")
        return redirect(url_for("dashboard.index"))

    user = current_user() or {}
    email = user.get("email", "")
    if not dashboard_data.user_can_access_customer(email, account):
        flash("You do not have access to this customer.", "error")
        return redirect(url_for("dashboard.index"))

    customer = dashboard_data.fetch_customer_info(account)
    days_param = request.args.get("days", type=int)
    last_param = request.args.get("last", type=int)
    active_period = "7"
    if last_param:
        active_period = f"last{last_param}"
    elif days_param:
        active_period = str(days_param)
    else:
        days_param = 7

    try:
        orders = dashboard_data.fetch_customer_orders(
            account,
            days=days_param,
            last_n=last_param,
        )
    except Exception:
        log.exception("Failed to load customer dashboard orders: %s", account)
        flash("Could not load order data from the reporting API.", "error")
        orders = []

    exclusions = get_user_exclusions(email)
    return render_template(
        "customer.html",
        active_tab="dashboard",
        user=user,
        customer=customer,
        orders=orders,
        active_period=active_period,
        is_excluded=account in exclusions,
        mirror_window_days=dashboard_data.salesline_window_days(),
    )


@dashboard_bp.route("/order/<order_number>")
@require_login
def order_detail(order_number: str):
    if not _validate_param(order_number):
        flash("Invalid order number.", "error")
        return redirect(url_for("dashboard.index"))

    user = current_user() or {}
    email = user.get("email", "")
    profile = get_user_profile(email)

    try:
        header, lines, customer_account = dashboard_data.fetch_order_detail(order_number)
    except Exception:
        log.exception("Failed to load dashboard order detail: %s", order_number)
        flash("Could not load order data from the reporting API.", "error")
        header, lines, customer_account = {"order_number": order_number}, [], ""

    if customer_account:
        if not dashboard_data.user_can_access_order(email, customer_account):
            flash("You do not have access to this order.", "error")
            return redirect(url_for("dashboard.index"))
    elif profile["role"] not in {"admin", "developer"}:
        flash("You do not have access to this order.", "error")
        return redirect(url_for("dashboard.index"))

    return render_template(
        "order.html",
        active_tab="dashboard",
        user=user,
        header=header,
        lines=lines,
        customer_account=customer_account,
        mirror_window_days=dashboard_data.salesline_window_days(),
    )


@dashboard_bp.post("/api/dashboard/refresh")
@require_login
def api_refresh():
    user = current_user() or {}
    email = user.get("email", "")
    salesman_key = _refresh_salesman_scope(email)
    result = dashboard_data.request_background_refresh(salesman_key)
    return jsonify({
        "success": True,
        **result,
    })


@dashboard_bp.get("/api/dashboard/refresh-status")
@require_login
def api_refresh_status():
    user = current_user() or {}
    salesman_key = _refresh_salesman_scope(user.get("email", ""))
    before = request.args.get("before", "")
    status = dashboard_data.get_refresh_status(salesman_key)
    current = status.get("last_completed") or ""
    failed = (status.get("step") or "").lower().startswith("refresh failed")
    done = bool(current and current != before) or (failed and not status.get("running"))
    return jsonify({
        "done": done,
        "running": status["running"],
        "step": status.get("step", ""),
        "last_requested": status.get("last_requested"),
        "last_completed": current,
    })


@dashboard_bp.get("/api/dashboard/data")
@require_login
def api_dashboard_data():
    user = current_user() or {}
    email = user.get("email", "")
    scope = dashboard_data.get_user_dashboard_scope(email)
    customers = dashboard_data.get_dashboard_data(
        salesman_key=scope.get("salesman_key"),
        allowed_salesman_keys=scope.get("allowed_salesman_keys"),
        exclude_accounts=get_user_exclusions(email),
    )
    summary = dashboard_data.get_dashboard_summary(customers)
    refresh = dashboard_data.get_refresh_status(_refresh_salesman_scope(email))
    visible_customers = []
    for c in customers:
        if c.get("excluded"):
            continue
        account = c.get("customer_account") or ""
        visible_customers.append({
            "customer_account": account,
            "customer_name": c.get("customer_name") or account,
            "last_order_date": c.get("last_order_date") or "",
            "days_since_last": c.get("days_since_last"),
            "avg_gap_days": c.get("avg_gap_days"),
            "overdue_threshold": c.get("overdue_threshold"),
            "status": c.get("status") or "new",
            "url": url_for("dashboard.customer_detail", account=account),
        })
    return jsonify({
        "success": True,
        "summary": summary,
        "customers": visible_customers,
        "refresh": refresh,
    })
