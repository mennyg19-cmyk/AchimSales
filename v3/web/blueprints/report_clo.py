"""Customer Last Order routes."""
from __future__ import annotations

from flask import abort, current_app, jsonify, redirect, render_template, request, send_file, url_for

from web.auth.decorators import require_login
from web.blueprints.reports import (
    _authz, _built_spec_or_404, _lookups, _principal_or_401, reports_bp,
)
from report_engine import registry
from report_engine.lib import salesman_key
from report_engine.reports import customer_last_order as clo
import io

_CLO_KEY = "customer_last_order"

def _report_service():
    return current_app.config["REPORT_SERVICE"]


def _assert_clo_access(p):
    """Page access: per-report grant (or privileged). Customer-level scope is
    enforced separately, per fetched customer, in the view itself."""
    _built_spec_or_404(_CLO_KEY)
    _authz().assert_can_view_report(p, _CLO_KEY)


def _visible_customers(p, salesman: str | None) -> list[dict]:
    """Customer picker list, narrowed to the principal's visible salesman scope."""
    customers = _lookups().customers(salesman)
    keys = _authz().visible_salesman_keys(p)
    if keys is None:
        return customers
    return [c for c in customers if salesman_key(c.get("salesman")) in keys]


@reports_bp.get("/report/customer-last-order")
@require_login
def customer_last_order_pick():
    p = _principal_or_401()
    _assert_clo_access(p)
    authz = _authz()
    # Admin/dev (unrestricted) get a salesman picker; scoped users don't need one.
    show_picker = authz.visible_salesman_keys(p) is None
    return render_template(
        "customer_last_order_pick.html", active_tab="reports",
        report=registry.get(_CLO_KEY), show_salesman_picker=show_picker,
    )


@reports_bp.get("/api/report/customer-last-order/customers")
@require_login
def customer_last_order_customers():
    p = _principal_or_401()
    _assert_clo_access(p)
    salesman = (request.args.get("salesman") or "").strip() or None
    return jsonify({"customers": _visible_customers(p, salesman)})


@reports_bp.get("/api/report/customer-last-order/salesmen")
@require_login
def customer_last_order_salesmen():
    p = _principal_or_401()
    _assert_clo_access(p)
    salesmen = _lookups().salesmen()
    keys = _authz().visible_salesman_keys(p)
    if keys is not None:  # scoped users only see their own salesmen (endpoint is callable directly)
        salesmen = [s for s in salesmen if salesman_key(s.get("key")) in keys]
    return jsonify({"salesmen": salesmen})


def _clo_rows_or_403(p, account: str):
    """Resolve the customer authoritatively, enforce scope, then fetch last orders.

    Returns (rows, customer_dict). Scope is checked against the CUSTOMER MASTER's
    sales group (LookupService), never the order lines — blank Salesman on a line
    must not deny a valid customer or skip authorization on empty history. When the
    master knows the customer we authorize on its group even with zero orders; when
    it can't resolve the account we fall back to Salesman on the SP rows and only
    authorize when there ARE rows (an empty unknown account leaks nothing).
    """
    from report_engine.lib import first_of, text as _text

    info = _lookups().customer(account)
    rows = _report_service().last_order_rows(account)
    if info is not None:
        sales_group, name = info["salesman"], info["name"]
        _authz().assert_can_view_customer(p, sales_group)
    else:
        sales_group = ""
        name = ""
        for r in rows:
            if not sales_group:
                sales_group = _text(first_of(r, "Salesman", "SalesGroup"))
            if not name:
                name = _text(first_of(r, "Customer Name", "CustomerName", "customername"))
            if sales_group and name:
                break
        if rows:
            _authz().assert_can_view_customer(p, sales_group)
    return rows, {"account": account, "name": name or account, "sales_group": sales_group}


