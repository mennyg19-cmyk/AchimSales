"""Ordered report builder (salesline_release).

Format/columns/math follow LIVE (reports/ordered/writer.py); on-screen
multi-tab architecture follows the test app. Six tabs:
Summary, By Customer, By Item, By Order, By Salesman, Full Data.

Authoritative vs derived
-------------------------
The SP returns server-side dollar columns (Ordered/Shipped/Cancelled $) that
already apply the WHS + packing-slip math; we use those as-is (owner: "the
$ columns are the god"). It does NOT yet return an explicit qty-cancelled, so
the qty buckets below are DERIVED on the interim rule and flagged as a stub
via each tab's ``stub_fields`` until the endpoint adds QtyCancelled::

    QtyCancelled = QtyOrdered            when status == 'cancelled', else 0
    QtyShipped   = QtyOrdered - DeliveryRemainder - QtyLeftToLoad - QtyCancelled
    QtyOpen      = QtyOrdered - QtyShipped - QtyCancelled
    Released $   = QtyReleased * UnitPrice
    Open $       = Ordered $ - Shipped $ - Cancelled $   (from authoritative $)

LIVE also drops "ERROR ITEM" lines; we mirror that.
"""

from __future__ import annotations

import re
from typing import Callable, Iterable, Sequence

from report_engine.facts import OrderLineFact

# Columns dependent on the not-yet-available qty-cancelled field. The UI
# renders these with a "pending API field" marker.
STUB_FIELDS: tuple[str, ...] = ("QtyShipped", "QtyCancelled", "QtyOpen", "Fulfillment %")
STUB_NOTE = ("QtyCancelled (and the QtyShipped/QtyOpen/Fulfillment % derived from "
             "it) are provisional until the salesline_release endpoint returns an "
             "explicit cancelled quantity. Dollar columns are authoritative.")

_ERROR_ITEM_RE = re.compile(r"ERROR\s*ITEM", re.IGNORECASE)

_QTY: tuple[str, ...] = ("QtyOrdered", "QtyShipped", "QtyCancelled", "QtyReleased", "QtyOpen")
_DOL: tuple[str, ...] = ("Ordered $", "Shipped $", "Cancelled $", "Released $", "Open $")


# --------------------------------------------------------------------------- #
# Column definitions (LIVE names, LIVE order)
# --------------------------------------------------------------------------- #

# LIVE order (reports/ordered/builder.py FULL_DATA_ORDER). LIVE's DataQualityFlag
# is a product of its WHS/packing-slip merge pipeline and can't be reproduced
# from the flat SP - omitted and logged as a known drift in REVIEW-LOG.
FULL_DATA_COLS = [
    {"field": "SalesOrderNumber", "header": "SalesOrderNumber", "type": "text"},
    {"field": "CustomerAccount",  "header": "CustomerAccount",  "type": "text"},
    {"field": "SalesOrderName",   "header": "SalesOrderName",    "type": "text"},
    {"field": "OrderDate",        "header": "OrderDate",         "type": "date"},
    {"field": "LineNumber",       "header": "LineNumber",        "type": "int"},
    {"field": "Item#",            "header": "Item#",             "type": "text"},
    {"field": "ItemName",         "header": "ItemName",          "type": "text"},
    {"field": "UnitPrice",        "header": "UnitPrice",         "type": "money"},
    {"field": "Status",           "header": "Status",            "type": "text"},
    {"field": "Fulfillment %",    "header": "Fulfillment %",     "type": "percent"},
    {"field": "QtyOrdered",       "header": "QtyOrdered",        "type": "int"},
    {"field": "QtyShipped",       "header": "QtyShipped",        "type": "int"},
    {"field": "QtyCancelled",     "header": "QtyCancelled",      "type": "int"},
    {"field": "QtyReleased",      "header": "QtyReleased",       "type": "int"},
    {"field": "QtyOpen",          "header": "QtyOpen",           "type": "int"},
    {"field": "Ordered $",        "header": "Ordered $",         "type": "money"},
    {"field": "Shipped $",        "header": "Shipped $",         "type": "money"},
    {"field": "Cancelled $",      "header": "Cancelled $",       "type": "money"},
    {"field": "Released $",       "header": "Released $",        "type": "money"},
    {"field": "Open $",           "header": "Open $",            "type": "money"},
]

