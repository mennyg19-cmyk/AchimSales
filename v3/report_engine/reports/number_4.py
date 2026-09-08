"""Number 4 report builder (pure).

Source: the two rolling-12 stored procedures (rpt.usp_customer_item_sales_
rolling_12 / rpt.usp_item_customer_sales_rolling_12). The SPs return the
finished pivot: one row per Customer+Item (or Item+Customer) with a Qty and $
column for each of the last 12 months, plus Total Qty / Total $ / Avg Price /
Book Price / Salesman. This builder types those columns, puts every month
column before that trailing block (a new month the SP appended after Salesman
still belongs with the other months), and fills missing Total $ / Avg Price /
Book Price on both By Customer and By Item.

There is no YTD stored procedure. YTD months are always a subset of the
rolling-12 window, so the YTD tabs drop prior-year month columns and
recalculate Total Qty / Total $ / Avg Price. Rows with no current-year
activity are omitted.
"""

from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Iterable, Sequence

from report_engine.dates import today_eastern
from report_engine.lib import num, salesman_key

# Fixed trailing columns; everything else ending in "Qty" or "$" is a month.
AVG_PRICE = "Avg Price"
BOOK_PRICE = "Book Price"
SALESMAN_COLUMN = "Salesman"
ITEM_GROUP = "Item #"
_MONEY_HEADERS = {"Total $", AVG_PRICE, BOOK_PRICE}
_INT_HEADERS = {"Total Qty"}
_PRICE_COLUMNS = (AVG_PRICE, BOOK_PRICE)
_TRAILING = ("Total Qty", "Total $", AVG_PRICE, BOOK_PRICE, SALESMAN_COLUMN)

# SP / Excel aliases → the headers the grid and writer already use.
_HEADER_ALIASES = {
    "avgprice": AVG_PRICE,
    "averageprice": AVG_PRICE,
    "bookprice": BOOK_PRICE,
}

# One fetched view: the SP's column headers (in its order) + the cleaned rows.
# Headers come from the API's column list, not the rows, so a run with zero
# rows (or one fully scope-filtered) still shows its column headers.
View = tuple[Sequence[str], list[dict]]

_MONTH_BODY = re.compile(r"^([A-Za-z]{3,9})[-/ ]+(\d{2,4})$")


def _fold_header(header: str) -> str:
    return "".join(ch for ch in str(header or "").lower() if ch.isalnum())


def canonical_header(header: str) -> str:
    key = str(header or "")
    return _HEADER_ALIASES.get(_fold_header(key), key)


