"""Number 4 Report builder.

Mirrors the live ``reports/number_4`` workbook structure: invoice
line-level data pivoted to monthly qty + dollar columns, grouped two
ways (By Item, By Customer) and over two windows (rolling 12 months,
year-to-date).

Source data is the ``invoice_lines`` SP (HTTP Reporting API) which
returns one row per invoice line with these fields (see
``invoice_lines_frontend_handoff.md``):

    InvoiceAccount, CustomerName, InvoiceDate, Invoice, SalesOrder,
    Amount, SalesGroup, Item, ItemName, ExternalItemID, InventQTY,
    SalesPrice, InventCostAmount

We don't have BookPrice in this SP, so the Book Price column from the
live report is intentionally omitted from the test version.

Output tabs (in order):
    1. By Item -- 12 Months      (one row per (Item, Customer) pair)
    2. By Item -- Year to Date   (same shape, only the current YTD months)
    3. By Customer -- 12 Months  (one row per (Customer, Item) pair)
    4. By Customer -- Year to Date

Both "By Item" tabs pivot Qty per month. Both "By Customer" tabs
interleave Qty + $ per month, mirroring the live writer_customer
layout.
"""
from __future__ import annotations

import logging
from calendar import month_abbr
from datetime import date
from typing import Any, Iterable

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _num(v: Any) -> float:
    if v is None or v == "" or v == "NULL":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _str(v: Any) -> str:
    if v is None or v == "NULL":
        return ""
    return str(v)


