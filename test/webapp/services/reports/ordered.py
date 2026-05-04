"""Ordered report builder.

Mirrors the live ``reports/ordered/writer.py`` shape so the test sandbox
shows the same columns, the same tabs, and the same totals the users
already trust. Source data is the ``salesline_release`` SP (HTTP
Reporting API) -- a flat sales-order-line dump.

Field mapping from SP -> live-style column names::

    SalesGroup       -> Salesman
    customername     -> CustomerName
    Item             -> Item#
    ItemDescription  -> ItemName
    SalesStatus      -> Status
    SalesPrice       -> UnitPrice
    CreatedDateTime  -> OrderDate
    CustomerRequisition -> PO #   (only on the By Order tab)

The SP doesn't return separate Shipped/Cancelled/Released/Open quantities
so we derive them from the dollar columns it DOES return + status::

    QtyCancelled = QuantityOrdered          when SalesStatus == 'Cancelled', else 0
    QtyShipped   = QuantityOrdered - DeliveryRemainder - QuantityLefttoLoad - QtyCancelled
    QtyReleased  = ReleasedQuantity
    QtyOpen      = max(0, QuantityOrdered - QtyShipped - QtyCancelled)
    Released $   = QtyReleased * UnitPrice
    Open $       = max(0, Ordered $ - Shipped $ - Cancelled $)

Tabs (in order):
    1. Summary     -- live-shape: grouped by Customer with per-customer
                      Total + spacer + GRAND TOTAL.
    2. By Customer -- one row per (Customer, Salesman) with Fulfillment %.
    3. By Item     -- one row per item with Fulfillment %.
    4. By Order    -- one row per sales order; CustomerRequisition shown
                      as "PO #".
    5. By Salesman -- one row per salesman with Fulfillment %.
    6. Full Data   -- every line, in FULL_DATA_ORDER.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Column definitions (live names; live order)
# ---------------------------------------------------------------------------


# Order matches reports/ordered/builder.py FULL_DATA_ORDER.
FULL_DATA_COLS: list[dict[str, str]] = [
    {"field": "SalesOrderNumber",  "header": "SalesOrderNumber",  "type": "text"},
    {"field": "CustomerAccount",   "header": "CustomerAccount",   "type": "text"},
    {"field": "CustomerName",      "header": "CustomerName",      "type": "text"},
    {"field": "Salesman",          "header": "Salesman",          "type": "text"},
    {"field": "OrderDate",         "header": "OrderDate",         "type": "date"},
    {"field": "PO #",              "header": "PO #",              "type": "text"},
    {"field": "LineNumber",        "header": "LineNumber",        "type": "int"},
    {"field": "Item#",             "header": "Item#",             "type": "text"},
    {"field": "ItemName",          "header": "ItemName",          "type": "text"},
    {"field": "UnitPrice",         "header": "UnitPrice",         "type": "money"},
    {"field": "Status",            "header": "Status",            "type": "text"},
    {"field": "Fulfillment %",     "header": "Fulfillment %",     "type": "percent"},
    {"field": "QtyOrdered",        "header": "QtyOrdered",        "type": "int"},
    {"field": "QtyShipped",        "header": "QtyShipped",        "type": "int"},
    {"field": "QtyCancelled",      "header": "QtyCancelled",      "type": "int"},
    {"field": "QtyReleased",       "header": "QtyReleased",       "type": "int"},
    {"field": "QtyOpen",           "header": "QtyOpen",           "type": "int"},
    {"field": "Ordered $",         "header": "Ordered $",         "type": "money"},
    {"field": "Shipped $",         "header": "Shipped $",         "type": "money"},
    {"field": "Cancelled $",       "header": "Cancelled $",       "type": "money"},
    {"field": "Released $",        "header": "Released $",        "type": "money"},
    {"field": "Open $",            "header": "Open $",            "type": "money"},
]


# Aggregated tabs: Customer / Salesman lead + dollar columns + Fulfillment %.
_AGG_QTY_COLS = [
    {"field": "QtyOrdered",   "header": "QtyOrdered",   "type": "int"},
    {"field": "QtyShipped",   "header": "QtyShipped",   "type": "int"},
    {"field": "QtyCancelled", "header": "QtyCancelled", "type": "int"},
    {"field": "QtyReleased",  "header": "QtyReleased",  "type": "int"},
    {"field": "QtyOpen",      "header": "QtyOpen",      "type": "int"},
]
_AGG_DOL_COLS = [
    {"field": "Ordered $",    "header": "Ordered $",    "type": "money"},
    {"field": "Shipped $",    "header": "Shipped $",    "type": "money"},
    {"field": "Cancelled $",  "header": "Cancelled $",  "type": "money"},
    {"field": "Released $",   "header": "Released $",   "type": "money"},
    {"field": "Open $",       "header": "Open $",       "type": "money"},
]

BY_CUSTOMER_COLS = (
    [
        {"field": "CustomerAccount", "header": "CustomerAccount", "type": "text"},
        {"field": "CustomerName",    "header": "CustomerName",    "type": "text"},
        {"field": "Salesman",        "header": "Salesman",        "type": "text"},
        {"field": "Fulfillment %",   "header": "Fulfillment %",   "type": "percent"},
    ]
    + _AGG_QTY_COLS
    + _AGG_DOL_COLS
)

BY_ITEM_COLS = (
    [
        {"field": "Item#",          "header": "Item#",          "type": "text"},
        {"field": "ItemName",       "header": "ItemName",       "type": "text"},
        {"field": "Fulfillment %",  "header": "Fulfillment %",  "type": "percent"},
    ]
    + _AGG_QTY_COLS
    + _AGG_DOL_COLS
)

BY_ORDER_COLS = (
    [
        {"field": "SalesOrderNumber", "header": "SalesOrderNumber", "type": "text"},
        {"field": "OrderDate",        "header": "OrderDate",        "type": "date"},
        {"field": "CustomerAccount",  "header": "CustomerAccount",  "type": "text"},
        {"field": "CustomerName",     "header": "CustomerName",     "type": "text"},
        {"field": "Salesman",         "header": "Salesman",         "type": "text"},
        {"field": "PO #",             "header": "PO #",             "type": "text"},
        {"field": "Status",           "header": "Status",           "type": "text"},
        {"field": "Fulfillment %",    "header": "Fulfillment %",    "type": "percent"},
    ]
    + _AGG_QTY_COLS
    + _AGG_DOL_COLS
)

BY_SALESMAN_COLS = (
    [
        {"field": "Salesman",        "header": "Salesman",        "type": "text"},
        {"field": "Fulfillment %",   "header": "Fulfillment %",   "type": "percent"},
    ]
    + _AGG_QTY_COLS
    + _AGG_DOL_COLS
)

# Live-shape Summary: per-customer rolled up to (item) lines, with
# `_is_total` / `_is_spacer` flag rows so the grid + Excel export can
# render them as bold totals + skipped rows.
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


def _date_only(v: Any) -> str:
    """Trim 'YYYY-MM-DDTHH:MM:SS' to 'YYYY-MM-DD' for OrderDate."""
    s = _str(v)
    return s[:10] if len(s) >= 10 else s


def _norm_row(raw: dict) -> dict:
    """Map an SP row onto live-style column names + derive the missing qty/$ columns."""
    qty_ord     = _int(raw.get("QuantityOrdered"))
    qty_release = _int(raw.get("ReleasedQuantity"))
    qty_remain  = _int(raw.get("DeliveryRemainder"))
    qty_load    = _int(raw.get("QuantityLefttoLoad"))
    status      = _str(raw.get("SalesStatus"))

    ordered_d   = round(_num(raw.get("Ordered $")), 2)
    shipped_d   = round(_num(raw.get("Shipped $")), 2)
    cancelled_d = round(_num(raw.get("Cancelled $")), 2)
    unit_price  = round(_num(raw.get("SalesPrice")), 4)

    is_cancelled = status.lower() == "cancelled"
    qty_cancelled = qty_ord if is_cancelled else 0
    qty_shipped = max(0, qty_ord - qty_remain - qty_load - qty_cancelled)
    qty_open    = max(0, qty_ord - qty_shipped - qty_cancelled)
    released_d  = round(qty_release * unit_price, 2)
    open_d      = round(max(0.0, ordered_d - shipped_d - cancelled_d), 2)

    fulfillment = (qty_ord - qty_cancelled) / qty_ord if qty_ord > 0 else None

    return {
        "Company":           _str(raw.get("Company")),
        "CustomerAccount":   _str(raw.get("CustomerAccount")),
        "CustomerName":      _str(raw.get("customername")),
        "Salesman":          _str(raw.get("SalesGroup")),
        "SalesOrderNumber":  _str(raw.get("SalesOrderNumber")),
        "PO #":              _str(raw.get("CustomerRequisition")),
        "LineNumber":        _int(raw.get("LineNumber")),
        "Status":            status,
        "Item#":             _str(raw.get("Item")),
        "ItemName":          _str(raw.get("ItemDescription")),
        "UnitPrice":         unit_price,
        "OrderDate":         _date_only(raw.get("CreatedDateTime")),

        "QtyOrdered":        qty_ord,
        "QtyShipped":        qty_shipped,
        "QtyCancelled":      qty_cancelled,
        "QtyReleased":       qty_release,
        "QtyOpen":           qty_open,

        "Ordered $":         ordered_d,
        "Shipped $":         shipped_d,
        "Cancelled $":       cancelled_d,
        "Released $":        released_d,
        "Open $":            open_d,

        "Fulfillment %":     fulfillment,
    }


_SUM_QTY_FIELDS = ("QtyOrdered", "QtyShipped", "QtyCancelled", "QtyReleased", "QtyOpen")
_SUM_DOL_FIELDS = ("Ordered $", "Shipped $", "Cancelled $", "Released $", "Open $")


def _empty_bucket() -> dict[str, Any]:
    return {
        **{f: 0   for f in _SUM_QTY_FIELDS},
        **{f: 0.0 for f in _SUM_DOL_FIELDS},
        "_orders": set(),
    }


def _accumulate(bucket: dict, line: dict) -> None:
    for f in _SUM_QTY_FIELDS:
        bucket[f] += line[f]
    for f in _SUM_DOL_FIELDS:
        bucket[f] += line[f]
    bucket["_orders"].add(line["SalesOrderNumber"])


def _round_bucket(b: dict) -> None:
    for f in _SUM_DOL_FIELDS:
        b[f] = round(b[f], 2)


def _ff_pct(qty_ord: float, qty_cancelled: float) -> float | None:
    """Same formula as live's `_fulfillment_score` but at aggregate level."""
    if qty_ord <= 1e-6:
        return None
    score = (qty_ord - qty_cancelled) / qty_ord
    if score < 0:
        score = 0.0
    if score > 1:
        score = 1.0
    return round(score, 4)


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
    buckets: dict[tuple, dict] = {}
    meta: dict[tuple, dict] = {}
    for ln in lines:
        key = (ln["CustomerAccount"] or "(none)", ln["Salesman"] or "")
        if key not in buckets:
            buckets[key] = _empty_bucket()
            meta[key] = {
                "CustomerName": ln["CustomerName"],
                "Salesman":     ln["Salesman"],
            }
        _accumulate(buckets[key], ln)

    rows = []
    for (cust, _), b in buckets.items():
        _round_bucket(b)
        m = meta[(cust, _)]
        rows.append({
            "CustomerAccount": cust,
            "CustomerName":    m["CustomerName"],
            "Salesman":        m["Salesman"],
            "Fulfillment %":   _ff_pct(b["QtyOrdered"], b["QtyCancelled"]),
            **{f: b[f] for f in _SUM_QTY_FIELDS},
            **{f: b[f] for f in _SUM_DOL_FIELDS},
        })

    rows.sort(key=lambda r: -float(r["Ordered $"] or 0))
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
        item = ln["Item#"] or "(none)"
        if item not in buckets:
            buckets[item] = _empty_bucket()
            meta[item] = {"ItemName": ln["ItemName"]}
        _accumulate(buckets[item], ln)

    rows = []
    for item, b in buckets.items():
        _round_bucket(b)
        rows.append({
            "Item#":         item,
            "ItemName":      meta[item]["ItemName"],
            "Fulfillment %": _ff_pct(b["QtyOrdered"], b["QtyCancelled"]),
            **{f: b[f] for f in _SUM_QTY_FIELDS},
            **{f: b[f] for f in _SUM_DOL_FIELDS},
        })
    rows.sort(key=lambda r: -float(r["Ordered $"] or 0))
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
                "OrderDate":       ln["OrderDate"],
                "CustomerAccount": ln["CustomerAccount"],
                "CustomerName":    ln["CustomerName"],
                "PO #":            ln["PO #"],
                "Salesman":        ln["Salesman"],
                "Status":          ln["Status"],
            }
        _accumulate(buckets[so], ln)

    rows = []
    for so, b in buckets.items():
        _round_bucket(b)
        m = meta[so]
        rows.append({
            "SalesOrderNumber": so,
            "OrderDate":        m["OrderDate"],
            "CustomerAccount":  m["CustomerAccount"],
            "CustomerName":     m["CustomerName"],
            "Salesman":         m["Salesman"],
            "PO #":             m["PO #"],
            "Status":           m["Status"],
            "Fulfillment %":    _ff_pct(b["QtyOrdered"], b["QtyCancelled"]),
            **{f: b[f] for f in _SUM_QTY_FIELDS},
            **{f: b[f] for f in _SUM_DOL_FIELDS},
        })
    rows.sort(key=lambda r: r["OrderDate"] or "", reverse=True)
    return {
        "key":     "by_order",
        "name":    "By Order",
        "columns": BY_ORDER_COLS,
        "rows":    rows,
    }


