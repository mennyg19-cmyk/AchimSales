"""Customer's Last Order report -- data layer.

The live app pulled SalesOrderHeaders + SalesOrderLines + WHSReleases +
PackingSlips from D365 OData and ran the Ordered Report's classifier to
derive per-line ``QtyShipped`` / ``QtyCancelled``. Our test app already
has the ``salesline_release`` SP, which returns those same fields *and*
the order-level ``OrderStatus`` (Invoiced / Partially invoiced / Open
Order / Cancelled) directly. One SP call per customer, no classifier.

Public surface used by the blueprint::

    fetch_customer_info(account)       -> {account, name, salesman}
    fetch_recent_orders(acct, limit)   -> [{order_number, order_date,
                                            status, ...}, ...]
    pick_default_order(acct)           -> the order to auto-load on
                                          first view: most recent invoiced
                                          if any, else most recent
                                          non-cancelled
    fetch_orders_with_lines(acct, [order_numbers])
                                       -> ([header_dict, ...], [line_dict, ...])
"""
from __future__ import annotations

import logging
from typing import Any

from core.dates import D365_GO_LIVE, get_today_eastern
from test.webapp.services import reporting_api
from test.webapp.services.reports.ordered import _norm_row

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_invoiced(order_status: str) -> bool:
    """Match the live filter: any *header* OrderStatus containing 'invoiced'.

    D365 emits 'Invoiced' for fully shipped/billed and 'Partially invoiced'
    for orders that are mid-shipment. Both are user-visible.

    NOTE: must be applied to ``OrderStatus`` (header), not ``Status``
    (line-level SalesStatus). A fully-invoiced order can have per-line
    SalesStatus values like 'Delivered' / 'Invoiced' / 'Open Order'.
    """
    return "invoiced" in (order_status or "").lower()


def _is_cancelled(order_status: str) -> bool:
    return "cancelled" in (order_status or "").lower()


def _fetch_lines_for_customer(
    account: str,
    *,
    require_orders: set[str] | None = None,
) -> list[dict]:
    """Pull every line for the customer, preferring the local mirror.

    The 60-day salesline mirror is an indexed SQLite lookup and answers
    in milliseconds. The SP call, by contrast, can take seconds because
    it scans 16 months of history. For most page loads (default order =
    most-recent) the mirror has everything we need, so we hit it first.

    If ``require_orders`` is given (e.g. user picked specific historical
    order numbers via the merge modal), we make sure every requested
    order is present in the mirror result; if any are missing, we fall
    back to the SP for the full history. This keeps deep links and
    older-order lookups working without slowing down the common case.

    ``period="all_time"`` resolves to ``(None, None)`` in the SP
    translator and returns nothing, so the SP fallback uses an explicit
    custom range from D365 go-live to today.
    """
    from test.webapp.services import mirror

    mirror_rows = mirror.get_salesline_fallback(customer_account=account)
    if mirror_rows:
        normalized = [_norm_row(r) for r in mirror_rows]
        if not require_orders:
            return normalized
        have = {ln["SalesOrderNumber"] for ln in normalized}
        if require_orders.issubset(have):
            return normalized
        # else: fall through to SP -- some requested orders aren't mirrored

    raw = reporting_api.run("ordered", {
        "period":     "custom",
        "start_date": D365_GO_LIVE.isoformat(),
        "end_date":   get_today_eastern().isoformat(),
        "customers":  [account],
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


def fetch_recent_orders(account: str, limit: int = 10) -> list[dict]:
    """Return the customer's most recent non-cancelled orders, newest first.

    Includes Invoiced, Partially invoiced, and Open Order statuses so
    the picker is useful even for customers who haven't been billed
    yet. Cancelled orders are filtered out -- they're never relevant
    on the "last order" page.

    Each entry has the fields the picker modal needs: ``order_number``,
    ``order_date``, ``customer_req`` (PO #), ``status`` (header
    OrderStatus), ``order_total`` (sum of Ordered $).
    """
    try:
        lines = _fetch_lines_for_customer(account)
    except Exception:
        log.exception("customer_last_order: SP fetch failed for %s", account)
        return []

    if not lines:
        return []

    by_order: dict[str, dict] = {}
    for ln in lines:
        so = ln.get("SalesOrderNumber") or ""
        if not so:
            continue
        order_status = ln.get("OrderStatus") or ""
        if _is_cancelled(order_status):
            continue
        if so not in by_order:
            by_order[so] = {
                "order_number":   so,
                "order_date":     (ln.get("OrderDate") or "")[:10],
                "customer_req":   ln.get("PO #") or "",
                "salesman":       ln.get("Salesman") or "",
                "status":         order_status,
                "processing_status": ln.get("Status") or "",
                "order_total":    0.0,
            }
        by_order[so]["order_total"] += float(ln.get("Ordered $") or 0)

    orders = list(by_order.values())
    for o in orders:
        o["order_total"] = round(o["order_total"], 2)

    orders.sort(
        key=lambda o: (o["order_date"] or "0000-00-00"),
        reverse=True,
    )
    return orders[:limit]


def pick_default_order(account: str) -> dict | None:
    """Pick which single order to auto-load when the page opens with
    no ``?orders=`` param.

    Preference: most-recent INVOICED order (matches the live app's
    "Last Invoiced Order" behaviour). If the customer has none on
    record, fall back to the most-recent non-cancelled order so the
    page still has something useful to show.

    Returns the chosen order dict (same shape as ``fetch_recent_orders``)
    or ``None`` if the customer has zero non-cancelled orders.
    """
    orders = fetch_recent_orders(account, limit=50)
    if not orders:
        return None
    return next((o for o in orders if _is_invoiced(o["status"])), orders[0])


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
        all_lines = _fetch_lines_for_customer(account, require_orders=wanted)
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
            "status":       ln.get("OrderStatus") or "",
            "processing_status": ln.get("Status") or "",
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
