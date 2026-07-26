"""Customer Activity stored-procedure result builder.

Source: rpt.usp_customer_activity (one row per customer with Salesman + last
order fields). This builder does no math — it keeps the SP's rows (including
N/A placeholders) and fans them out into workbook-style tabs like live:

  1. All          — every customer, Salesman column first
  2. <Salesman>   — one tab per assigned salesman (no Salesman column)
  3. Unassigned   — blank Salesman (same base columns)

Sort matches live (pandas): Customer Name ascending, case-sensitive. The All
tab is salesman groups in alphabetical order (Unassigned last), each group
already name-sorted — same as live's management workbook concat.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

from report_engine.lib import salesman_key

_BASE_COLS = [
    {"field": "Customer Account", "header": "Customer Account", "type": "text"},
    {"field": "Customer Name", "header": "Customer Name", "type": "text"},
    {"field": "Last Order Date", "header": "Last Order Date", "type": "text"},
    {"field": "PO #", "header": "PO #", "type": "text"},
    {"field": "Sales Order Number", "header": "Sales Order Number", "type": "text"},
]
_ALL_COLS = [{"field": "Salesman", "header": "Salesman", "type": "text"}] + _BASE_COLS


def clean_rows(rows: Iterable[dict]) -> list[dict]:
    """Keep the stored procedure's rows, including its N/A placeholders."""
    return [{column["field"]: row.get(column["field"], "") for column in _ALL_COLS}
            for row in rows]


def filter_rows_by_salesman(rows: list[dict], visible_keys) -> list[dict]:
    if visible_keys is None:
        return rows
    allowed = {salesman_key(key) for key in visible_keys}
    return [row for row in rows if salesman_key(str(row["Salesman"])) in allowed]


def _without_salesman(rows: Sequence[dict]) -> list[dict]:
    return [{c["field"]: row.get(c["field"], "") for c in _BASE_COLS} for row in rows]


def _sort_by_customer_name(rows: list[dict]) -> list[dict]:
    """Same key as live ``DataFrame.sort_values('Customer Name')`` (case-sensitive)."""
    return sorted(rows, key=lambda r: str(r.get("Customer Name") or ""))


def build(rows: Sequence[dict]) -> list[dict]:
    """All tab first, then one tab per salesman (Unassigned last)."""
    by_salesman: dict[str, list[dict]] = {}
    for row in rows:
        salesman = str(row["Salesman"]).strip()
        by_salesman.setdefault(salesman, []).append(row)

    # Blank Salesman ("Unassigned") last; other tabs A–Z like live sorted(keys).
    ordered = sorted(
        by_salesman.items(),
        key=lambda item: (item[0] == "", item[0]),
    )

    all_rows: list[dict] = []
    salesman_tabs: list[dict] = []
    used_keys: set[str] = set()
    for salesman, salesman_rows in ordered:
        sorted_rows = _sort_by_customer_name(list(salesman_rows))
        all_rows.extend(sorted_rows)
        base_key = re.sub(r"[^a-z0-9]+", "_", salesman.lower()).strip("_") or "unassigned"
        tab_key = base_key
        suffix = 2
        while tab_key in used_keys:
            tab_key = f"{base_key}_{suffix}"
            suffix += 1
        used_keys.add(tab_key)
        salesman_tabs.append({
            "key": "unassigned" if not salesman else f"sm_{tab_key}",
            "name": salesman or "Unassigned",
            "columns": _BASE_COLS,
            "rows": _without_salesman(sorted_rows),
        })

    return [{
        "key": "all", "name": "All", "columns": _ALL_COLS,
        "rows": all_rows,
    }, *salesman_tabs]
