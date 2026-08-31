"""Ordered report builder (rpt.usp_ordered_report).

Six tabs: Summary, By Customer, By Item, By Order, By Salesman, Full Data.

Qty columns are the SP's own fields (no QtyShipped column — SP ReleasedQuantity
is the combined live QtyReleased+QtyShipped)::

    QtyOrdered      = QuantityOrdered
    QtyReserved     = QuantityReserved
    QtyReleased     = ReleasedQuantity   (Excel/UI header: "QTY Shipping")
    QtyCancelled    = CancelledQTY
    QtyLeftToShip   = DeliveryRemainder   ("qty left to ship")

Dollar columns: Ordered/Shipped/Cancelled $ from the SP. Shipping $ and
Summary Extended Price Remainder are ShippingDollars with no fallback math.
Summary Extended Price Cancelled is Cancelled $.
Open $ stays Ordered $ − Shipped $ − Cancelled $. Shipped $ is not shown.

LIVE also drops "ERROR ITEM" lines; we mirror that.
"""

from __future__ import annotations

import re
from typing import Callable, Iterable, Sequence

from report_engine.facts import OrderLineFact

# Only columns the SP still doesn't supply.
STUB_FIELDS: tuple[str, ...] = ("OrderStatus",)
STUB_NOTE = ("Order Status is blank until the ordered_report SP provides it. "
             "PO # comes from CustomerRequisition. Qty columns and "
             "Ordered/Cancelled $ come straight from the SP; Shipping $ is "
             "ShippingDollars only.")

_ERROR_ITEM_RE = re.compile(r"ERROR\s*ITEM", re.IGNORECASE)

_QTY: tuple[str, ...] = (
    "QtyOrdered", "QtyReserved", "QtyReleased", "QtyCancelled", "QtyLeftToShip",
)
_DOL: tuple[str, ...] = ("Ordered $", "Cancelled $", "Released $", "Open $")
_DOL_HEADERS: dict[str, str] = {
    "Ordered $": "Ordered $",
    "Cancelled $": "Cancelled $",
    "Released $": "Shipping $",
    "Open $": "Open $",
}


# --------------------------------------------------------------------------- #
# Column definitions
# --------------------------------------------------------------------------- #

FULL_DATA_COLS = [
    {"field": "SalesOrderNumber",    "header": "SalesOrderNumber",    "type": "text"},
    {"field": "CustomerAccount",     "header": "CustomerAccount",     "type": "text"},
    {"field": "CustomerName",        "header": "CustomerName",        "type": "text"},
    {"field": "SalesOrderName",      "header": "SalesOrderName",      "type": "text"},
    {"field": "OrderDate",           "header": "OrderDate",           "type": "date"},
    {"field": "purchid",             "header": "purchid",             "type": "text"},
    {"field": "ExpectedArrivalDate", "header": "ExpectedArrivalDate", "type": "date"},
    {"field": "ShipDate",            "header": "ShipDate",            "type": "date"},
    {"field": "LineNumber",          "header": "LineNumber",          "type": "int"},
    {"field": "Item#",               "header": "Item#",               "type": "text"},
    {"field": "ItemName",            "header": "ItemName",            "type": "text"},
    {"field": "UnitPrice",           "header": "UnitPrice",           "type": "money"},
    {"field": "Status",              "header": "Status",              "type": "text"},
    {"field": "Fulfillment %",       "header": "Fulfillment %",       "type": "percent"},
    {"field": "QtyOrdered",          "header": "QtyOrdered",          "type": "int"},
    {"field": "QtyReserved",         "header": "QtyReserved",         "type": "int"},
    {"field": "QtyReleased",         "header": "QTY Shipping",        "type": "int"},
    {"field": "QtyCancelled",        "header": "QtyCancelled",        "type": "int"},
    {"field": "QtyLeftToShip",       "header": "Qty left to ship",    "type": "int"},
    {"field": "Ordered $",           "header": "Ordered $",           "type": "money"},
    {"field": "Cancelled $",         "header": "Cancelled $",         "type": "money"},
    {"field": "Released $",          "header": "Shipping $",          "type": "money"},
    {"field": "Open $",              "header": "Open $",              "type": "money"},
]

