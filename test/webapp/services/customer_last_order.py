"""Customer's Last Order report -- data layer.

The live app pulls SalesOrderHeaders + SalesOrderLines + WHSReleases +
PackingSlips from D365 OData and runs the Ordered Report's classifier
to derive per-line ``QtyShipped`` / ``QtyCancelled``. Our test app
already has the ``salesline_release`` SP, which returns those same
fields directly (the live classifier exists *only* to compute them).
So we can power this report from a single SP call per customer.

Public surface used by the blueprint::

    fetch_customer_info(account)       -> {account, name, salesman}
    fetch_recent_invoiced_orders(acct) -> [{order_number, order_date, ...}, ...]
    fetch_orders_with_lines(acct, [order_numbers])
                                       -> ([header_dict, ...], [line_dict, ...])

Each call hits the SP once (with ``CustomerAccount`` filtered) and is
small and fast: a single customer's order history is a few hundred
lines at most.
"""
from __future__ import annotations

import logging
from typing import Any

from test.webapp.services import reporting_api
from test.webapp.services.reports.ordered import _norm_row

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_invoiced(status: str) -> bool:
    """Match the live filter: any status containing the word 'invoiced'.

    D365 emits 'Invoiced' for fully shipped/billed and 'Partially invoiced'
    for orders that are mid-shipment. Both are user-visible.
    """
    return "invoiced" in (status or "").lower()


def _fetch_lines_for_customer(account: str) -> list[dict]:
    """Pull every line for the customer from the SP and normalise.

    No date bound (period=all_time). The SP only returns rows for one
    company at a time, but `salesline_release` already scopes correctly.
    """
    raw = reporting_api.run("ordered", {
        "period":    "all_time",
        "customers": [account],
    })
    return [_norm_row(r) for r in (raw or [])]


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def fetch_customer_info(account: str) -> dict[str, str]:
    """Best-effort lookup of customer name + salesman.

    We don't have a customers table in test, so we infer from the SP's
    line data. If the customer has zero rows, we return a minimal stub.
    """
    try:
        lines = _fetch_lines_for_customer(account)
    except Exception:
        log.exception("customer_last_order: SP fetch failed for %s", account)
        return {"account": account, "name": account, "salesman": ""}

    if not lines:
        return {"account": account, "name": account, "salesman": ""}

    first = lines[0]
    return {
        "account":  account,
        "name":     first.get("CustomerName") or account,
        "salesman": first.get("Salesman") or "",
    }


def fetch_recent_invoiced_orders(account: str, limit: int = 10) -> list[dict]:
    """Return the customer's most recent *invoiced* orders, newest first.

    Each entry has the fields the picker modal needs: ``order_number``,
    ``order_date``, ``customer_req`` (PO #), ``order_total`` (sum of
    Ordered $).
    """
    try:
        lines = _fetch_lines_for_customer(account)
    except Exception:
        log.exception("customer_last_order: SP fetch failed for %s", account)
        return []

    if not lines:
        return []

    # Group by SalesOrderNumber, keep only invoiced.
    by_order: dict[str, dict] = {}
    for ln in lines:
        if not _is_invoiced(ln.get("Status", "")):
            continue
        so = ln.get("SalesOrderNumber") or ""
        if not so:
            continue
        if so not in by_order:
            by_order[so] = {
                "order_number":   so,
                "order_date":     (ln.get("OrderDate") or "")[:10],
                "customer_req":   ln.get("PO #") or "",
                "salesman":       ln.get("Salesman") or "",
                "status":         ln.get("Status") or "",
                "order_total":    0.0,
            }
        by_order[so]["order_total"] += float(ln.get("Ordered $") or 0)

    orders = list(by_order.values())
    for o in orders:
        o["order_total"] = round(o["order_total"], 2)

    # Newest first: sort by order_date descending. Empty dates land last.
    orders.sort(
        key=lambda o: (o["order_date"] or "0000-00-00"),
        reverse=True,
    )
    return orders[:limit]


