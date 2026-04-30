"""Multi-sheet .xlsx export for a report viewer.

Takes the payload produced by ``report_runner.run_report`` and a
per-tab layout override (column order + hidden list) supplied by the
client, and writes one sheet per tab with formatted values.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# Excel max chars per cell; anything longer will raise IllegalCharacterError.
_MAX_CELL_CHARS = 32767
# Excel chokes on certain ASCII control characters in cell values.
_BAD_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_ALIGN = Alignment(horizontal="left", vertical="center")


_NUMBER_FORMATS = {
    "money":   '"$"#,##0.00;[Red]-"$"#,##0.00',
    "int":     "#,##0",
    "percent": "0.00%",
    "date":    "mm/dd/yyyy",
}


def _apply_layout(tab: dict, layout: dict | None) -> tuple[list[dict], list[dict]]:
    """Return (visible_columns_in_order, rows) after applying the layout."""
    all_cols = list(tab.get("columns") or [])
    by_field = {c["field"]: c for c in all_cols}

    if not layout:
        return all_cols, list(tab.get("rows") or [])

    order = layout.get("order") or [c["field"] for c in all_cols]
    hidden = set(layout.get("hidden") or [])

    visible = [by_field[f] for f in order if f in by_field and f not in hidden]
    # Anything new the client didn't know about keeps its original order at the end.
    seen = {c["field"] for c in visible}
    for c in all_cols:
        if c["field"] not in seen and c["field"] not in hidden:
            visible.append(c)

    return visible, list(tab.get("rows") or [])


def _coerce_for_cell(value, col_type: str):
    """Best-effort coercion + sanitisation for an Excel cell.

    openpyxl raises on:
      - NaN / +inf / -inf floats
      - strings with ASCII control chars (\\x00, etc.)
      - strings longer than 32_767 chars
      - non-jsonable types like Decimal in some versions
    Whatever this function returns must be safe for openpyxl.
    """
    if value is None or value == "":
        return None

    if col_type == "date":
        if isinstance(value, (date, datetime)):
            return value
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except Exception:
            return _sanitise_text(value)

    if col_type in ("money", "int", "percent"):
        try:
            f = float(value)
        except (TypeError, ValueError):
            return _sanitise_text(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f

    return _sanitise_text(value)


def _sanitise_text(value):
    """Strip control chars and clamp length so openpyxl is happy."""
    s = str(value)
    if _BAD_CTRL.search(s):
        s = _BAD_CTRL.sub("", s)
    if len(s) > _MAX_CELL_CHARS:
        s = s[: _MAX_CELL_CHARS - 1] + "\u2026"
    return s


def _safe_sheet_name(name: str, used: set[str]) -> str:
    """Excel sheet names: max 31 chars, no : \\ / ? * [ ]"""
    bad = ':\\/?*[]'
    clean = "".join("_" if ch in bad else ch for ch in name).strip() or "Sheet"
    clean = clean[:31]
    if clean not in used:
        used.add(clean)
        return clean
    i = 2
    while True:
        candidate = f"{clean[:28]} ({i})"
        if candidate not in used:
            used.add(candidate)
            return candidate
        i += 1


def _autosize(ws, columns: list[dict], row_count: int) -> None:
    for idx, col in enumerate(columns, start=1):
        header_len = len(str(col.get("header") or col["field"]))
        # Cheap guess based on type, good enough for a first pass.
        type_guess = {
            "money":   14,
            "int":     10,
            "percent": 10,
            "date":    12,
            "text":    22,
        }.get(col.get("type", "text"), 16)
        width = min(42, max(header_len + 3, type_guess))
        ws.column_dimensions[get_column_letter(idx)].width = width


def build_workbook(payload: dict, layouts: dict[str, dict] | None = None) -> bytes:
    """Render the viewer payload into a .xlsx byte string.

    ``layouts`` is ``{tab_key: {"order": [...fields...], "hidden": [...fields...]}}``.
    Missing entries fall back to the tab's declared columns.
    """
    wb = Workbook()
    wb.remove(wb.active)

    used_names: set[str] = set()
    tabs = payload.get("tabs") or []
    layouts = layouts or {}

    if not tabs:
        ws = wb.create_sheet(title="Report")
        ws["A1"] = "No data."

    for tab in tabs:
        cols, rows = _apply_layout(tab, layouts.get(tab["key"]))
        sheet_name = _safe_sheet_name(tab.get("name") or tab["key"], used_names)
        ws = wb.create_sheet(title=sheet_name)

        for idx, col in enumerate(cols, start=1):
            cell = ws.cell(row=1, column=idx, value=col.get("header") or col["field"])
            cell.font = _HEADER_FONT
            cell.fill = _HEADER_FILL
            cell.alignment = _HEADER_ALIGN

        for r_idx, row in enumerate(rows, start=2):
            for c_idx, col in enumerate(cols, start=1):
                cell = ws.cell(
                    row=r_idx,
                    column=c_idx,
                    value=_coerce_for_cell(row.get(col["field"]), col.get("type", "text")),
                )
                fmt = _NUMBER_FORMATS.get(col.get("type"))
                if fmt:
                    cell.number_format = fmt

        ws.freeze_panes = "A2"
        _autosize(ws, cols, len(rows))

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