def _build_by_salesman(lines: list[dict]) -> dict:
    buckets: dict[str, dict] = {}
    for ln in lines:
        key = ln["Salesman"] or "(none)"
        if key not in buckets:
            buckets[key] = _empty_bucket()
        _accumulate(buckets[key], ln)

    rows = []
    for sm, b in buckets.items():
        _round_bucket(b)
        rows.append({
            "Salesman":      sm,
            "Fulfillment %": _ff_pct(b["QtyOrdered"], b["QtyCancelled"]),
            **{f: b[f] for f in _SUM_QTY_FIELDS},
            **{f: b[f] for f in _SUM_DOL_FIELDS},
        })
    rows.sort(key=lambda r: -float(r["Ordered $"] or 0))
    return {
        "key":     "by_salesman",
        "name":    "By Salesman",
        "columns": BY_SALESMAN_COLS,
        "rows":    rows,
    }


def _build_summary(lines: list[dict]) -> dict:
    """Live-shape Summary: rolled up to (Customer, Item) with per-customer
    Total + spacer + GRAND TOTAL.

    Output rows include two synthetic flags:
      - ``_is_total``  -> render bold (used for per-customer Total + GRAND TOTAL)
      - ``_is_spacer`` -> render as a blank row
    """
    if not lines:
        return {
            "key": "summary", "name": "Summary",
            "columns": SUMMARY_COLS, "rows": [],
        }

    # Roll up to (customer, item)
    grouped: dict[tuple, dict] = {}
    for ln in lines:
        cust = ln["CustomerName"] or ln["CustomerAccount"] or "(blank)"
        item = ln["Item#"] or "(blank)"
        key = (cust, item)
        if key not in grouped:
            grouped[key] = {
                "Customer Name":            cust,
                "Salesman":                 ln["Salesman"],
                "Item Number":              item,
                "Line Description":         ln["ItemName"],
                "QtyOrdered":               0,
                "QtyCancelled":             0,
                "QtyRemainder":             0,
                "Extended Price - Ordered": 0.0,
                "Extended Price Remainder": 0.0,
            }
        g = grouped[key]
        g["QtyOrdered"]               += ln["QtyOrdered"]
        g["QtyCancelled"]             += ln["QtyCancelled"]
        g["QtyRemainder"]             += ln["QtyOpen"]  # remainder = open
        g["Extended Price - Ordered"] += ln["Ordered $"]
        g["Extended Price Remainder"] += ln["Open $"]

    # Net Price = Ext Ordered / QtyOrdered (mirrors live)
    for g in grouped.values():
        qo = g["QtyOrdered"]
        g["Net Price"] = round(g["Extended Price - Ordered"] / qo, 4) if qo else 0.0
        g["Extended Price - Ordered"] = round(g["Extended Price - Ordered"], 2)
        g["Extended Price Remainder"] = round(g["Extended Price Remainder"], 2)

    # Sort by Customer then Item, then walk and inject totals + spacers.
    sorted_rows = sorted(grouped.values(), key=lambda r: (r["Customer Name"], r["Item Number"]))

    out: list[dict] = []
    by_cust: dict[str, list[dict]] = defaultdict(list)
    for r in sorted_rows:
        by_cust[r["Customer Name"]].append(r)

    grand = defaultdict(float)
    for cust in by_cust:  # preserves insertion order = sorted order
        cust_rows = by_cust[cust]
        for r in cust_rows:
            r["_is_total"]  = False
            r["_is_spacer"] = False
            out.append(r)

        # per-customer Total
        total = {c["field"]: "" for c in SUMMARY_COLS}
        total["Customer Name"]            = cust
        total["Salesman"]                 = cust_rows[0]["Salesman"] if cust_rows else ""
        total["Item Number"]              = "TOTALS"
        total["Line Description"]         = ""
        total["QtyOrdered"]               = sum(r["QtyOrdered"]   for r in cust_rows)
        total["QtyCancelled"]             = sum(r["QtyCancelled"] for r in cust_rows)
        total["QtyRemainder"]             = sum(r["QtyRemainder"] for r in cust_rows)
        total["Net Price"]                = ""
        total["Extended Price - Ordered"] = round(sum(r["Extended Price - Ordered"] for r in cust_rows), 2)
        total["Extended Price Remainder"] = round(sum(r["Extended Price Remainder"] for r in cust_rows), 2)
        total["_is_total"]  = True
        total["_is_spacer"] = False
        out.append(total)

        # spacer row
        spacer = {c["field"]: "" for c in SUMMARY_COLS}
        spacer["_is_total"]  = False
        spacer["_is_spacer"] = True
        out.append(spacer)

        # accumulate grand totals
        grand["QtyOrdered"]               += total["QtyOrdered"]
        grand["QtyCancelled"]             += total["QtyCancelled"]
        grand["QtyRemainder"]             += total["QtyRemainder"]
        grand["Extended Price - Ordered"] += total["Extended Price - Ordered"]
        grand["Extended Price Remainder"] += total["Extended Price Remainder"]

    grand_row = {c["field"]: "" for c in SUMMARY_COLS}
    grand_row["Customer Name"]            = "GRAND TOTAL"
    grand_row["Salesman"]                 = ""
    grand_row["Item Number"]              = ""
    grand_row["Line Description"]         = ""
    grand_row["QtyOrdered"]               = int(grand["QtyOrdered"])
    grand_row["QtyCancelled"]             = int(grand["QtyCancelled"])
    grand_row["QtyRemainder"]             = int(grand["QtyRemainder"])
    grand_row["Net Price"]                = ""
    grand_row["Extended Price - Ordered"] = round(grand["Extended Price - Ordered"], 2)
    grand_row["Extended Price Remainder"] = round(grand["Extended Price Remainder"], 2)
    grand_row["_is_total"]  = True
    grand_row["_is_spacer"] = False
    out.append(grand_row)

    return {
        "key":     "summary",
        "name":    "Summary",
        "columns": SUMMARY_COLS,
        "rows":    out,
    }


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
        _build_by_salesman(lines),
        _build_full_data(lines),
    ]