_AGG_QTY_COLS = [{"field": f, "header": f, "type": "int"} for f in _QTY]
_AGG_DOL_COLS = [{"field": f, "header": f, "type": "money"} for f in _DOL]
_FF_COL = {"field": "Fulfillment %", "header": "Fulfillment %", "type": "percent"}

BY_CUSTOMER_COLS = [
    {"field": "CustomerAccount", "header": "CustomerAccount", "type": "text"},
    {"field": "CustomerName",    "header": "CustomerName",    "type": "text"},
    {"field": "Salesman",        "header": "Salesman",        "type": "text"},
    _FF_COL, *_AGG_QTY_COLS, *_AGG_DOL_COLS,
]
BY_ITEM_COLS = [
    {"field": "Item#",    "header": "Item#",    "type": "text"},
    {"field": "ItemName", "header": "ItemName", "type": "text"},
    _FF_COL, *_AGG_QTY_COLS, *_AGG_DOL_COLS,
]
BY_ORDER_COLS = [
    {"field": "SalesOrderNumber", "header": "SalesOrderNumber", "type": "text"},
    {"field": "OrderDate",        "header": "OrderDate",        "type": "date"},
    {"field": "CustomerAccount",  "header": "CustomerAccount",  "type": "text"},
    {"field": "CustomerName",     "header": "CustomerName",     "type": "text"},
    {"field": "Salesman",         "header": "Salesman",         "type": "text"},
    {"field": "PO #",             "header": "PO #",             "type": "text"},
    {"field": "OrderStatus",      "header": "Order Status",     "type": "text"},
    {"field": "Status",           "header": "Status",           "type": "text"},
    _FF_COL, *_AGG_QTY_COLS, *_AGG_DOL_COLS,
]
BY_SALESMAN_COLS = [
    {"field": "Salesman", "header": "Salesman", "type": "text"},
    _FF_COL, *_AGG_QTY_COLS, *_AGG_DOL_COLS,
]
SUMMARY_COLS = [
    {"field": "Customer Name",            "header": "Customer Name",            "type": "text"},
    {"field": "Salesman",                 "header": "Salesman",                 "type": "text"},
    {"field": "Item Number",              "header": "Item Number",              "type": "text"},
    {"field": "Line Description",         "header": "Line Description",         "type": "text"},
    {"field": "QtyOrdered",               "header": "QtyOrdered",               "type": "int"},
    {"field": "QtyCancelled",             "header": "QtyCancelled",             "type": "int"},
    {"field": "QtyRemainder",             "header": "QtyRemainder",             "type": "int"},
    {"field": "Net Price",                "header": "Net Price",                "type": "money"},
    {"field": "Extended Price - Ordered", "header": "Extended Price - Ordered", "type": "money"},
    {"field": "Extended Price Remainder", "header": "Extended Price Remainder", "type": "money"},
]


# --------------------------------------------------------------------------- #
# Per-line normalization
# --------------------------------------------------------------------------- #

_CANCELLED = {"canceled", "cancelled"}


