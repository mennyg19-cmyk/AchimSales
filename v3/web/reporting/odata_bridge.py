"""OData path for Beta: run Live's report runners, shape sheets into v3 tabs.

Used when the per-report source switch is 'odata'. Live runners write Excel;
we read the workbook sheets into the same {key,name,columns,rows} tab shape
the v3 viewer expects.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from report_engine.lib import salesman_key

log = logging.getLogger(__name__)


class UnscopedODataError(RuntimeError):
    """Scoped user would have received a tab with no salesman filter."""


def apply_visible_scope(tabs: list[dict], visible_keys: set[str] | None) -> list[dict]:
    """Filter OData tabs for a scoped user, or refuse the whole report."""
    if visible_keys is None:
        return tabs
    unscoped = [
        str(tab.get("name") or tab.get("key") or "sheet")
        for tab in tabs
        if (tab.get("rows") or []) and _scope_column(tab) is None
    ]
    if unscoped:
        raise UnscopedODataError(
            "OData report refused for a scoped user; tabs without a "
            "salesman column: " + ", ".join(unscoped)
        )
    return [_scope_tab(tab, visible_keys) for tab in tabs]


def build_odata_payload(
    report_key: str,
    params: dict[str, Any],
    visible_keys: set[str] | None,
) -> dict:
    """Run the live OData report and return a v3-compatible payload."""
    from web.reporting.odata_run import run_report

    run_params = dict(params or {})
    result = run_report(report_key, run_params)
    if not result.get("success"):
        raise RuntimeError(result.get("error") or f"Live OData run failed for {report_key}")

    filepath = result.get("filepath") or ""
    extra_files = result.get("extra_files") or []
    paths = [p for p in [filepath, *_extra_file_paths(extra_files)] if p and Path(p).is_file()]
    if not paths:
        raise RuntimeError(f"Live OData run for {report_key} produced no Excel file")

    tabs = []
    for path in paths:
        tabs.extend(_workbook_to_tabs(path, report_key=report_key, source_path=path))

    tabs = apply_visible_scope(tabs, visible_keys)

    if report_key == "ordered" and not params.get("salesman"):
        tabs = [_attach_ordered_default_group(tab) for tab in tabs]
    elif report_key == "number_4":
        tabs = [_attach_number4_defaults(tab) for tab in tabs]

    row_count = sum(len(t.get("rows") or []) for t in tabs)
    return {
        "report_key": report_key,
        "tabs": tabs,
        "row_count": row_count,
        "data_source": "odata",
    }


# Match SQL Ordered builder: Summary / By Customer / By Order group by Salesman.
_ORDERED_DEFAULT_GROUP_KEYS = {
    "summary", "by_customer", "by_order",
    "summary_by_customer",  # live filtered variant sheet names sometimes differ
}
_ORDERED_DEFAULT_GROUP_NAMES = {
    "summary", "by customer", "by order",
}


def _extra_file_paths(extra_files) -> list[str]:
    """History stores extra_files as {filepath, filename} dicts, not bare paths."""
    paths: list[str] = []
    for item in extra_files or []:
        if isinstance(item, str) and item:
            paths.append(item)
        elif isinstance(item, dict):
            p = item.get("filepath") or item.get("path") or ""
            if p:
                paths.append(p)
    return paths


def _attach_ordered_default_group(tab: dict) -> dict:
    key = str(tab.get("key") or "").strip().lower()
    name = str(tab.get("name") or "").strip().lower()
    if key in _ORDERED_DEFAULT_GROUP_KEYS or name in _ORDERED_DEFAULT_GROUP_NAMES:
        out = dict(tab)
        out["default_group"] = ["Salesman"]
        return out
    return tab


def _number4_version_label(path: str) -> str:
    name = Path(path).name.lower()
    if "item" in name:
        return "By Item"
    if "customer" in name:
        return "By Customer"
    return ""


def _is_summary_row(row: dict) -> bool:
    for value in row.values():
        text = str(value or "").strip()
        if text.startswith("TOTALS") or text.startswith("GRAND TOTALS"):
            return True
    return False


def _attach_number4_defaults(tab: dict) -> dict:
    """Group by item; drop Excel TOTALS rows so the grid grouping is clean."""
    out = dict(tab)
    out["default_group"] = ["Item #"]
    rows = [r for r in (tab.get("rows") or []) if not _is_summary_row(r)]
    out["rows"] = rows
    return out


def _workbook_to_tabs(path: str, *, report_key: str = "", source_path: str = "") -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    tabs: list[dict] = []
    try:
        for sheet in wb.worksheets:
            rows_iter = sheet.iter_rows(values_only=True)
            try:
                header = next(rows_iter)
            except StopIteration:
                continue
            columns = [str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(header)]
            # Skip fully blank header rows
            if not any(columns):
                continue
            data_rows: list[dict] = []
            for raw in rows_iter:
                if raw is None or all(v is None or str(v).strip() == "" for v in raw):
                    continue
                row = {}
                for i, col in enumerate(columns):
                    if not col:
                        continue
                    val = raw[i] if i < len(raw) else None
                    if hasattr(val, "isoformat"):
                        val = val.isoformat()
                    row[col] = val
                data_rows.append(row)
            title = sheet.title
            prefix = _number4_version_label(source_path or path) if report_key == "number_4" else ""
            if prefix:
                title = f"{prefix} ({sheet.title})"
            key = _slug(title)
            tabs.append({
                "key": key,
                "name": title,
                "columns": [c for c in columns if c],
                "rows": data_rows,
            })
    finally:
        wb.close()
    return tabs


def _slug(title: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "_" for ch in (title or "sheet"))
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_") or "sheet"


_SCOPE_COLS = ("Salesman", "SalesGroup", "SalesmanNumber", "Sales Group", "sales_group")


def _scope_column(tab: dict) -> str | None:
    columns = tab.get("columns") or []
    col = next((c for c in _SCOPE_COLS if c in columns), None)
    if col is not None:
        return col
    rows = tab.get("rows") or []
    if not rows:
        return None
    sample = rows[0]
    return next((c for c in _SCOPE_COLS if c in sample), None)


def _scope_tab(tab: dict, visible_keys: set[str]) -> dict:
    """Keep only rows whose salesman key is in scope. Caller must fail closed first."""
    rows = tab.get("rows") or []
    if not rows:
        return tab
    col = _scope_column(tab)
    if col is None:
        raise UnscopedODataError(
            f"OData tab {tab.get('name')!r} has no salesman column; "
            "refusing to return unscoped rows"
        )
    allowed = {salesman_key(k) for k in visible_keys}
    filtered = [r for r in rows if salesman_key(str(r.get(col, ""))) in allowed]
    out = dict(tab)
    out["rows"] = filtered
    return out