def _first(raw: dict, *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", "NULL"):
            return value
    return None


def _ym_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_label(y: int, m: int) -> str:
    return f"{month_abbr[m]}-{str(y)[-2:]}"


def _rolling_12_months(today: date) -> list[tuple[int, int]]:
    out = []
    y, m = today.year, today.month
    for _ in range(12):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    out.reverse()
    return out


def _ytd_months(today: date) -> list[tuple[int, int]]:
    return [(today.year, m) for m in range(1, today.month + 1)]


def _load_salesman_map() -> dict[str, str]:
    """SalesGroup key -> display label (full_name fallback to the key)."""
    try:
        from test.webapp.db import list_salesman_map
        rows = list_salesman_map()
    except Exception:
        log.exception("number_4: failed to load app_salesmen")
        return {}
    out: dict[str, str] = {}
    for r in rows or []:
        key = (r.get("key") or "").strip().lower()
        if not key:
            continue
        out[key] = (r.get("display_name") or r.get("full_name") or "").strip()
    return out


def _norm_line(raw: dict, sm_map: dict[str, str]) -> dict | None:
    """Map an invoice_lines row onto an internal line dict.

    Returns None if the line has no InvoiceDate (can't bucket it) or
    no Item (can't aggregate it).
    """
    date_raw = _first(raw, "InvoiceDate", "Invoice Date")
    if not date_raw:
        return None
    date_str = str(date_raw)[:10]
    try:
        y = int(date_str[:4]); m = int(date_str[5:7]); d = int(date_str[8:10])
        dt = date(y, m, d)
    except (TypeError, ValueError):
        return None

    item = _str(_first(raw, "Item", "ItemId", "Item#", "ItemNumber"))
    if not item:
        return None

    qty = _num(_first(raw, "InventQTY", "Qty", "Quantity"))
    amount = _num(_first(raw, "Amount", "Total_$", "TotalAmount"))

    salesgroup = _str(_first(raw, "SalesGroup", "salesgroup", "Salesman"))
    sm_label = (sm_map.get(salesgroup.lower()) if salesgroup else "") or salesgroup or "Unassigned"

    return {
        "InvoiceDate":     dt,
        "_ym":             _ym_key(dt),
        "Item#":           item,
        "ItemName":        _str(_first(raw, "ItemName", "ItemDescription")),
        "CustomerAccount": _str(_first(raw, "InvoiceAccount", "CustomerAccount", "AccountNum")),
        "CustomerName":    _str(_first(raw, "CustomerName", "customername", "Name")),
        "Salesman":        sm_label,
        "Qty":             qty,
        "Total_$":         amount,
    }


# ---------------------------------------------------------------------------
# Pivot
# ---------------------------------------------------------------------------


def _aggregate(
    lines: list[dict],
    months: list[tuple[int, int]],
) -> tuple[dict[tuple, dict], list[str]]:
    """Group lines by (Item#, ItemName, CustomerAccount, CustomerName,
    Salesman) and bucket Qty + Total_$ per month.

    Returns ``(buckets, month_keys)`` where ``month_keys`` is the list
    of ``"YYYY-MM"`` strings in display order.
    """
    month_keys = [_ym_key(date(y, m, 1)) for y, m in months]
    month_set = set(month_keys)

    buckets: dict[tuple, dict] = {}

    for ln in lines:
        if ln["_ym"] not in month_set:
            continue
        key = (ln["Item#"], ln["CustomerAccount"])
        b = buckets.get(key)
        if b is None:
            b = {
                "Item#":           ln["Item#"],
                "ItemName":        ln["ItemName"],
                "CustomerAccount": ln["CustomerAccount"],
                "CustomerName":    ln["CustomerName"],
                "Salesman":        ln["Salesman"],
                **{f"{mk}_qty": 0.0 for mk in month_keys},
                **{f"{mk}_dol": 0.0 for mk in month_keys},
                "Total_Qty":       0.0,
                "Total_$":         0.0,
            }
            buckets[key] = b
        b[f"{ln['_ym']}_qty"] += ln["Qty"]
        b[f"{ln['_ym']}_dol"] += ln["Total_$"]
        b["Total_Qty"]        += ln["Qty"]
        b["Total_$"]          += ln["Total_$"]

    return buckets, month_keys


def _avg_price(total_dollars: float, total_qty: float) -> float | None:
    if total_qty in (0, 0.0):
        return None
    return round(total_dollars / total_qty, 4)


# ---------------------------------------------------------------------------
# Tab builders
# ---------------------------------------------------------------------------


def _build_by_item_tab(
    key: str,
    name: str,
    buckets: dict[tuple, dict],
    month_keys: list[str],
) -> dict:
    """One row per (Item, Customer). Shows monthly Qty only (no $ per month)."""
    columns: list[dict] = [
        {"field": "Item#",           "header": "Item #",        "type": "text"},
        {"field": "ItemName",        "header": "Item Name",     "type": "text"},
        {"field": "CustomerAccount", "header": "Customer #",    "type": "text"},
        {"field": "CustomerName",    "header": "Customer Name", "type": "text"},
    ]
    for mk in month_keys:
        y, m = int(mk[:4]), int(mk[5:7])
        columns.append({
            "field": f"{mk}_qty", "header": f"{_month_label(y, m)} Qty", "type": "int",
        })
    columns.extend([
        {"field": "Total_Qty", "header": "Total Qty", "type": "int"},
        {"field": "Total_$",   "header": "Total $",   "type": "money"},
        {"field": "Avg_Price", "header": "Avg Price", "type": "money"},
        {"field": "Salesman",  "header": "Salesman",  "type": "text"},
    ])

    rows = []
    for b in buckets.values():
        row = {
            "Item#":           b["Item#"],
            "ItemName":        b["ItemName"],
            "CustomerAccount": b["CustomerAccount"],
            "CustomerName":    b["CustomerName"],
            "Salesman":        b["Salesman"],
            "Total_Qty":       round(b["Total_Qty"], 2),
            "Total_$":         round(b["Total_$"], 2),
            "Avg_Price":       _avg_price(b["Total_$"], b["Total_Qty"]),
        }
        for mk in month_keys:
            row[f"{mk}_qty"] = round(b[f"{mk}_qty"], 2)
        rows.append(row)

    rows.sort(key=lambda r: (r["Item#"] or "", r["CustomerAccount"] or ""))

    return {"key": key, "name": name, "columns": columns, "rows": rows}


def _build_by_customer_tab(
    key: str,
    name: str,
    buckets: dict[tuple, dict],
    month_keys: list[str],
) -> dict:
    """One row per (Customer, Item). Interleaves Qty + $ per month."""
    columns: list[dict] = [
        {"field": "CustomerAccount", "header": "Customer #",    "type": "text"},
        {"field": "CustomerName",    "header": "Customer Name", "type": "text"},
        {"field": "Item#",           "header": "Item #",        "type": "text"},
        {"field": "ItemName",        "header": "Item Name",     "type": "text"},
    ]
    for mk in month_keys:
        y, m = int(mk[:4]), int(mk[5:7])
        lbl = _month_label(y, m)
        columns.append({"field": f"{mk}_qty", "header": f"{lbl} Qty", "type": "int"})
        columns.append({"field": f"{mk}_dol", "header": f"{lbl} $",   "type": "money"})
    columns.extend([
        {"field": "Total_Qty", "header": "Total Qty", "type": "int"},
        {"field": "Total_$",   "header": "Total $",   "type": "money"},
        {"field": "Avg_Price", "header": "Avg Price", "type": "money"},
        {"field": "Salesman",  "header": "Salesman",  "type": "text"},
    ])

    rows = []
    for b in buckets.values():
        row = {
            "CustomerAccount": b["CustomerAccount"],
            "CustomerName":    b["CustomerName"],
            "Item#":           b["Item#"],
            "ItemName":        b["ItemName"],
            "Salesman":        b["Salesman"],
            "Total_Qty":       round(b["Total_Qty"], 2),
            "Total_$":         round(b["Total_$"], 2),
            "Avg_Price":       _avg_price(b["Total_$"], b["Total_Qty"]),
        }
        for mk in month_keys:
            row[f"{mk}_qty"] = round(b[f"{mk}_qty"], 2)
            row[f"{mk}_dol"] = round(b[f"{mk}_dol"], 2)
        rows.append(row)

    rows.sort(key=lambda r: (r["CustomerAccount"] or "", r["Item#"] or ""))

    return {"key": key, "name": name, "columns": columns, "rows": rows}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build(rows: Iterable[dict], *, today: date) -> list[dict]:
    """Turn flat invoice_lines rows into the 4-tab Number 4 payload."""
    sm_map = _load_salesman_map()
    lines = []
    for r in rows:
        nl = _norm_line(r, sm_map)
        if nl is not None:
            lines.append(nl)

    months_12 = _rolling_12_months(today)
    months_ytd = _ytd_months(today)

    buckets_12, keys_12 = _aggregate(lines, months_12)
    buckets_ytd, keys_ytd = _aggregate(lines, months_ytd)

    return [
        _build_by_item_tab    ("by_item_12mo",     "By Item -- 12 Months",     buckets_12,  keys_12),
        _build_by_item_tab    ("by_item_ytd",      "By Item -- YTD",           buckets_ytd, keys_ytd),
        _build_by_customer_tab("by_customer_12mo", "By Customer -- 12 Months", buckets_12,  keys_12),
        _build_by_customer_tab("by_customer_ytd",  "By Customer -- YTD",       buckets_ytd, keys_ytd),
    ]
