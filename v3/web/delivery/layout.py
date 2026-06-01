"""Apply a saved grid layout to a report payload before server-side export.

The interactive viewer exports "what you see" in the browser. Email/scheduled
deliveries build the workbook on the server, so we replay the saved per-tab
layout (hidden columns, column order, sort, header filters) onto the payload so
the delivered file matches the saved view. Group/freeze are viewer-only and
don't affect a flat sheet, so they're ignored here.

Layout shape (produced by report.ts `serializeLayout`):
    {"active": <tabKey|null>,
     "views": {<tabKey>: {"hidden": [field...], "order": [field...],
                          "sorters": [{"column": field, "dir": "asc|desc"}],
                          "headerFilters": [{"field": f, "value": v}]}}}
Tabs are matched by their ``key``.
"""

from __future__ import annotations

from typing import Any


def apply_layout(payload: dict, layout: dict | None) -> dict:
    views = (layout or {}).get("views") or {}
    if not views:
        return payload
    tabs = []
    for tab in payload.get("tabs") or []:
        v = views.get(tab.get("key"))
        tabs.append(_apply_to_tab(tab, v) if v else tab)
    return {**payload, "tabs": tabs}


def _apply_to_tab(tab: dict, v: dict) -> dict:
    columns = list(tab.get("columns") or [])
    rows = list(tab.get("rows") or [])
    columns = _reorder_and_hide(columns, v)
    rows = _filter_rows(rows, v.get("headerFilters") or [])
    rows = _sort_rows(rows, v.get("sorters") or [])
    return {**tab, "columns": columns, "rows": rows}


def _field_of(col: Any) -> str:
    return str(col.get("field") or col.get("header") or "") if isinstance(col, dict) else str(col)


def _reorder_and_hide(columns: list, v: dict) -> list:
    hidden = set(v.get("hidden") or [])
    order = [f for f in (v.get("order") or []) if f]
    visible = [c for c in columns if _field_of(c) not in hidden]
    if not order:
        return visible
    by_field = {_field_of(c): c for c in visible}
    ordered = [by_field[f] for f in order if f in by_field]
    # Append any visible columns the saved order didn't mention (new since save).
    seen = set(order)
    ordered.extend(c for c in visible if _field_of(c) not in seen)
    return ordered


def _filter_rows(rows: list, header_filters: list) -> list:
    active = [(hf.get("field"), str(hf.get("value", "")).strip().lower())
              for hf in header_filters if hf.get("field") and str(hf.get("value", "")).strip()]
    if not active:
        return rows
    out = []
    for row in rows:
        if all(needle in str(row.get(field, "")).lower() for field, needle in active):
            out.append(row)
    return out


def _sort_rows(rows: list, sorters: list) -> list:
    # Apply sorters in reverse so the first sorter is the primary key (stable sort).
    out = list(rows)
    for s in reversed(sorters):
        field = s.get("column") or s.get("field")
        if not field:
            continue
        reverse = str(s.get("dir", "asc")).lower() == "desc"
        out.sort(key=lambda r, f=field: _sort_key(r.get(f)), reverse=reverse)
    return out


def _sort_key(value: Any) -> tuple:
    """Sort numbers before strings, both ascending, with None last."""
    if value is None or value == "":
        return (2, 0.0, "")
    if isinstance(value, (int, float)):
        return (0, float(value), "")
    try:
        return (0, float(str(value).replace(",", "").replace("$", "")), "")
    except (TypeError, ValueError):
        return (1, 0.0, str(value).lower())
