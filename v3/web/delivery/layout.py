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
                          "columnFilters": {<field>: {"op": str, "v": str, "v2": str}}}}}
Tabs are matched by their ``key``. ``columnFilters`` mirrors the Excel-style
per-column operators in the viewer; older saved presets used a flat
``headerFilters`` list (substring contains) which is still honoured.
"""

from __future__ import annotations

import copy
from typing import Any

_NUMERIC_TYPES = {"money", "int", "percent"}


def expand_clones(payload: dict, layout: dict | None) -> dict:
    """Recreate the viewer's duplicated tabs and reorder to match the screen.

    The viewer can duplicate a tab (client-only ``<key>__copy`` tabs) to hold a
    different filter/sort/group view; those don't exist in the server payload.
    ``serializeLayout`` reports them as ``clones: [{key, baseKey, name}]`` plus
    the on-screen ``order``. We deep-copy each clone's base tab so ``apply_layout``
    can then apply the clone's own per-tab view by key. No-op without clones/order.
    """
    if not isinstance(layout, dict):
        return payload
    clones = layout.get("clones") if isinstance(layout.get("clones"), list) else []
    order = layout.get("order") if isinstance(layout.get("order"), list) else []
    if not clones and not order:
        return payload
    tabs = list(payload.get("tabs") or [])
    by_key = {t.get("key"): t for t in tabs}
    for clone in clones:
        if not isinstance(clone, dict):
            continue
        key, base = clone.get("key"), clone.get("baseKey")
        if not key or key in by_key:
            continue
        src = by_key.get(base)
        if src is None:
            continue
        new = copy.deepcopy(src)
        new["key"] = key
        if clone.get("name"):
            new["name"] = str(clone["name"])
        tabs.append(new)
        by_key[key] = new
    if order:
        pos = {k: i for i, k in enumerate(order)}
        tabs.sort(key=lambda t: pos.get(t.get("key"), len(order)))
    return {**payload, "tabs": tabs}


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
    type_by_field = {
        _field_of(c): (c.get("type") if isinstance(c, dict) else None) for c in columns
    }
    columns = _reorder_and_hide(columns, v)
    col_filters = v.get("columnFilters")
    if col_filters:
        rows = _filter_rows(rows, col_filters, type_by_field)
    else:
        rows = _filter_rows_legacy(rows, v.get("headerFilters") or [])
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


def _filter_rows_legacy(rows: list, header_filters: list) -> list:
    """Old preset format: a flat list of {field, value} substring filters."""
    active = [(hf.get("field"), str(hf.get("value", "")).strip().lower())
              for hf in header_filters if hf.get("field") and str(hf.get("value", "")).strip()]
    if not active:
        return rows
    return [row for row in rows
            if all(needle in str(row.get(field, "")).lower() for field, needle in active)]


def _filter_rows(rows: list, col_filters: dict, type_by_field: dict) -> list:
    """Excel-style per-column operators. Mirrors report.ts ``rowMatches``."""
    active = []
    for field, f in (col_filters or {}).items():
        if not isinstance(f, dict):
            continue
        op = f.get("op")
        v, v2 = f.get("v"), f.get("v2")
        if op in ("empty", "notEmpty"):
            active.append((field, op, v, v2, type_by_field.get(field)))
        elif v not in (None, ""):
            active.append((field, op, v, v2, type_by_field.get(field)))
    if not active:
        return rows
    return [row for row in rows
            if all(_match(row.get(field), op, v, v2, t) for field, op, v, v2, t in active)]


def _to_num(value: Any) -> float | None:
    try:
        return float(str(value).replace("$", "").replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _match(raw: Any, op: str, v: Any, v2: Any, col_type: Any) -> bool:
    if op == "empty":
        return raw is None or str(raw) == ""
    if op == "notEmpty":
        return not (raw is None or str(raw) == "")

    if col_type in _NUMERIC_TYPES:
        x, a = _to_num(raw), _to_num(v)
        if x is None or a is None:
            return False
        b = _to_num(v2)
        return {
            "eq": x == a, "ne": x != a, "gt": x > a, "ge": x >= a,
            "lt": x < a, "le": x <= a,
            "between": x >= a if b is None else (a <= x <= b),
        }.get(op, True)

    if col_type == "date":
        d = str(raw or "")[:10]
        a = str(v or "")[:10]
        b = str(v2 or "")[:10]
        if op == "on":
            return d == a
        if op == "before":
            return bool(d) and d < a
        if op == "after":
            return bool(d) and d > a
        if op == "between":
            return (not a or d >= a) and (not b or d <= b)
        return True

    s = str(raw if raw is not None else "").lower()
    q = str(v).lower()
    if op == "equals":
        return s == q
    if op == "starts":
        return s.startswith(q)
    if op == "ends":
        return s.endswith(q)
    if op == "in":
        return s in [p.strip() for p in q.split(",") if p.strip()]
    return q in s  # "contains" (and default)


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