def _line(f: OrderLineFact) -> dict:
    qty_ord = f.qty_ordered
    # LIVE treats a line as cancelled when the line status OR the order status is
    # canceled/cancelled (both spellings). Still a stub for QtyCancelled until the
    # SP returns an explicit cancelled quantity.
    is_cancelled = f.status.lower() in _CANCELLED or f.order_status.lower() in _CANCELLED
    qty_cancelled = qty_ord if is_cancelled else 0.0
    qty_shipped = max(0.0, qty_ord - f.delivery_remainder - f.qty_left_to_load - qty_cancelled)
    qty_open = max(0.0, qty_ord - qty_shipped - qty_cancelled)
    return {
        "SalesOrderNumber": f.sales_order_number,
        "SalesOrderName":   f.sales_order_name,
        "CustomerAccount":  f.customer_account,
        "CustomerName":     f.customer_name,
        "Salesman":         f.sales_group,
        "OrderDate":        f.order_date,
        "PO #":             f.po_number,
        "LineNumber":       f.line_number,
        "Item#":            f.item_number,
        "ItemName":         f.item_name,
        "UnitPrice":        f.unit_price,
        "OrderStatus":      f.order_status,
        "Status":           f.status,
        "Fulfillment %":    _ff_pct(qty_ord, qty_cancelled),
        "QtyOrdered":       qty_ord,
        "QtyShipped":       qty_shipped,
        "QtyCancelled":     qty_cancelled,
        "QtyReleased":      f.qty_released,
        "QtyOpen":          qty_open,
        "Ordered $":        f.ordered_dollars,
        "Shipped $":        f.shipped_dollars,
        "Cancelled $":      f.cancelled_dollars,
        "Released $":       round(f.qty_released * f.unit_price, 2),
        # Owner rule: Open $ = Ordered - Shipped - Cancelled (authoritative $),
        # not clamped (a credit/over-ship can legitimately make it negative).
        "Open $":           round(f.ordered_dollars - f.shipped_dollars - f.cancelled_dollars, 2),
    }


def _ff_pct(qty_ordered: float, qty_cancelled: float) -> float | None:
    """Fulfillment ratio, clamped to [0, 1] (matches LIVE _fulfillment_score)."""
    if qty_ordered <= 1e-6:
        return None
    return round(min(1.0, max(0.0, (qty_ordered - qty_cancelled) / qty_ordered)), 4)


def _is_error_item(line: dict) -> bool:
    # LIVE filters the Item number only (reports/ordered/builder.py), not the name.
    return bool(_ERROR_ITEM_RE.search(line["Item#"]))


# --------------------------------------------------------------------------- #
# Generic aggregation (one engine for the four rolled-up tabs)
# --------------------------------------------------------------------------- #

def _aggregate(
    lines: list[dict],
    *,
    key: Callable[[dict], tuple],
    lead: Callable[[dict], dict],
    sort: Callable[[dict], object],
) -> list[dict]:
    buckets: dict[tuple, dict] = {}
    leads: dict[tuple, dict] = {}
    for ln in lines:
        k = key(ln)
        b = buckets.get(k)
        if b is None:
            b = buckets[k] = {f: 0 for f in _QTY} | {f: 0.0 for f in _DOL}
            leads[k] = lead(ln)
        for f in _QTY:
            b[f] += ln[f]
        for f in _DOL:
            b[f] += ln[f]

    rows: list[dict] = []
    for k, b in buckets.items():
        row = dict(leads[k])
        row["Fulfillment %"] = _ff_pct(b["QtyOrdered"], b["QtyCancelled"])
        row.update({f: b[f] for f in _QTY})
        row.update({f: round(b[f], 2) for f in _DOL})
        rows.append(row)
    rows.sort(key=sort)
    return rows


def _tab(key: str, name: str, columns: Sequence[dict], rows: list[dict],
         *, stub: tuple[str, ...], **extra) -> dict:
    return {"key": key, "name": name, "columns": list(columns), "rows": rows,
            "stub_fields": list(stub), **extra}


def _by_ordered_desc(row: dict) -> float:
    return -float(row["Ordered $"] or 0)


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #

