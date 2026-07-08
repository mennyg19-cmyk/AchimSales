"""Number 4 report builder (pure).

Source: the two rolling-12 stored procedures (rpt.usp_customer_item_sales_
rolling_12 / rpt.usp_item_customer_sales_rolling_12). Unlike the other v3
reports, these SPs do ALL the math server-side and return the finished pivot:
one row per Customer+Item (or Item+Customer) with a Qty and $ column for each
of the last 12 months, plus Total Qty / Total $ / Avg Price / Salesman /
Book Price. So there are no facts and no aggregation here -- this builder just
names each column's type (so the viewer and Excel format Qty and $ right) and
passes the rows through in the SP's own column order. The handoff says not to
hard-code month names, so column names are read from the rows.

The old 4-tab layout (12-months + YTD, each grouped two ways) is gone: the new
SPs only do rolling-12, and the owner chose to drop YTD for now and ask the
DBA for a YTD variant later (2026-07-08).

# === What's in this file ===
# _column_type() -- name a column's type from its header (Qty=int, $=money)
# columns_for() -- headers in SP order -> viewer column defs
# clean_rows() -- coerce the SP's Qty/$ cells to real numbers
# filter_rows_by_salesman() -- row-level scope filter on the Salesman column
# build() -- wrap the fetched view(s) into one tab each (By Customer / By Item)
"""

from __future__ import annotations

from typing import Iterable, Sequence

from report_engine.lib import num, salesman_key

# Fixed trailing columns the handoff names; everything else ending in "Qty" or
# "$" is a dynamic month column.
_MONEY_HEADERS = {"Total $", "Avg Price", "Book Price"}
_INT_HEADERS = {"Total Qty"}

SALESMAN_COLUMN = "Salesman"


def _column_type(header: str) -> str:
    if header in _MONEY_HEADERS or header.endswith("$"):
        return "money"
    if header in _INT_HEADERS or header.endswith("Qty"):
        return "int"
    return "text"


def columns_for(headers: Sequence[str]) -> list[dict]:
    return [{"field": h, "header": h, "type": _column_type(h)} for h in headers]


def clean_rows(rows: Iterable[dict]) -> list[dict]:
    """Coerce Qty/$ cells to floats so on-screen and Excel totals are numeric.

    Quantities can be fractional (cases vs eaches), so "int" columns keep two
    decimals too -- the type only drives display alignment.
    """
    out = []
    for raw in rows:
        out.append({
            header: value if _column_type(header) == "text" else round(num(value), 2)
            for header, value in raw.items()
        })
    return out


def filter_rows_by_salesman(rows: list[dict], visible_keys) -> list[dict]:
    """Scope backstop on the pivoted rows (they have no fact objects to filter).

    visible_keys=None means unrestricted; an empty set means no access.
    """
    if visible_keys is None:
        return rows
    normalized = {salesman_key(k) for k in visible_keys}
    return [r for r in rows if salesman_key(str(r.get(SALESMAN_COLUMN, ""))) in normalized]


def _tab(key: str, name: str, rows: list[dict]) -> dict:
    headers = list(rows[0].keys()) if rows else []
    return {"key": key, "name": name, "columns": columns_for(headers), "rows": rows}


def build(
    *,
    by_customer_rows: list[dict] | None = None,
    by_item_rows: list[dict] | None = None,
) -> list[dict]:
    """One tab per fetched view; None means that view wasn't requested."""
    tabs = []
    if by_customer_rows is not None:
        tabs.append(_tab("by_customer", "By Customer", by_customer_rows))
    if by_item_rows is not None:
        tabs.append(_tab("by_item", "By Item", by_item_rows))
    return tabs
