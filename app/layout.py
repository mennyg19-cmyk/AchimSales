"""Replay a saved grid layout onto report tabs before Excel / email."""

from __future__ import annotations

from datetime import datetime


def apply_layout(payload: dict, layout: dict | None) -> dict:
    if not isinstance(layout, dict):
        return payload
    report = payload.get("data") or {}
    tabs = report.get("tabs")
    if not isinstance(tabs, dict) or not tabs:
        return payload
    views = layout.get("views") if isinstance(layout.get("views"), dict) else {}
    order = layout.get("order") if isinstance(layout.get("order"), list) else []
    clones = layout.get("clones") if isinstance(layout.get("clones"), list) else []
    for clone in clones:
        if not isinstance(clone, dict):
            continue
        key, base = clone.get("key"), clone.get("baseKey")
        if not key or key in tabs or base not in tabs:
            continue
        copy = dict(tabs[base])
        copy["name"] = clone.get("name") or copy.get("name")
        copy["rows"] = list(copy.get("rows") or [])
        tabs[key] = copy
    if order:
        tabs = {key: tabs[key] for key in order if key in tabs}
    for key, tab in list(tabs.items()):
        spec = views.get(key) or views.get("_default")
        if isinstance(spec, dict) and spec:
            tabs[key] = _apply_to_tab(tab, spec)
    payload = dict(payload)
    data = dict(report)
    data["tabs"] = tabs
    payload["data"] = data
    return payload


def _apply_to_tab(tab: dict, spec: dict) -> dict:
    rows = list(tab.get("rows") or [])
    if not rows:
        return tab
    hidden = set(spec.get("hidden") or [])
    order = [f for f in (spec.get("order") or []) if f]
    fields = [f for f in (order or list(rows[0].keys())) if f not in hidden]
    leftover = [f for f in rows[0].keys() if f not in fields and f not in hidden]
    fields.extend(leftover)
    rows = _filter_rows(rows, spec.get("columnFilters") or {})
    rows = _sort_rows(rows, spec.get("sorters") or [])
    slim = [{field: row.get(field) for field in fields} for row in rows]
    out = dict(tab)
    out["rows"] = slim
    return out


def _filter_rows(rows: list[dict], filters: dict) -> list[dict]:
    if not isinstance(filters, dict) or not filters:
        return rows
    kept = []
    for row in rows:
        if all(_match(row.get(field), spec) for field, spec in filters.items()):
            kept.append(row)
    return kept


def _match(value, spec: dict) -> bool:
    if not isinstance(spec, dict):
        return True
    op = (spec.get("op") or "contains").lower()
    left = "" if value is None else str(value)
    v = spec.get("v") or ""
    v2 = spec.get("v2") or ""
    if op == "contains":
        return v.lower() in left.lower() if v else True
    if op == "equals":
        return left.lower() == v.lower()
    if op == "starts":
        return left.lower().startswith(v.lower())
    if op in {"gt", "lt", "between"}:
        try:
            num = float(str(value).replace(",", ""))
            a = float(v) if v else None
            b = float(v2) if v2 else None
        except (TypeError, ValueError):
            return True
        if op == "gt" and a is not None:
            return num > a
        if op == "lt" and a is not None:
            return num < a
        if op == "between" and a is not None and b is not None:
            return a <= num <= b
    empty = left.strip() == ""
    if op == "empty":
        return empty
    if op == "not_empty":
        return not empty
    return True


def _sort_rows(rows: list[dict], sorters: list) -> list[dict]:
    if not isinstance(sorters, list) or not sorters:
        return rows
    out = list(rows)
    for sorter in reversed(sorters):
        if not isinstance(sorter, dict) or not sorter.get("column"):
            continue
        field = sorter["column"]
        reverse = sorter.get("dir") == "desc"

        def key(row, col=field):
            val = row.get(col)
            if val is None:
                return (1, "")
            if isinstance(val, (int, float)):
                return (0, val)
            try:
                return (0, datetime.fromisoformat(str(val)))
            except ValueError:
                try:
                    return (0, float(str(val).replace(",", "")))
                except ValueError:
                    return (0, str(val).lower())

        out.sort(key=key, reverse=reverse)
    return out