_AGG_QTY_COLS = [
    {"field": "QtyOrdered", "header": "QtyOrdered", "type": "int"},
    {"field": "QtyReserved", "header": "QtyReserved", "type": "int"},
    {"field": "QtyReleased", "header": "QTY Shipping", "type": "int"},
    {"field": "QtyCancelled", "header": "QtyCancelled", "type": "int"},
    {"field": "QtyLeftToShip", "header": "Qty left to ship", "type": "int"},
]
_AGG_DOL_COLS = [
    {"field": f, "header": _DOL_HEADERS[f], "type": "money"} for f in _DOL
]
_FF_COL = {"field": "Fulfillment %", "header": "Fulfillment %", "type": "percent"}

BY_CUSTOMER_COLS = [
    {"field": "CustomerAccount", "header": "CustomerAccount", "type": "text"},
    {"field": "CustomerName",    "header": "CustomerName",    "type": "text"},
    {"field": "Salesman",        "header": "Salesman",        "type": "text"},
    _FF_COL, *_AGG_QTY_COLS, *_AGG_DOL_COLS,
]
BY_ITEM_COLS = [
    {"field": "Item#",               "header": "Item#",               "type": "text"},
    {"field": "ItemName",            "header": "ItemName",            "type": "text"},
    {"field": "purchid",             "header": "purchid",             "type": "text"},
    {"field": "ExpectedArrivalDate", "header": "ExpectedArrivalDate", "type": "date"},
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
    {"field": "purchid",                  "header": "purchid",                  "type": "text"},
    {"field": "ExpectedArrivalDate",      "header": "ExpectedArrivalDate",      "type": "date"},
    {"field": "QtyOrdered",               "header": "QtyOrdered",               "type": "int"},
    {"field": "QtyReserved",              "header": "QtyReserved",              "type": "int"},
    {"field": "QtyReleased",              "header": "QTY Shipping",             "type": "int"},
    {"field": "QtyCancelled",             "header": "QtyCancelled",             "type": "int"},
    {"field": "QtyLeftToShip",            "header": "Qty left to ship",         "type": "int"},
    {"field": "Net Price",                "header": "Net Price",                "type": "money"},
    {"field": "Extended Price - Ordered", "header": "Extended Price - Ordered", "type": "money"},
    {"field": "Extended Price Cancelled", "header": "Extended Price Cancelled", "type": "money"},
    {"field": "Extended Price Remainder", "header": "Extended Price Remainder", "type": "money"},
]


# --------------------------------------------------------------------------- #
# Per-line normalization
# --------------------------------------------------------------------------- #


def classify_line(f: OrderLineFact) -> dict:
    """Legacy line shape for Customer's Last Order (salesline_release).

    Kept separate from the Ordered report's SP qty columns so CLO still shows
    QtyShipped / QtyOpen from the older SP that actually has shipped qty.
    """
    qty_ord = f.qty_ordered
    qty_shipped = f.qty_shipped
    qty_cancelled = f.qty_cancelled
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
        "Open $":           round(f.ordered_dollars - f.shipped_dollars - f.cancelled_dollars, 2),
    }


def _classify_ordered_line(f: OrderLineFact) -> dict:
    """Ordered report line: SP qty columns + SP dollars."""
    open_dollars = round(f.ordered_dollars - f.shipped_dollars - f.cancelled_dollars, 2)
    shipping = round(f.shipping_dollars, 2)
    return {
        "SalesOrderNumber": f.sales_order_number,
        "SalesOrderName":   f.sales_order_name,
        "CustomerAccount":  f.customer_account,
        "CustomerName":     f.customer_name,
        "Salesman":         f.sales_group,
        "OrderDate":        f.order_date,
        "purchid":          f.purch_id,
        "ExpectedArrivalDate": f.expected_arrival_date,
        "ShipDate":         f.ship_date,
        "PO #":             f.po_number,
        "LineNumber":       f.line_number,
        "Item#":            f.item_number,
        "ItemName":         f.item_name,
        "UnitPrice":        f.unit_price,
        "OrderStatus":      f.order_status,
        "Status":           f.status,
        "Fulfillment %":    _ff_pct(f.qty_ordered, f.qty_cancelled),
        "QtyOrdered":       f.qty_ordered,
        "QtyReserved":      f.qty_reserved,
        "QtyReleased":      f.qty_released,
        "QtyCancelled":     f.qty_cancelled,
        "QtyLeftToShip":    f.delivery_remainder,
        "Ordered $":        f.ordered_dollars,
        "Shipped $":        f.shipped_dollars,
        "Cancelled $":      f.cancelled_dollars,
        "Released $":       shipping,
        "Open $":           open_dollars,
        "Extended Price Remainder": shipping,
    }


