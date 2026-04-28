"""Ordered report builder.

Transforms the flat sales-order-line dump from SQL (or the JSON fixture
fallback) into the multi-tab payload the report viewer / Excel export
already understand.

Input shape (one dict per sales order line) — based on the test dump
and the existing live runbook:

    Company, CustomerAccount, customername, SalesOrderNumber,
    CustomerRequisition, SalesGroup, LineNumber, SalesStatus,
    Item, ItemDescription,
    QuantityOrdered, QuantityReserved, ReleasedQuantity,
    DeliveryRemainder, QuantityLefttoLoad,
    SalesPrice, "Ordered $", "Shipped $", "Cancelled $",
    CreatedDateTime, ShippingDateRequested,
    InventoryTransactionID, SalesLineRecordHash, WHSSalesLineRecordHash

Output tabs (modeled after reports/ordered/writer.py in the live app):

    1. Summary     — totals + status mix
    2. By Customer — one row per customer with rolled-up dollars
    3. By Item     — one row per item with rolled-up dollars
    4. By Order    — one row per sales order
    5. Full Data   — every line, all columns
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------


# Full Data: mirror the SP output 1-for-1 so users can see / hide / move
# every column. Order matches the SP field order, not the dump order, so
# the most important fields land first.
FULL_DATA_COLS: list[dict[str, str]] = [
    {"field": "Company",                "header": "Company",            "type": "text"},
    {"field": "CustomerAccount",        "header": "Customer #",         "type": "text"},
    {"field": "customername",           "header": "Customer Name",      "type": "text"},
    {"field": "SalesOrderNumber",       "header": "Sales Order #",      "type": "text"},
    {"field": "CustomerRequisition",    "header": "Customer PO",        "type": "text"},
    {"field": "SalesGroup",             "header": "Salesman",           "type": "text"},
    {"field": "LineNumber",             "header": "Line #",             "type": "int"},
    {"field": "SalesStatus",            "header": "Status",             "type": "text"},
    {"field": "Item",                   "header": "Item",               "type": "text"},
    {"field": "ItemDescription",        "header": "Description",        "type": "text"},
    {"field": "QuantityOrdered",        "header": "Qty Ordered",        "type": "int"},
    {"field": "QuantityReserved",       "header": "Qty Reserved",       "type": "int"},
    {"field": "ReleasedQuantity",       "header": "Qty Released",       "type": "int"},
    {"field": "DeliveryRemainder",      "header": "Qty Remaining",      "type": "int"},
    {"field": "QuantityLefttoLoad",     "header": "Qty Left to Load",   "type": "int"},
    {"field": "SalesPrice",             "header": "Sales Price",        "type": "money"},
    {"field": "OrderedAmount",          "header": "Ordered $",          "type": "money"},
    {"field": "ShippedAmount",          "header": "Shipped $",          "type": "money"},
    {"field": "CancelledAmount",        "header": "Cancelled $",        "type": "money"},
    {"field": "RemainingAmount",        "header": "Remaining $",        "type": "money"},
    {"field": "CreatedDateTime",        "header": "Created",            "type": "date"},
    {"field": "ShippingDateRequested",  "header": "Ship Date Requested","type": "date"},
    {"field": "InventoryTransactionID", "header": "Inventory Trans ID", "type": "text"},
]

BY_CUSTOMER_COLS = [
    {"field": "CustomerAccount",  "header": "Customer #",     "type": "text"},
    {"field": "customername",     "header": "Customer Name",  "type": "text"},
    {"field": "SalesGroup",       "header": "Salesman",       "type": "text"},
    {"field": "OrderCount",       "header": "# Orders",       "type": "int"},
    {"field": "LineCount",        "header": "# Lines",        "type": "int"},
    {"field": "QuantityOrdered",  "header": "Qty Ordered",    "type": "int"},
    {"field": "OrderedAmount",    "header": "Ordered $",      "type": "money"},
    {"field": "ShippedAmount",    "header": "Shipped $",      "type": "money"},
    {"field": "CancelledAmount",  "header": "Cancelled $",    "type": "money"},
    {"field": "RemainingAmount",  "header": "Remaining $",    "type": "money"},
]

BY_ITEM_COLS = [
    {"field": "Item",             "header": "Item",           "type": "text"},
    {"field": "ItemDescription",  "header": "Description",    "type": "text"},
    {"field": "OrderCount",       "header": "# Orders",       "type": "int"},
    {"field": "QuantityOrdered",  "header": "Qty Ordered",    "type": "int"},
    {"field": "OrderedAmount",    "header": "Ordered $",      "type": "money"},
    {"field": "ShippedAmount",    "header": "Shipped $",      "type": "money"},
    {"field": "CancelledAmount",  "header": "Cancelled $",    "type": "money"},
    {"field": "RemainingAmount",  "header": "Remaining $",    "type": "money"},
]

BY_ORDER_COLS = [
    {"field": "SalesOrderNumber",    "header": "Sales Order #",   "type": "text"},
    {"field": "CreatedDateTime",     "header": "Created",         "type": "date"},
    {"field": "CustomerAccount",     "header": "Customer #",      "type": "text"},
    {"field": "customername",        "header": "Customer Name",   "type": "text"},
    {"field": "CustomerRequisition", "header": "Customer PO",     "type": "text"},
    {"field": "SalesGroup",          "header": "Salesman",        "type": "text"},
    {"field": "SalesStatus",         "header": "Status",          "type": "text"},
    {"field": "LineCount",           "header": "# Lines",         "type": "int"},
    {"field": "QuantityOrdered",     "header": "Qty Ordered",     "type": "int"},
    {"field": "OrderedAmount",       "header": "Ordered $",       "type": "money"},
    {"field": "ShippedAmount",       "header": "Shipped $",       "type": "money"},
    {"field": "CancelledAmount",     "header": "Cancelled $",     "type": "money"},
    {"field": "RemainingAmount",     "header": "Remaining $",     "type": "money"},
]

SUMMARY_COLS = [
    {"field": "Metric", "header": "Metric", "type": "text"},
    {"field": "Value",  "header": "Value",  "type": "text"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _num(v: Any) -> float:
    """Coerce to float, treating None / blanks / 'NULL' as 0."""
    if v is None or v == "" or v == "NULL":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _int(v: Any) -> int:
    return int(round(_num(v)))


def _str(v: Any) -> str:
    if v is None or v == "NULL":
        return ""
    return str(v)


def _norm_row(raw: dict) -> dict:
    """Normalise a SP row: rename `Ordered $` -> `OrderedAmount`, fill blanks,
    derive `RemainingAmount = Ordered - Shipped - Cancelled`.
    """
    ordered = _num(raw.get("Ordered $"))
    shipped = _num(raw.get("Shipped $"))
    cancelled = _num(raw.get("Cancelled $"))
    remaining = round(ordered - shipped - cancelled, 2)

    return {
        "Company":              _str(raw.get("Company")),
        "CustomerAccount":      _str(raw.get("CustomerAccount")),
        "customername":         _str(raw.get("customername")),
        "SalesOrderNumber":     _str(raw.get("SalesOrderNumber")),
        "CustomerRequisition":  _str(raw.get("CustomerRequisition")),
        "SalesGroup":           _str(raw.get("SalesGroup")),
        "LineNumber":           _int(raw.get("LineNumber")),
        "SalesStatus":          _str(raw.get("SalesStatus")),
        "Item":                 _str(raw.get("Item")),
        "ItemDescription":      _str(raw.get("ItemDescription")),
        "QuantityOrdered":      _int(raw.get("QuantityOrdered")),
        "QuantityReserved":     _int(raw.get("QuantityReserved")),
        "ReleasedQuantity":     _int(raw.get("ReleasedQuantity")),
        "DeliveryRemainder":    _int(raw.get("DeliveryRemainder")),
        "QuantityLefttoLoad":   _int(raw.get("QuantityLefttoLoad")),
        "SalesPrice":           round(_num(raw.get("SalesPrice")), 4),
        "OrderedAmount":        round(ordered, 2),
        "ShippedAmount":        round(shipped, 2),
        "CancelledAmount":      round(cancelled, 2),
        "RemainingAmount":      remaining,
        "CreatedDateTime":      _str(raw.get("CreatedDateTime")),
        "ShippingDateRequested":_str(raw.get("ShippingDateRequested")),
        "InventoryTransactionID": _str(raw.get("InventoryTransactionID")),
    }


_DOLLAR_FIELDS = ("OrderedAmount", "ShippedAmount", "CancelledAmount", "RemainingAmount")


def _empty_bucket() -> dict[str, Any]:
    return {
        "QuantityOrdered": 0,
        "OrderedAmount":   0.0,
        "ShippedAmount":   0.0,
        "CancelledAmount": 0.0,
        "RemainingAmount": 0.0,
        "_orders":         set(),
        "LineCount":       0,
    }


def _accumulate(bucket: dict, line: dict) -> None:
    bucket["QuantityOrdered"] += line["QuantityOrdered"]
    for f in _DOLLAR_FIELDS:
        bucket[f] += line[f]
    bucket["_orders"].add(line["SalesOrderNumber"])
    bucket["LineCount"] += 1


def _round_money(d: dict) -> None:
    for f in _DOLLAR_FIELDS:
        if f in d:
            d[f] = round(d[f], 2)


# ---------------------------------------------------------------------------
# Tab builders
# ---------------------------------------------------------------------------


def _build_full_data(lines: list[dict]) -> dict:
    return {
        "key":     "full_data",
        "name":    "Full Data",
        "columns": FULL_DATA_COLS,
        "rows":    lines,
    }


def _build_by_customer(lines: list[dict]) -> dict:
    buckets: dict[str, dict] = {}
    meta: dict[str, dict] = {}
    for ln in lines:
        cust = ln["CustomerAccount"] or "(none)"
        if cust not in buckets:
            buckets[cust] = _empty_bucket()
            meta[cust] = {
                "customername": ln["customername"],
                "SalesGroup":   ln["SalesGroup"],
            }
        _accumulate(buckets[cust], ln)

    rows = []
    for cust, b in buckets.items():
        m = meta[cust]
        rows.append({
            "CustomerAccount": cust,
            "customername":    m["customername"],
            "SalesGroup":      m["SalesGroup"],
            "OrderCount":      len(b["_orders"]),
            "LineCount":       b["LineCount"],
            "QuantityOrdered": b["QuantityOrdered"],
            "OrderedAmount":   round(b["OrderedAmount"], 2),
            "ShippedAmount":   round(b["ShippedAmount"], 2),
            "CancelledAmount": round(b["CancelledAmount"], 2),
            "RemainingAmount": round(b["RemainingAmount"], 2),
        })

    rows.sort(key=lambda r: -r["OrderedAmount"])
    return {
        "key":     "by_customer",
        "name":    "By Customer",
        "columns": BY_CUSTOMER_COLS,
        "rows":    rows,
    }


def _build_by_item(lines: list[dict]) -> dict:
    buckets: dict[str, dict] = {}
    meta: dict[str, dict] = {}
    for ln in lines:
        item = ln["Item"] or "(none)"
        if item not in buckets:
            buckets[item] = _empty_bucket()
            meta[item] = {"ItemDescription": ln["ItemDescription"]}
        _accumulate(buckets[item], ln)

    rows = []
    for item, b in buckets.items():
        rows.append({
            "Item":            item,
            "ItemDescription": meta[item]["ItemDescription"],
            "OrderCount":      len(b["_orders"]),
            "QuantityOrdered": b["QuantityOrdered"],
            "OrderedAmount":   round(b["OrderedAmount"], 2),
            "ShippedAmount":   round(b["ShippedAmount"], 2),
            "CancelledAmount": round(b["CancelledAmount"], 2),
            "RemainingAmount": round(b["RemainingAmount"], 2),
        })
    rows.sort(key=lambda r: -r["OrderedAmount"])
    return {
        "key":     "by_item",
        "name":    "By Item",
        "columns": BY_ITEM_COLS,
        "rows":    rows,
    }


def _build_by_order(lines: list[dict]) -> dict:
    buckets: dict[str, dict] = {}
    meta: dict[str, dict] = {}
    for ln in lines:
        so = ln["SalesOrderNumber"] or "(none)"
        if so not in buckets:
            buckets[so] = _empty_bucket()
            meta[so] = {
                "CreatedDateTime":     ln["CreatedDateTime"],
                "CustomerAccount":     ln["CustomerAccount"],
                "customername":        ln["customername"],
                "CustomerRequisition": ln["CustomerRequisition"],
                "SalesGroup":          ln["SalesGroup"],
                "SalesStatus":         ln["SalesStatus"],
            }
        _accumulate(buckets[so], ln)

    rows = []
    for so, b in buckets.items():
        m = meta[so]
        rows.append({
            "SalesOrderNumber":    so,
            "CreatedDateTime":     m["CreatedDateTime"],
            "CustomerAccount":     m["CustomerAccount"],
            "customername":        m["customername"],
            "CustomerRequisition": m["CustomerRequisition"],
            "SalesGroup":          m["SalesGroup"],
            "SalesStatus":         m["SalesStatus"],
            "LineCount":           b["LineCount"],
            "QuantityOrdered":     b["QuantityOrdered"],
            "OrderedAmount":       round(b["OrderedAmount"], 2),
            "ShippedAmount":       round(b["ShippedAmount"], 2),
            "CancelledAmount":     round(b["CancelledAmount"], 2),
            "RemainingAmount":     round(b["RemainingAmount"], 2),
        })
    rows.sort(key=lambda r: r["CreatedDateTime"], reverse=True)
    return {
        "key":     "by_order",
        "name":    "By Order",
        "columns": BY_ORDER_COLS,
        "rows":    rows,
    }


def _build_summary(lines: list[dict]) -> dict:
    if not lines:
        rows = [
            {"Metric": "Lines", "Value": "0"},
        ]
        return {"key": "summary", "name": "Summary", "columns": SUMMARY_COLS, "rows": rows}

    total = _empty_bucket()
    statuses: dict[str, float] = defaultdict(float)
    for ln in lines:
        _accumulate(total, ln)
        statuses[ln["SalesStatus"] or "(blank)"] += ln["OrderedAmount"]

    def _money(v: float) -> str:
        return f"${v:,.2f}"

    rows = [
        {"Metric": "Lines",          "Value": f"{total['LineCount']:,}"},
        {"Metric": "Distinct Orders","Value": f"{len(total['_orders']):,}"},
        {"Metric": "Qty Ordered",    "Value": f"{total['QuantityOrdered']:,}"},
        {"Metric": "Ordered $",      "Value": _money(total["OrderedAmount"])},
        {"Metric": "Shipped $",      "Value": _money(total["ShippedAmount"])},
        {"Metric": "Cancelled $",    "Value": _money(total["CancelledAmount"])},
        {"Metric": "Remaining $",    "Value": _money(total["RemainingAmount"])},
    ]
    for status, amt in sorted(statuses.items(), key=lambda kv: -kv[1]):
        rows.append({"Metric": f"Status: {status}", "Value": _money(amt)})

    return {"key": "summary", "name": "Summary", "columns": SUMMARY_COLS, "rows": rows}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build(rows: Iterable[dict]) -> list[dict]:
    """Turn flat SP rows into the multi-tab payload for the viewer."""
    lines = [_norm_row(r) for r in rows]
    return [
        _build_summary(lines),
        _build_by_customer(lines),
        _build_by_item(lines),
        _build_by_order(lines),
        _build_full_data(lines),
    ]
