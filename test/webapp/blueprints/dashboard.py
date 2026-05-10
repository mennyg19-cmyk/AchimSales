"""Dashboard blueprint.

Routes: /dashboard, /customer/<account>, /order/<order_number>, plus
refresh APIs used by the dashboard page.
"""

from __future__ import annotations

import logging
import re
import threading

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from test.webapp.auth import current_user, require_login
from test.webapp.db import (
    get_app_user,
    get_feature_flag,
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


@dashboard_bp.route("/dashboard")
@require_login
def index():
    user = current_user() or {}
    email = user.get("email", "")
    if not _dashboard_enabled_for_user(email):
        flash("Dashboard is not enabled for your account.", "info")
        return redirect(url_for("reports.list_all"))

    scope = dashboard_data.get_user_dashboard_scope(email)
    excluded = get_user_exclusions(email)
    customers = dashboard_data.get_dashboard_data(
        salesman_key=scope.get("salesman_key"),
        allowed_salesman_keys=scope.get("allowed_salesman_keys"),
        exclude_accounts=excluded,
    )
    summary = dashboard_data.get_dashboard_summary(customers)
    refresh = dashboard_data.get_refresh_status(_refresh_salesman_scope(email))

    return render_template(
        "dashboard.html",
        active_tab="dashboard",
        user=user,
        customers=customers,
        summary=summary,
        refresh=refresh,
        alerts=[],
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
    )


@dashboard_bp.post("/api/dashboard/refresh")
@require_login
def api_refresh():
    user = current_user() or {}
    email = user.get("email", "")
    salesman_key = _refresh_salesman_scope(email)
    before = dashboard_data.get_last_refresh() or ""
    requested_at = dashboard_data.mark_refresh_requested()

    def _run_refresh() -> None:
        try:
            dashboard_data.refresh_cache(salesman_key=salesman_key)
        except Exception:
            log.exception("Manual dashboard refresh failed")

    threading.Thread(target=_run_refresh, name="v2-dashboard-manual-refresh", daemon=True).start()
    return jsonify({
        "success": True,
        "started": True,
        "before": before,
        "requested_at": requested_at,
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