def _dedupe_headers(headers: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for header in headers:
        if header in seen:
            continue
        seen.add(header)
        out.append(header)
    return out


def _column_type(header: str) -> str:
    if header in _MONEY_HEADERS or header.endswith("$"):
        return "money"
    if header in _INT_HEADERS or header.endswith("Qty"):
        return "int"
    return "text"


def is_money_header(header: str) -> bool:
    return _column_type(header) == "money"


def columns_for(headers: Sequence[str]) -> list[dict]:
    return [{"field": h, "header": h, "type": _column_type(h)} for h in headers]


def parse_month_header(header: str) -> tuple[int, int] | None:
    """Map 'Jul-25 Qty' / 'Jul-25 $' / '2025-07 $' -> (year, month).

    Total Qty / Total $ are not months.
    """
    h = str(header or "").strip()
    if not h or h in _INT_HEADERS or h in _MONEY_HEADERS:
        return None
    body = None
    if h.endswith(" Qty"):
        body = h[:-4].strip()
    elif h.endswith(" $"):
        body = h[:-2].strip()
    elif h.endswith("$"):
        body = h[:-1].strip()
    else:
        return None
    if len(body) >= 7 and body[4] == "-" and body[:4].isdigit():
        try:
            return int(body[:4]), int(body[5:7])
        except ValueError:
            return None
    mon_map = {calendar.month_abbr[i].lower(): i for i in range(1, 13)}
    m = _MONTH_BODY.match(body)
    if not m:
        return None
    mon = mon_map.get(m.group(1).lower()[:3])
    if not mon:
        return None
    yy = int(m.group(2))
    if yy < 100:
        yy += 2000
    return yy, mon


def _looks_like_number4(fields: Sequence[str]) -> bool:
    return any(f in fields for f in _PRICE_COLUMNS) or any(
        parse_month_header(f) is not None for f in fields
    )


def _month_sort_key(header: str) -> tuple[int, int, int]:
    ym = parse_month_header(header)
    if ym is None:
        return (9999, 99, 9)
    return (ym[0], ym[1], 1 if is_money_header(header) else 0)


def order_number4_columns(fields: Sequence[str]) -> list[str]:
    """Months first (calendar order), then Total Qty / Total $ / Avg / Book / Salesman.

    Only runs on Number 4-shaped column lists so Ordered's Salesman column
    is not dragged to the end.
    """
    fields = list(fields)
    if not _looks_like_number4(fields):
        return fields
    trailing_set = set(_TRAILING)
    lead: list[str] = []
    months: list[str] = []
    for field in fields:
        if field in trailing_set:
            continue
        if parse_month_header(field) is not None:
            months.append(field)
        else:
            lead.append(field)
    months.sort(key=_month_sort_key)
    trailing = [field for field in _TRAILING if field in fields]
    return lead + months + trailing


def place_price_columns(fields: Sequence[str]) -> list[str]:
    """Apply the Number 4 trailing-column order."""
    return order_number4_columns(fields)


def _fill_avg_price(row: dict) -> None:
    if row.get(AVG_PRICE) not in (None, ""):
        return
    total_qty = num(row.get("Total Qty"))
    total_dol = num(row.get("Total $"))
    row[AVG_PRICE] = round(total_dol / total_qty, 2) if total_qty else 0.0


def prepare_number4_view(view: View) -> View:
    """Rename aliases, add missing money trailers, months before the trailing block."""
    headers, rows = view
    headers = _dedupe_headers(canonical_header(h) for h in headers)
    for col in ("Total $", AVG_PRICE, BOOK_PRICE):
        if col not in headers:
            headers.append(col)
    headers = order_number4_columns(headers)
    month_dol = [h for h in headers if parse_month_header(h) and is_money_header(h)]
    month_qty = [h for h in headers if parse_month_header(h) and not is_money_header(h)]
    new_rows = []
    for raw in rows:
        row = {canonical_header(k): v for k, v in raw.items()}
        if row.get("Total $") in (None, "") and month_dol:
            row["Total $"] = round(sum(num(row.get(h)) for h in month_dol), 2)
        if row.get("Total Qty") in (None, "") and month_qty:
            row["Total Qty"] = round(sum(num(row.get(h)) for h in month_qty), 2)
        _fill_avg_price(row)
        if BOOK_PRICE not in row:
            row[BOOK_PRICE] = None
        new_rows.append(row)
    return headers, new_rows


ensure_prices_before_salesman = prepare_number4_view


def clean_rows(rows: Iterable[dict]) -> list[dict]:
    """Coerce Qty/$ cells to floats so on-screen and Excel totals are numeric.

    Quantities can be fractional (cases vs eaches), so "int" columns keep two
    decimals too -- the type only drives display alignment.
    """
    out = []
    for raw in rows:
        cleaned = {}
        for header, value in raw.items():
            field = canonical_header(header)
            cleaned[field] = value if _column_type(field) == "text" else round(num(value), 2)
        out.append(cleaned)
    return out


def filter_rows_by_salesman(rows: list[dict], visible_keys) -> list[dict]:
    """Scope backstop on the pivoted rows (they have no fact objects to filter).

    visible_keys=None means unrestricted; an empty set means no access.
    """
    if visible_keys is None:
        return rows
    normalized = {salesman_key(k) for k in visible_keys}
    return [r for r in rows if salesman_key(str(r.get(SALESMAN_COLUMN, ""))) in normalized]


def ytd_view(view: View, as_of: date) -> View:
    """Keep Jan..as_of month columns and recalc totals; drop idle rows."""
    headers, rows = view
    kept_months: list[str] = []
    new_headers: list[str] = []
    for header in headers:
        ym = parse_month_header(header)
        if ym is None:
            new_headers.append(header)
            continue
        if ym[0] == as_of.year and ym[1] <= as_of.month:
            kept_months.append(header)
            new_headers.append(header)
    new_headers = order_number4_columns(new_headers)

    qty_months = [h for h in kept_months if _column_type(h) == "int"]
    dol_months = [h for h in kept_months if _column_type(h) == "money"]

    new_rows = []
    for raw in rows:
        row = {h: raw.get(h) for h in new_headers}
        total_qty = round(sum(num(raw.get(h)) for h in qty_months), 2)
        total_dol = round(sum(num(raw.get(h)) for h in dol_months), 2)
        if total_qty == 0 and total_dol == 0:
            continue
        if "Total Qty" in row:
            row["Total Qty"] = total_qty
        if "Total $" in row:
            row["Total $"] = total_dol
        if AVG_PRICE in row:
            row[AVG_PRICE] = round(total_dol / total_qty, 2) if total_qty else 0.0
        new_rows.append(row)
    return new_headers, new_rows


def _tab(key: str, name: str, view: View) -> dict:
    headers, rows = view
    return {
        "key": key,
        "name": name,
        "columns": columns_for(headers),
        "rows": rows,
        "default_group": [ITEM_GROUP],
    }


def build(
    *,
    by_customer: View | None = None,
    by_item: View | None = None,
    as_of: date | None = None,
) -> list[dict]:
    """Two tabs per fetched view: rolling 12 months, then YTD."""
    as_of = as_of or today_eastern()
    tabs = []
    if by_customer is not None:
        by_customer = prepare_number4_view(by_customer)
        tabs.append(_tab("by_customer", "By Customer (12 Months)", by_customer))
        tabs.append(_tab("by_customer_ytd", "By Customer (YTD)", ytd_view(by_customer, as_of)))
    if by_item is not None:
        by_item = prepare_number4_view(by_item)
        tabs.append(_tab("by_item", "By Item (12 Months)", by_item))
        tabs.append(_tab("by_item_ytd", "By Item (YTD)", ytd_view(by_item, as_of)))
    return tabs
