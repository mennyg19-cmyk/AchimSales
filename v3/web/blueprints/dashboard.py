"""Customer dashboard: cadence tiles + activity table, customer detail, and the
mirror refresh trigger.

Access: privileged users, or a user with the live `dashboard_enabled` flag. The
data is read from the precomputed `dashboard_customers` mirror; the viewer's
salesman scope and personal exclusions are applied on read (never trusting the
session). Customer detail's order list is fetched live from the Reporting API.
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, render_template, request

from report_engine.lib import salesman_key
from web.auth.decorators import require_login
from web.auth.session import current_principal
from web.data.repositories.exclusions import ExclusionRepository
from web.data.repositories.notifications import (
    OVERDUE,
    REPORT_READY,
    NotificationRepository,
)
from web.data.repositories.users import UserRepository

dashboard_bp = Blueprint("dashboard", __name__)


def _db():
    return current_app.config["DB"]


def _uid() -> int | None:
    row = UserRepository(_db()).get_by_email(current_principal().email)
    return row.id if row else None


def _require_dashboard_user():
    """Return (principal, user_row) if allowed, else abort 403."""
    p = current_principal()
    row = UserRepository(_db()).get_by_email(p.email)
    allowed = current_app.config["AUTHZ"].is_privileged(p) or bool(
        row and row.is_active and row.dashboard_enabled
    )
    if not allowed:
        abort(403, description="Dashboard access required")
    return p, row


@dashboard_bp.get("/dashboard")
@require_login
def dashboard():
    p, row = _require_dashboard_user()
    authz = current_app.config["AUTHZ"]
    excluded = ExclusionRepository(_db()).get(row.id) if row else set()
    summary, rows = current_app.config["DASHBOARD_SERVICE"].view(
        allowed_keys=authz.visible_salesman_keys(p), excluded=excluded,
    )
    return render_template(
        "dashboard.html", active_tab="dashboard",
        summary=summary, customers=rows, excluded=excluded,
        last_refreshed=current_app.config["DASHBOARD_SERVICE"].last_refreshed(),
    )


@dashboard_bp.post("/api/dashboard/refresh")
@require_login
def refresh():
    _, row = _require_dashboard_user()
    from web.dashboard.jobs import enqueue_refresh

    job_id = enqueue_refresh(current_app.config["JOB_REPO"], owner_user_id=row.id if row else None)
    return jsonify({"job_id": job_id}), 202


@dashboard_bp.get("/api/dashboard/refresh-status")
@require_login
def refresh_status():
    p, row = _require_dashboard_user()
    authz = current_app.config["AUTHZ"]
    excluded = ExclusionRepository(_db()).get(row.id) if row else set()
    # Scoped count, not the global mirror size: a scoped user must not learn how
    # many customers exist outside their book.
    _, rows = current_app.config["DASHBOARD_SERVICE"].view(
        allowed_keys=authz.visible_salesman_keys(p), excluded=excluded)
    return jsonify({"last_refreshed": current_app.config["DASHBOARD_SERVICE"].last_refreshed(),
                    "count": len(rows)})


@dashboard_bp.post("/api/dashboard/exclusion")
@require_login
def toggle_exclusion():
    _, row = _require_dashboard_user()
    body = request.get_json(silent=True) or {}
    account = (body.get("customer_account") or "").strip()
    if not account:
        return jsonify({"error": "customer_account required"}), 400
    ExclusionRepository(_db()).set(row.id, account, bool(body.get("excluded")))
    return jsonify({"customer_account": account, "excluded": bool(body.get("excluded"))})


@dashboard_bp.get("/api/notifications")
@require_login
def notifications():
    uid = _uid()
    if uid is None:
        return jsonify({"total": 0, "overdue_count": 0, "report_ready_count": 0, "items": []})
    repo = NotificationRepository(_db())
    counts = repo.counts(uid)
    items = [{"id": n.id, "type": n.type, **n.payload} for n in repo.list_undismissed(uid)]
    return jsonify({
        "total": sum(counts.values()),
        "overdue_count": counts.get(OVERDUE, 0),
        "report_ready_count": counts.get(REPORT_READY, 0),
        "items": items,
    })


@dashboard_bp.post("/api/notifications/dismiss")
@require_login
def dismiss_notification():
    uid = _uid()
    if uid is None:
        return jsonify({"dismissed": 0})
    body = request.get_json(silent=True) or {}
    n = NotificationRepository(_db()).dismiss(
        uid, notif_id=body.get("id"), type_=body.get("type"), all_=bool(body.get("all")))
    return jsonify({"dismissed": n})


@dashboard_bp.get("/customer/<account>")
@require_login
def customer_detail(account: str):
    p, row = _require_dashboard_user()
    authz = current_app.config["AUTHZ"]
    cust = current_app.config["DASHBOARD_REPO"].get(account)
    if cust is None:
        abort(404, description="Customer not found")
    # Scope: a non-privileged viewer may only open customers in their book.
    allowed = authz.visible_salesman_keys(p)
    if allowed is not None and salesman_key(cust.sales_group) not in allowed:
        abort(403, description="Not authorized for this customer")

    try:
        orders = current_app.config["REPORT_SERVICE"].customer_orders(account)
    except Exception:  # noqa: BLE001 - order history is best-effort; metrics still render
        current_app.logger.exception("customer order fetch failed for %s", account)
        orders = []
    orders = sorted(orders, key=lambda o: o.order_date or "", reverse=True)
    is_excluded = ExclusionRepository(_db()).is_excluded(row.id, account) if row else False
    return render_template(
        "customer_detail.html", active_tab="dashboard",
        customer=cust, orders=orders, is_excluded=is_excluded,
    )
