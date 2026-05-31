"""Number 4 report builder (pure).

Source: invoice_lines SP -> InvoiceItemFact. Format/columns follow LIVE
(reports/number_4); on-screen multi-tab architecture follows the test app.

Four tabs (rolling-12-month and YTD windows, grouped two ways):
    1. By Item -- 12 Months      (row per Item+Customer; monthly Qty only)
    2. By Item -- YTD
    3. By Customer -- 12 Months  (row per Customer+Item; monthly Qty + $)
    4. By Customer -- YTD

Book Price (LIVE) = the released product's SalesPrice, joined by ItemNumber
(upper-cased). It is the LAST column on every tab (after Salesman), matching
reports/number_4/writer_item.py / writer_customer.py. The builder takes an
optional `book_prices` map; when absent the column renders blank.
"""

from __future__ import annotations

from calendar import month_abbr
from datetime import date
from typing import Iterable, Mapping

from report_engine.facts import InvoiceItemFact, SalesmanFact
from report_engine.lib import salesman_key

_BOOK_PRICE_COL = {"field": "BookPrice", "header": "Book Price", "type": "money"}


def _month_label(y: int, m: int) -> str:
    return f"{month_abbr[m]}-{str(y)[-2:]}"


def _ym(y: int, m: int) -> str:
    return f"{y:04d}-{m:02d}"


def _rolling_12_months(today: date) -> list[tuple[int, int]]:
    out, y, m = [], today.year, today.month
    for _ in range(12):
        out.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    out.reverse()
    return out


def _ytd_months(today: date) -> list[tuple[int, int]]:
    return [(today.year, m) for m in range(1, today.month + 1)]


def _resolve_salesman(sales_group: str, salesmen: Mapping[str, SalesmanFact]) -> str:
    sm = salesmen.get(salesman_key(sales_group)) if sales_group else None
    if sm:
        return sm.display_name or sm.full_name or sales_group
    return sales_group or "Unassigned"


def _line(fact: InvoiceItemFact, salesmen: Mapping[str, SalesmanFact]) -> dict | None:
    d = fact.invoice_date
    if not (isinstance(d, str) and len(d) >= 7 and d[4] == "-") or not fact.item_number:
        return None
    # LIVE excludes free-text invoice lines (no SalesOrderNumber).
    if not fact.sales_order_number.strip():
        return None
    try:
        year, month = int(d[:4]), int(d[5:7])
    except ValueError:
        return None
    if not (1 <= month <= 12):
        return None
    return {
        "year": year, "month": month, "_ym": _ym(year, month),
        "Item#": fact.item_number, "ItemName": fact.item_name,
        "CustomerAccount": fact.customer_account, "CustomerName": fact.customer_name,
        "Salesman": _resolve_salesman(fact.sales_group, salesmen),
        "Qty": fact.qty, "Total_$": fact.amount,
    }


def _aggregate(lines: list[dict], months: list[tuple[int, int]]) -> tuple[dict, list[str]]:
    month_keys = [_ym(y, m) for y, m in months]
    month_set = set(month_keys)
    buckets: dict[tuple, dict] = {}
    for ln in lines:
        if ln["_ym"] not in month_set:
            continue
        # LIVE groups by item, item name, customer account, customer name, salesman
        # (reports/number_4/aggregator.py).
        key = (ln["Item#"], ln["ItemName"], ln["CustomerAccount"],
               ln["CustomerName"], ln["Salesman"])
        b = buckets.get(key)
        if b is None:
            b = buckets[key] = {
                "Item#": ln["Item#"], "ItemName": ln["ItemName"],
                "CustomerAccount": ln["CustomerAccount"], "CustomerName": ln["CustomerName"],
                "Salesman": ln["Salesman"],
                **{f"{mk}_qty": 0.0 for mk in month_keys},
                **{f"{mk}_dol": 0.0 for mk in month_keys},
                "Total_Qty": 0.0, "Total_$": 0.0,
            }
        b[f"{ln['_ym']}_qty"] += ln["Qty"]
        b[f"{ln['_ym']}_dol"] += ln["Total_$"]
        b["Total_Qty"] += ln["Qty"]
        b["Total_$"] += ln["Total_$"]
    return buckets, month_keys


def _avg_price(total_dollars: float, total_qty: float) -> float | None:
    return round(total_dollars / total_qty, 4) if total_qty else None


def _book_price(item: str, book_prices: Mapping[str, float] | None) -> float | None:
    if not book_prices:
        return None
    return book_prices.get(item.strip().upper())