def _build_summary(lines: list[dict]) -> dict:
    grouped: dict[tuple, dict] = {}
    for ln in lines:
        cust = ln["CustomerName"] or ln["CustomerAccount"] or "(blank)"
        item = ln["Item#"] or "(blank)"
        k = (cust, item)
        g = grouped.get(k)
        if g is None:
            g = grouped[k] = {
                "Customer Name": cust, "Salesman": ln["Salesman"],
                "Item Number": item, "Line Description": ln["ItemName"],
                "QtyOrdered": 0, "QtyCancelled": 0, "QtyRemainder": 0,
                "Extended Price - Ordered": 0.0, "Extended Price Remainder": 0.0,
            }
        g["QtyOrdered"] += ln["QtyOrdered"]
        g["QtyCancelled"] += ln["QtyCancelled"]
        g["QtyRemainder"] += ln["QtyOpen"]
        g["Extended Price - Ordered"] += ln["Ordered $"]
        g["Extended Price Remainder"] += ln["Open $"]

    for g in grouped.values():
        qo = g["QtyOrdered"]
        g["Net Price"] = round(g["Extended Price - Ordered"] / qo, 4) if qo else 0.0
        g["Extended Price - Ordered"] = round(g["Extended Price - Ordered"], 2)
        g["Extended Price Remainder"] = round(g["Extended Price Remainder"], 2)

    return _tab(
        "summary", "Summary", SUMMARY_COLS, list(grouped.values()),
        stub=("QtyCancelled", "QtyRemainder"),
        default_layout={
            "group_levels": ["Customer Name"],
            "sort_levels": [{"field": "Customer Name", "dir": "asc"},
                            {"field": "Item Number", "dir": "asc"}],
        },
    )


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def build(facts: Iterable[OrderLineFact]) -> list[dict]:
    lines = [ln for ln in (_line(f) for f in facts) if not _is_error_item(ln)]

    by_customer = _aggregate(
        lines,
        key=lambda r: (r["CustomerAccount"] or "(none)", r["Salesman"] or ""),
        lead=lambda r: {"CustomerAccount": r["CustomerAccount"] or "(none)",
                        "CustomerName": r["CustomerName"], "Salesman": r["Salesman"]},
        sort=_by_ordered_desc,
    )
    by_item = _aggregate(
        lines,
        key=lambda r: (r["Item#"] or "(none)",),
        lead=lambda r: {"Item#": r["Item#"] or "(none)", "ItemName": r["ItemName"]},
        sort=_by_ordered_desc,
    )
    by_order = _aggregate(
        lines,
        key=lambda r: (r["SalesOrderNumber"] or "(none)",),
        lead=lambda r: {"SalesOrderNumber": r["SalesOrderNumber"] or "(none)",
                        "OrderDate": r["OrderDate"], "CustomerAccount": r["CustomerAccount"],
                        "CustomerName": r["CustomerName"], "Salesman": r["Salesman"],
                        "PO #": r["PO #"], "OrderStatus": r["OrderStatus"], "Status": r["Status"]},
        sort=lambda r: (r["OrderDate"] or ""),
    )
    by_order.sort(key=lambda r: (r["OrderDate"] or ""), reverse=True)
    by_salesman = _aggregate(
        lines,
        key=lambda r: (r["Salesman"] or "(none)",),
        lead=lambda r: {"Salesman": r["Salesman"] or "(none)"},
        sort=_by_ordered_desc,
    )

    return [
        _build_summary(lines),
        _tab("by_customer", "By Customer", BY_CUSTOMER_COLS, by_customer, stub=STUB_FIELDS),
        _tab("by_item", "By Item", BY_ITEM_COLS, by_item, stub=STUB_FIELDS),
        _tab("by_order", "By Order", BY_ORDER_COLS, by_order, stub=STUB_FIELDS),
        _tab("by_salesman", "By Salesman", BY_SALESMAN_COLS, by_salesman, stub=STUB_FIELDS),
        _tab("full_data", "Full Data", FULL_DATA_COLS, lines, stub=STUB_FIELDS),
    ]