def _ff_pct(qty_ordered: float, qty_cancelled: float) -> float | None:
    """(QtyOrdered - QtyCancelled) / QtyOrdered, clipped 0–1. Same as live Ordered."""
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
        row.update({f: b[f] for f in _QTY})
        row.update({f: round(b[f], 2) for f in _DOL})
        row["Fulfillment %"] = _ff_pct(b["QtyOrdered"], b["QtyCancelled"])
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
                "purchid": ln["purchid"],
                "ExpectedArrivalDate": ln["ExpectedArrivalDate"],
                "QtyOrdered": 0, "QtyReserved": 0, "QtyReleased": 0,
                "QtyCancelled": 0, "QtyLeftToShip": 0,
                "Extended Price - Ordered": 0.0, "Extended Price Cancelled": 0.0,
                "Extended Price Remainder": 0.0,
            }
        g["QtyOrdered"] += ln["QtyOrdered"]
        g["QtyReserved"] += ln["QtyReserved"]
        g["QtyReleased"] += ln["QtyReleased"]
        g["QtyCancelled"] += ln["QtyCancelled"]
        g["QtyLeftToShip"] += ln["QtyLeftToShip"]
        g["Extended Price - Ordered"] += ln["Ordered $"]
        g["Extended Price Cancelled"] += ln["Cancelled $"]
        g["Extended Price Remainder"] += ln["Extended Price Remainder"]

    for g in grouped.values():
        qo = g["QtyOrdered"]
        g["Net Price"] = round(g["Extended Price - Ordered"] / qo, 4) if qo else 0.0
        g["Extended Price - Ordered"] = round(g["Extended Price - Ordered"], 2)
        g["Extended Price Cancelled"] = round(g["Extended Price Cancelled"], 2)
        g["Extended Price Remainder"] = round(g["Extended Price Remainder"], 2)

    return _tab(
        "summary", "Summary", SUMMARY_COLS, list(grouped.values()),
        stub=(),
        default_layout={
            "group_levels": ["Customer Name"],
            "sort_levels": [{"field": "Customer Name", "dir": "asc"},
                            {"field": "Item Number", "dir": "asc"}],
        },
    )


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def _classify_lines(facts: Iterable[OrderLineFact]) -> list[dict]:
    """Turn facts into Ordered report rows, dropping ERROR ITEM lines."""
    if not isinstance(facts, list):
        return [ln for ln in (_classify_ordered_line(f) for f in facts) if not _is_error_item(ln)]
    lines: list[dict] = []
    for i in range(len(facts)):
        line = _classify_ordered_line(facts[i])
        facts[i] = None
        if not _is_error_item(line):
            lines.append(line)
    return lines


def build(facts: Iterable[OrderLineFact], *, skip_by_salesman: bool = False) -> list[dict]:
    lines = _classify_lines(facts)

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
        lead=lambda r: {"Item#": r["Item#"] or "(none)", "ItemName": r["ItemName"],
                        "purchid": r["purchid"],
                        "ExpectedArrivalDate": r["ExpectedArrivalDate"]},
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

    summary = _build_summary(lines)
    salesman_group = [] if skip_by_salesman else ["Salesman"]
    summary["default_group"] = salesman_group

    tabs = [
        summary,
        _tab("by_customer", "By Customer", BY_CUSTOMER_COLS, by_customer, stub=STUB_FIELDS,
             default_group=salesman_group),
        _tab("by_item", "By Item", BY_ITEM_COLS, by_item, stub=STUB_FIELDS),
        _tab("by_order", "By Order", BY_ORDER_COLS, by_order, stub=STUB_FIELDS,
             default_group=salesman_group),
    ]
    if not skip_by_salesman:
        by_salesman = _aggregate(
            lines,
            key=lambda r: (r["Salesman"] or "(none)",),
            lead=lambda r: {"Salesman": r["Salesman"] or "(none)"},
            sort=_by_ordered_desc,
        )
        tabs.append(_tab("by_salesman", "By Salesman", BY_SALESMAN_COLS, by_salesman, stub=STUB_FIELDS))
    tabs.append(_tab("full_data", "Full Data", FULL_DATA_COLS, lines, stub=STUB_FIELDS))
    return tabs
