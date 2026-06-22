"""The generic engine: one flat table -> the report's tabs."""

# === What's in this file ===
# The stored procedure returns one flat table; each tab is a recipe over it:
# keep some rows (filter), roll them up (group + totals), pick and order the
# columns, and sort. This engine runs those recipes from config, so a new report
# is mostly new config, not new code. Tabs that need bespoke math (the
# commission cards) hand off to a registered transform; tabs that only make
# sense for some data are gated by a condition.
#
# build_tabs() -- run every tab recipe and return the on-screen tab payloads
# _apply_filter() -- keep rows matching a tab's filter (incl. credit/reversal)
# _group() -- group_by + sum / count_distinct aggregations
# _project() -- pick a tab's columns out of each row
# _sort() / _total_row() -- ordering and the footer totals row

from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Sequence

from . import conditions
from .lib import num, text

Transform = Callable[[Sequence[dict], Mapping[str, Any]], dict]


def build_tabs(
    rows: Sequence[dict],
    tabs: Sequence[dict],
    *,
    transforms: Mapping[str, Transform],
    params: Mapping[str, Any] | None = None,
) -> list[dict]:
    params = params or {}
    results: list[dict] = []
    for tab in tabs:
        condition = tab.get("condition")
        if condition and not conditions.evaluate(condition, rows):
            continue

        transform_name = tab.get("transform")
        if transform_name:
            transform = transforms.get(transform_name)
            if transform is None:
                raise KeyError(f"No transform registered named {transform_name!r}")
            built = transform(rows, params)
            # Pass the transform's whole payload through (columns/rows/total plus
            # any layout-specific extras like the commission cards' per-salesman
            # blocks), so new layouts don't need engine changes.
            payload = dict(built)
            payload["key"] = tab["tab_key"]
            payload["label"] = tab["label"]
            payload["layout"] = tab.get("layout") or built.get("layout")
            results.append(payload)
            continue

        columns = tab.get("column_keys") or []
        filtered = _apply_filter(rows, tab.get("filter_expr"))
        if tab.get("group_by"):
            out_rows = _group(filtered, tab["group_by"], tab.get("aggregations") or {})
        else:
            out_rows = _project(filtered, columns)
        out_rows = _sort(out_rows, tab.get("sorters") or [])
        results.append({
            "key": tab["tab_key"],
            "label": tab["label"],
            "layout": tab.get("layout"),
            "columns": columns,
            "rows": out_rows,
            "total": _total_row(out_rows, columns),
        })
    return results


def _apply_filter(rows: Sequence[dict], filter_expr: Any) -> list[dict]:
    if not filter_expr:
        return list(rows)
    spec = json.loads(filter_expr) if isinstance(filter_expr, str) else filter_expr
    op = spec.get("op")
    field = spec.get("field")
    if op == "truthy":
        return [r for r in rows if r.get(field)]
    if op == "falsy":
        return [r for r in rows if not r.get(field)]
    if op == "eq":
        return [r for r in rows if r.get(field) == spec.get("value")]
    if op == "reversal":
        flagged = conditions.reversal_invoice_numbers(rows)
        return [r for r in rows if (r.get("InvoiceNumber") or "") in flagged]
    raise ValueError(f"Unknown tab filter op {op!r}")


def _group(rows: Sequence[dict], group_by: Sequence[str], aggregations: Mapping[str, str]) -> list[dict]:
    buckets: dict[tuple, dict] = {}
    order: list[tuple] = []
    distinct: dict[tuple, dict[str, set]] = {}
    for r in rows:
        key = tuple(text(r.get(g)) for g in group_by)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {g: r.get(g) for g in group_by}
            for out_field, spec in aggregations.items():
                bucket[out_field] = None if spec.startswith("first:") else 0
            buckets[key] = bucket
            order.append(key)
            distinct[key] = {}
        for out_field, spec in aggregations.items():
            op, _, src = spec.partition(":")
            if op == "sum":
                bucket[out_field] = round(num(bucket[out_field]) + num(r.get(src)), 2)
            elif op == "count":
                bucket[out_field] += 1
            elif op == "count_distinct":
                seen = distinct[key].setdefault(out_field, set())
                value = r.get(src)
                if value not in (None, ""):
                    seen.add(value)
                bucket[out_field] = len(seen)
            elif op == "first":
                if bucket[out_field] in (None, ""):
                    bucket[out_field] = r.get(src)
            else:
                raise ValueError(f"Unknown aggregation op {op!r}")
    return [buckets[k] for k in order]


def _project(rows: Sequence[dict], columns: Sequence[dict]) -> list[dict]:
    fields = [c["field"] for c in columns]
    return [{f: r.get(f) for f in fields} for r in rows]


def _sort(rows: list[dict], sorters: Sequence[dict]) -> list[dict]:
    for sorter in reversed(sorters):
        field = sorter.get("field")
        descending = (sorter.get("dir") or "asc").lower() == "desc"
        rows.sort(key=lambda r, f=field: _sort_key(r.get(f)), reverse=descending)
    return rows


def _sort_key(value: Any):
    if isinstance(value, (int, float)):
        return (0, value)
    return (1, text(value).lower())


def _total_row(rows: Sequence[dict], columns: Sequence[dict]) -> dict | None:
    if not columns:
        return None
    total: dict[str, Any] = {}
    for column in columns:
        field = column["field"]
        if column.get("type") == "money":
            total[field] = round(sum(num(r.get(field)) for r in rows), 2)
        elif column.get("type") == "int":
            total[field] = int(sum(num(r.get(field)) for r in rows))
        else:
            total[field] = ""
    total[columns[0]["field"]] = "TOTAL"
    return total
