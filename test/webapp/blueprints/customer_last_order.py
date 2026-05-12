"""Customer's Last Order -- a custom report whose interaction model
diverges from the standard ``filter form -> Tabulator viewer`` flow.

Routes:

* ``GET  /report/customer-last-order``
    Picker page. Customer search box + recent-customers list.

* ``GET  /api/report/customer-last-order/customers``
    JSON: every known customer (account + name). Used by the
    picker's autocomplete.

* ``GET  /api/report/customer-last-order/<account>/recent-orders``
    JSON: the customer's last 10 non-cancelled orders, newest first.
    Used by the "Add a previous order" modal on the view page.

* ``GET  /report/customer-last-order/<account>?orders=ORD1,ORD2``
    The detail page itself: header card + line items.
    ``orders`` defaults to "the customer's most recent invoiced
    order, falling back to most recent non-cancelled"; passing more
    order numbers triggers the rollup view.
"""
from __future__ import annotations

import logging

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

from test.config.reports import REPORTS
from test.webapp.auth import require_login
from test.webapp.services import customer_last_order as svc
from test.webapp.services import reporting_api

log = logging.getLogger(__name__)

bp = Blueprint(
    "customer_last_order",
    __name__,
    url_prefix="/report/customer-last-order",
)


def _ensure_enabled() -> None:
    rep = REPORTS.get("customer_last_order")
    if not rep or not rep.enabled:
        abort(404)


# ---------------------------------------------------------------------------
# Picker page
# ---------------------------------------------------------------------------


@bp.get("/")
@require_login
def pick():
    """Render the customer picker."""
    _ensure_enabled()
    return render_template(
        "customer_last_order_pick.html",
        report=REPORTS["customer_last_order"],
    )


# ---------------------------------------------------------------------------
# JSON APIs
# ---------------------------------------------------------------------------


@bp.get("/customers.json")
@require_login
def customers_json():
    """Return every customer the SP has lookup data for. Empty list if
    the API isn't configured -- the picker shows an info banner in that
    case.
    """
    _ensure_enabled()
    if not reporting_api.is_configured():
        return jsonify([])
    try:
        return jsonify(reporting_api.list_customers())
    except Exception:
        log.exception("customer_last_order: list_customers failed")
        return jsonify([])


@bp.get("/<account>/recent-orders.json")
@require_login
def recent_orders_json(account: str):
    """Last 10 non-cancelled orders for *account* (invoiced, partial,
    or open) -- powers the "Add a previous order" modal on the view
    page.
    """
    _ensure_enabled()
    account = (account or "").strip()
    if not account:
        return jsonify([])
    return jsonify(svc.fetch_recent_orders(account, limit=10))


# ---------------------------------------------------------------------------
# Detail (view) page
# ---------------------------------------------------------------------------


@bp.get("/<account>")
@require_login
def view(account: str):
    """Customer's last order detail.

    Without ``?orders=`` we default to the most recent invoiced order.
    With it, we render whichever orders the user picked, rolled up into
    a single "what they bought" view.
    """
    _ensure_enabled()
    account = (account or "").strip()
    if not account:
        return redirect(url_for("customer_last_order.pick"))

    info = svc.fetch_customer_info(account)

    raw_orders = (request.args.get("orders") or "").strip()
    if raw_orders:
        order_numbers = [o.strip() for o in raw_orders.split(",") if o.strip()]
    else:
        default = svc.pick_default_order(account)
        order_numbers = [default["order_number"]] if default else []

    headers, lines = ([], [])
    rolled = []
    if order_numbers:
        headers, lines = svc.fetch_orders_with_lines(account, order_numbers)
        rolled = svc.rollup_lines(lines)

    # Compose a synthetic header for the page banner. Single order =
    # use that order's metadata; multi-order = take the newest as
    # canonical and merge POs/orders for display.
    banner = {}
    if headers:
        newest = headers[0]
        banner = dict(newest)
        if len(headers) > 1:
            pos = [h.get("customer_req") or "" for h in headers]
            banner["customer_req"] = svc.common_po_prefix(pos) or " / ".join(p for p in pos if p)
            banner["order_number"] = " + ".join(h["order_number"] for h in headers)

    totals = {
        "qty_ordered":   round(sum(r.get("qty_ordered", 0)   for r in rolled), 2),
        "qty_shipped":   round(sum(r.get("qty_shipped", 0)   for r in rolled), 2),
        "qty_cancelled": round(sum(r.get("qty_cancelled", 0) for r in rolled), 2),
        "total":         round(sum(r.get("total", 0)         for r in rolled), 2),
    }

    return render_template(
        "customer_last_order_view.html",
        report=REPORTS["customer_last_order"],
        customer=info,
        headers=headers,
        lines=rolled,
        totals=totals,
        order_numbers=order_numbers,
        is_merged=len(headers) > 1,
        banner=banner,
        no_data=not headers,
    )
