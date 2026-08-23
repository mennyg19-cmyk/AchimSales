"""Item Averages report builder (pure).

Source: Number 4 By Item SP (`item_customer_sales_rolling_12`). That SP returns
one row per Item+Customer with a finished rolling-12 Total Qty. This builder
rolls those rows up to one row per item and computes:
  Avg/Month = Total Qty / 12
  Avg/Week  = Total Qty / 52
Company-wide quantities only; no dollar columns.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from report_engine.lib import num, text

REPORT_KEY = "item_averages"
SP_NAME = "item_customer_sales_rolling_12"

_ITEM_COL = "Item #"
_NAME_COL = "Item Name"
_QTY_COL = "Total Qty"

COLUMNS = [
    {"field": "Item #", "header": "Item #", "type": "text"},
    {"field": "Item Name", "header": "Item Name", "type": "text"},
    {"field": "12-Month Qty", "header": "12-Month Qty", "type": "int"},
    {"field": "Avg/Month", "header": "Avg/Month", "type": "int"},
    {"field": "Avg/Week", "header": "Avg/Week", "type": "int"},
]


def rollup_by_item(rows: Iterable[dict]) -> list[dict]:
    """Sum Total Qty per Item #, then attach fixed-window averages."""
    totals: dict[str, dict] = {}
    for raw in rows:
        item = text(raw.get(_ITEM_COL))
        if not item:
            continue
        name = text(raw.get(_NAME_COL))
        qty = num(raw.get(_QTY_COL))
        slot = totals.get(item)
        if slot is None:
            totals[item] = {"Item #": item, "Item Name": name, "qty": qty}
        else:
            slot["qty"] += qty
            if not slot["Item Name"] and name:
                slot["Item Name"] = name

    out: list[dict] = []
    for item in sorted(totals):
        slot = totals[item]
        total_qty = round(slot["qty"], 2)
        out.append({
            "Item #": slot["Item #"],
            "Item Name": slot["Item Name"],
            "12-Month Qty": total_qty,
            "Avg/Month": round(total_qty / 12, 2),
            "Avg/Week": round(total_qty / 52, 2),
        })
    return out


def build(rows: Sequence[dict]) -> list[dict]:
    """One tab: Item Averages."""
    rolled = rollup_by_item(rows)
    return [{
        "key": "item_averages",
        "name": "Item Averages",
        "columns": COLUMNS,
        "rows": rolled,
    }]