def fetch_orders_with_lines(
    account: str,
    order_numbers: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """For one or more sales orders belonging to *account*, return
    ``(headers, lines)`` shaped for the view page.

    Header dict: ``order_number, order_date, customer_req, salesman, status``.
    Line dict:   ``order_number, line_number, item, description,
                  qty_ordered, qty_shipped, qty_cancelled, sales_price,
                  total_ordered, total_shipped, total, status``.

    ``total`` is an alias for ``total_shipped`` (matches the live
    template's totals row, which uses ``total``).
    """
    if not order_numbers:
        return [], []

    wanted = {str(n).strip() for n in order_numbers if str(n).strip()}
    if not wanted:
        return [], []

    try:
        all_lines = _fetch_lines_for_customer(account)
    except Exception:
        log.exception("customer_last_order: SP fetch failed for %s", account)
        return [], []

    matched = [ln for ln in all_lines if (ln.get("SalesOrderNumber") or "") in wanted]
    if not matched:
        return [], []

    # Build per-order headers (one row per distinct SalesOrderNumber).
    headers: dict[str, dict] = {}
    for ln in matched:
        so = ln["SalesOrderNumber"]
        if so in headers:
            continue
        headers[so] = {
            "order_number": so,
            "order_date":   (ln.get("OrderDate") or "")[:10],
            "customer_req": ln.get("PO #") or "",
            "salesman":     ln.get("Salesman") or "",
            "status":       ln.get("Status") or "",
            "customer_account": ln.get("CustomerAccount") or account,
            "customer_name":    ln.get("CustomerName") or "",
        }
    header_list = sorted(
        headers.values(),
        key=lambda h: h["order_date"] or "0000-00-00",
        reverse=True,
    )

    # Build line dicts in the shape the view template + Tabulator expect.
    line_list: list[dict] = []
    for ln in matched:
        qty_ordered   = float(ln.get("QtyOrdered")   or 0)
        qty_shipped   = float(ln.get("QtyShipped")   or 0)
        qty_cancelled = float(ln.get("QtyCancelled") or 0)
        sales_price   = float(ln.get("UnitPrice")    or 0)
        total_ordered = round(sales_price * qty_ordered, 2)
        total_shipped = round(sales_price * qty_shipped, 2)
        line_list.append({
            "order_number":  ln["SalesOrderNumber"],
            "line_number":   int(ln.get("LineNumber") or 0),
            "item":          ln.get("Item#") or "",
            "description":   ln.get("ItemName") or "",
            "qty_ordered":   qty_ordered,
            "qty_shipped":   qty_shipped,
            "qty_cancelled": qty_cancelled,
            "sales_price":   sales_price,
            "total_ordered": total_ordered,
            "total_shipped": total_shipped,
            "total":         total_shipped,
            "status":        ln.get("Status") or "",
        })

    return header_list, line_list


def rollup_lines(lines: list[dict]) -> list[dict]:
    """Combine identical (item, sales_price) rows across orders.

    Mirrors webapp/blueprints/reports.py::_rollup_lines so the
    test version produces the same totals as the live one.
    """
    grouped: dict[tuple, dict] = {}
    order_for_key: dict[tuple, list[str]] = {}
    for ln in lines:
        key = (ln["item"], round(float(ln.get("sales_price") or 0), 4))
        if key not in grouped:
            grouped[key] = {
                "item":          ln["item"],
                "description":   ln["description"],
                "qty_ordered":   0.0,
                "qty_shipped":   0.0,
                "qty_cancelled": 0.0,
                "sales_price":   ln["sales_price"],
                "total":         0.0,
            }
            order_for_key[key] = []
        g = grouped[key]
        g["qty_ordered"]   += float(ln.get("qty_ordered")   or 0)
        g["qty_shipped"]   += float(ln.get("qty_shipped")   or 0)
        g["qty_cancelled"] += float(ln.get("qty_cancelled") or 0)
        g["total"]         += float(ln.get("total")         or 0)
        if ln.get("order_number") and ln["order_number"] not in order_for_key[key]:
            order_for_key[key].append(ln["order_number"])

    rows = list(grouped.values())
    for r, k in zip(rows, grouped.keys()):
        r["qty_ordered"]   = round(r["qty_ordered"], 2)
        r["qty_shipped"]   = round(r["qty_shipped"], 2)
        r["qty_cancelled"] = round(r["qty_cancelled"], 2)
        r["total"]         = round(r["total"], 2)
        r["from_orders"]   = order_for_key[k]
    rows.sort(key=lambda r: r["item"])
    return rows


def common_po_prefix(pos: list[str]) -> str:
    """Longest shared prefix across PO strings, with trailing junk
    stripped. Used to render a clean PO header when merged orders look
    like ``PO12345`` + ``PO12345-addon``. Mirrors the live helper.
    """
    pos = [p.strip() for p in pos if p and p.strip()]
    if not pos:
        return ""
    if len(pos) == 1:
        return pos[0]
    prefix = pos[0]
    for p in pos[1:]:
        i = 0
        while i < len(prefix) and i < len(p) and prefix[i] == p[i]:
            i += 1
        prefix = prefix[:i]
    return prefix.rstrip("-_ ").strip() or pos[0]