def _build_by_item_tab(key, name, buckets, month_keys, book_prices) -> dict:
    columns = [
        {"field": "Item#",           "header": "Item #",        "type": "text"},
        {"field": "ItemName",        "header": "Item Name",     "type": "text"},
        {"field": "CustomerAccount", "header": "Customer #",    "type": "text"},
        {"field": "CustomerName",    "header": "Customer Name", "type": "text"},
    ]
    for mk in month_keys:
        columns.append({"field": f"{mk}_qty",
                        "header": f"{_month_label(int(mk[:4]), int(mk[5:7]))} Qty", "type": "int"})
    columns += [
        {"field": "Total_Qty", "header": "Total Qty", "type": "int"},
        {"field": "Total_$",   "header": "Total $",   "type": "money"},
        {"field": "Avg_Price", "header": "Avg Price", "type": "money"},
        {"field": "Salesman",  "header": "Salesman",  "type": "text"},
        _BOOK_PRICE_COL,
    ]
    rows = []
    for b in buckets.values():
        row = {
            "Item#": b["Item#"], "ItemName": b["ItemName"],
            "CustomerAccount": b["CustomerAccount"], "CustomerName": b["CustomerName"],
            "Salesman": b["Salesman"],
            "Total_Qty": round(b["Total_Qty"], 2), "Total_$": round(b["Total_$"], 2),
            "Avg_Price": _avg_price(b["Total_$"], b["Total_Qty"]),
            "BookPrice": _book_price(b["Item#"], book_prices),
        }
        for mk in month_keys:
            row[f"{mk}_qty"] = round(b[f"{mk}_qty"], 2)
        rows.append(row)
    rows.sort(key=lambda r: (r["Item#"] or "", r["CustomerAccount"] or ""))
    return {"key": key, "name": name, "columns": columns, "rows": rows}


def _build_by_customer_tab(key, name, buckets, month_keys, book_prices) -> dict:
    columns = [
        {"field": "CustomerAccount", "header": "Customer #",    "type": "text"},
        {"field": "CustomerName",    "header": "Customer Name", "type": "text"},
        {"field": "Item#",           "header": "Item #",        "type": "text"},
        {"field": "ItemName",        "header": "Item Name",     "type": "text"},
    ]
    for mk in month_keys:
        lbl = _month_label(int(mk[:4]), int(mk[5:7]))
        columns.append({"field": f"{mk}_qty", "header": f"{lbl} Qty", "type": "int"})
        columns.append({"field": f"{mk}_dol", "header": f"{lbl} $",   "type": "money"})
    columns += [
        {"field": "Total_Qty", "header": "Total Qty", "type": "int"},
        {"field": "Total_$",   "header": "Total $",   "type": "money"},
        {"field": "Avg_Price", "header": "Avg Price", "type": "money"},
        {"field": "Salesman",  "header": "Salesman",  "type": "text"},
        _BOOK_PRICE_COL,
    ]
    rows = []
    for b in buckets.values():
        row = {
            "CustomerAccount": b["CustomerAccount"], "CustomerName": b["CustomerName"],
            "Item#": b["Item#"], "ItemName": b["ItemName"], "Salesman": b["Salesman"],
            "Total_Qty": round(b["Total_Qty"], 2), "Total_$": round(b["Total_$"], 2),
            "Avg_Price": _avg_price(b["Total_$"], b["Total_Qty"]),
            "BookPrice": _book_price(b["Item#"], book_prices),
        }
        for mk in month_keys:
            row[f"{mk}_qty"] = round(b[f"{mk}_qty"], 2)
            row[f"{mk}_dol"] = round(b[f"{mk}_dol"], 2)
        rows.append(row)
    rows.sort(key=lambda r: (r["CustomerAccount"] or "", r["Item#"] or ""))
    return {"key": key, "name": name, "columns": columns, "rows": rows}


def build(
    facts: Iterable[InvoiceItemFact],
    *,
    today: date,
    salesmen: Mapping[str, SalesmanFact] | None = None,
    book_prices: Mapping[str, float] | None = None,
) -> list[dict]:
    salesmen = salesmen or {}
    lines = [ln for ln in (_line(f, salesmen) for f in facts) if ln is not None]

    buckets_12, keys_12 = _aggregate(lines, _rolling_12_months(today))
    buckets_ytd, keys_ytd = _aggregate(lines, _ytd_months(today))

    return [
        _build_by_item_tab("by_item_12mo", "By Item -- 12 Months", buckets_12, keys_12, book_prices),
        _build_by_item_tab("by_item_ytd", "By Item -- YTD", buckets_ytd, keys_ytd, book_prices),
        _build_by_customer_tab("by_customer_12mo", "By Customer -- 12 Months", buckets_12, keys_12, book_prices),
        _build_by_customer_tab("by_customer_ytd", "By Customer -- YTD", buckets_ytd, keys_ytd, book_prices),
    ]