@reports_bp.get("/api/report/customer-last-order/<account>/recent-invoiced")
@require_login
def customer_last_order_recent_invoiced(account: str):
    p = _principal_or_401()
    _assert_clo_access(p)
    rows, _ = _clo_rows_or_403(p, account)
    orders = [
        {"order_number": o.order_number, "order_date": o.order_date,
         "status": o.status, "customer_req": o.customer_req, "order_name": o.order_name}
        for o in clo.logical_orders(rows)
    ]
    return jsonify({"orders": orders})


@reports_bp.get("/report/customer-last-order/<account>")
@require_login
def customer_last_order_view(account: str):
    p = _principal_or_401()
    _assert_clo_access(p)

    requested = [o.strip() for o in (request.args.get("orders") or "").split(",") if o.strip()]
    try:
        rows, customer = _clo_rows_or_403(p, account)
        view = clo.build(rows, requested_orders=requested)
    except Exception as exc:  # noqa: BLE001 - render a clean error card, never 500
        if getattr(exc, "status_code", None) == 403:
            raise
        current_app.logger.exception("customer last order failed for %s", account)
        return render_template(
            "customer_last_order_view.html", active_tab="reports",
            customer={"account": account, "name": account, "sales_group": ""},
            view=None, error=str(exc),
        )
    return render_template(
        "customer_last_order_view.html", active_tab="reports",
        customer=customer, view=view, error=None,
    )


@reports_bp.get("/report/customer-last-order/<account>/export")
@require_login
def customer_last_order_export(account: str):
    """Excel or PDF of the current Last Order view (format=xlsx|pdf)."""
    from openpyxl import Workbook
    from web.reporting.last_order_export import last_order_pdf

    p = _principal_or_401()
    _assert_clo_access(p)
    fmt = (request.args.get("format") or "xlsx").strip().lower()
    if fmt not in ("xlsx", "pdf"):
        abort(400, description="format must be xlsx or pdf")
    requested = [o.strip() for o in (request.args.get("orders") or "").split(",") if o.strip()]
    rows, customer = _clo_rows_or_403(p, account)
    view = clo.build(rows, requested_orders=requested)
    if not view or not view.primary:
        abort(404, description="No order data to export")

    primary = view.primary
    name = customer.get("name") or account
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)[:40]
    primary_dict = {
        "order_number": primary.order_number,
        "order_date": primary.order_date,
        "salesman": primary.salesman,
    }
    line_dicts = [
        {
            "item": ln.item, "description": ln.description,
            "qty_ordered": ln.qty_ordered, "qty_shipped": ln.qty_shipped,
            "qty_cancelled": ln.qty_cancelled, "sales_price": ln.sales_price,
            "total": ln.total,
        }
        for ln in (view.lines or [])
    ]
    if fmt == "pdf":
        data = last_order_pdf(
            customer_name=name, account=account, primary=primary_dict,
            display_po=view.display_po or "", lines=line_dicts,
            totals=view.totals or {},
        )
        return send_file(
            io.BytesIO(data), mimetype="application/pdf", as_attachment=True,
            download_name=f"Last_Order_{safe}.pdf",
        )

    wb = Workbook()
    ws = wb.active
    ws.title = "Last Order"
    ws.append(["Customer", name, "Account", account])
    ws.append(["Order", primary.order_number, "Date", primary.order_date,
               "PO", view.display_po or ""])
    ws.append([])
    ws.append(["Item #", "Description", "Qty Ordered", "Qty Shipped",
               "Qty Cancelled", "Sales Price", "Total"])
    for line in line_dicts:
        ws.append([
            line["item"], line["description"],
            line["qty_ordered"], line["qty_shipped"], line["qty_cancelled"],
            line["sales_price"], line["total"],
        ])
    totals = view.totals or {}
    ws.append([
        "TOTALS", "", totals.get("qty_ordered"), totals.get("qty_shipped"),
        totals.get("qty_cancelled"), "", totals.get("total"),
    ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"Last_Order_{safe}.xlsx",
    )

