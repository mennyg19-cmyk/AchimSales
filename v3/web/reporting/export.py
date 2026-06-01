"""Styled Excel export from a report payload (openpyxl).

One worksheet per tab, formatted to match the look of the live app's exports:
a bold grey header row, thin cell borders, subtle zebra striping, and real
Excel number formats per column type (currency, integer, percent, date). When
a tab is grouped (via the saved/clicked view), each group gets a subtotal line
and the sheet ends with a grand total - mirroring the legacy test app.

Payload shape: {"tabs": [{"key", "name", "columns": [...], "rows": [{col: val}],
"layout"?}]}. ``columns`` is either a list of header strings or a list of
{"field", "header", "type"} dicts (the viewer shape); both are supported.

``build_workbook(payload, layout)`` accepts the viewer's serialized layout
(``{"views": {<tabKey>: {"group": [...], ...}}}``) to drive per-tab grouping.
``apply_layout`` (web.delivery.layout) should be run on the payload first to
replay column order / hide / sort / filter; this module only adds grouping +
styling on top. ``payload_to_xlsx`` is the no-layout shortcut kept for the
delivery + test callers. Pure transform -> bytes; no Flask, no DB.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from io import BytesIO
from itertools import groupby
from typing import Any

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Excel sheet-title constraints: <=31 chars, none of : \ / ? * [ ]
_INVALID_SHEET = re.compile(r"[:\\/?*\[\]]")
# CSV/Excel formula-injection: a cell whose text starts with one of these can be
# executed as a formula. Prefix with an apostrophe to force it to literal text.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n")
# openpyxl rejects these ASCII control chars in cell text; strip them.
_BAD_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MAX_CELL_CHARS = 32767

_NUMERIC_TYPES = {"money", "int", "percent"}

# --- Number formats (match the on-screen grid + the live exports) ---
_FMT = {
    "money": '"$"#,##0.00',
    "int": "#,##0",
    "percent": "0.0%",
    "date": "M/D/YYYY",
}

# --- Styling (live palette: grey header, light zebra, darker totals) ---
_HEADER_FILL = PatternFill("solid", fgColor="E0E0E0")
_HEADER_FONT = Font(bold=True)
_HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
_ZEBRA_FILL = PatternFill("solid", fgColor="F2F2F2")
_TOTAL_FILL = PatternFill("solid", fgColor="D9D9D9")
_TOTAL_FONT = Font(bold=True)
_GROUP_FILL = PatternFill("solid", fgColor="BDD7EE")
_GROUP_FONT = Font(bold=True)
_THIN = Side(style="thin", color="000000")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _safe_text(value: Any) -> str:
    """Stringify, neutralise formula injection, strip control chars, clamp length."""
    s = str(value)
    if s[:1] in _FORMULA_TRIGGERS:
        s = "'" + s
    if _BAD_CTRL.search(s):
        s = _BAD_CTRL.sub("", s)
    if len(s) > _MAX_CELL_CHARS:
        s = s[: _MAX_CELL_CHARS - 1] + "\u2026"
    return s


def _coerce(value: Any, col_type: str | None) -> tuple[Any, str | None]:
    """Return (excel_value, number_format) for a typed cell, openpyxl-safe."""
    if value is None or value == "":
        return None, None
    if col_type == "date":
        if isinstance(value, (date, datetime)):
            return value, _FMT["date"]
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date(), _FMT["date"]
        except (TypeError, ValueError):
            return _safe_text(value), None
    if col_type in _NUMERIC_TYPES:
        try:
            f = float(value)
        except (TypeError, ValueError):
            return _safe_text(value), None
        if math.isnan(f) or math.isinf(f):
            return None, None
        return f, _FMT[col_type]
    return _safe_text(value), None


def _num(value: Any) -> float | None:
    try:
        f = float(value)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _safe_sheet_title(name: str, used: set[str]) -> str:
    title = _INVALID_SHEET.sub(" ", (name or "Sheet").strip())[:31] or "Sheet"
    base, n = title, 2
    while title.lower() in used:
        suffix = f" {n}"
        title = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(title.lower())
    return title


def _columns_meta(columns: list, rows: list) -> list[tuple[str, str, str | None]]:
    """Normalise a tab's columns to (header, field, type) triples.

    Supports the viewer's {"field","header","type"} dicts, plain header strings,
    or (when no columns are declared) the keys of the first row.
    """
    if columns and isinstance(columns[0], dict):
        return [(
            str(c.get("header") or c.get("field") or ""),
            str(c.get("field") or c.get("header") or ""),
            c.get("type"),
        ) for c in columns]
    if columns:
        return [(str(c), str(c), None) for c in columns]
    if rows:
        return [(str(k), str(k), None) for k in rows[0].keys()]
    return []


def _group_sort_key(value: Any) -> tuple:
    if value is None or value == "":
        return (1, "")
    return (0, str(value).lower())


def _autosize(ws, metas: list[tuple[str, str, str | None]]) -> None:
    type_guess = {"money": 14, "int": 10, "percent": 10, "date": 12, "text": 22}
    for idx, (header, _field, ctype) in enumerate(metas, start=1):
        guess = type_guess.get(ctype or "text", 16)
        width = min(45, max(len(header) + 3, guess))
        ws.column_dimensions[get_column_letter(idx)].width = width


def _write_header(ws, metas: list[tuple[str, str, str | None]]) -> None:
    for i, (header, _field, _ctype) in enumerate(metas, start=1):
        cell = ws.cell(row=1, column=i, value=_safe_text(header))
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _BORDER
        cell.alignment = _HEADER_ALIGN


def _write_data_row(ws, r: int, metas, row: dict, zebra: bool, acc: dict[str, float]) -> None:
    for i, (_header, field, ctype) in enumerate(metas, start=1):
        value, fmt = _coerce(row.get(field), ctype)
        cell = ws.cell(row=r, column=i, value=value)
        cell.border = _BORDER
        if fmt:
            cell.number_format = fmt
        if zebra:
            cell.fill = _ZEBRA_FILL
        if ctype in _NUMERIC_TYPES:
            x = _num(row.get(field))
            if x is not None:
                acc[field] = acc.get(field, 0.0) + x


def _write_total_row(ws, r: int, metas, sums: dict[str, float], label: str) -> None:
    for i, (_header, field, ctype) in enumerate(metas, start=1):
        if i == 1:
            value, fmt = label, None
        elif ctype in _NUMERIC_TYPES and field in sums:
            value, fmt = sums[field], _FMT[ctype]
        else:
            value, fmt = None, None
        cell = ws.cell(row=r, column=i, value=value)
        cell.font = _TOTAL_FONT
        cell.fill = _TOTAL_FILL
        cell.border = _BORDER
        if fmt:
            cell.number_format = fmt


def _write_group_banner(ws, r: int, ncol: int, text: str) -> None:
    for i in range(1, ncol + 1):
        cell = ws.cell(row=r, column=i, value=_safe_text(text) if i == 1 else None)
        cell.font = _GROUP_FONT
        cell.fill = _GROUP_FILL
        cell.border = _BORDER


def _write_grid(ws, metas, rows: list, group_fields: list[str]) -> None:
    if not metas:
        return
    ncol = len(metas)
    _write_header(ws, metas)

    if group_fields:
        gf = group_fields[0]
        glabel = next((h for h, f, _t in metas if f == gf), gf)
        ordered = sorted(rows, key=lambda x: _group_sort_key(x.get(gf)))
        grand: dict[str, float] = {}
        r, data_n = 2, 0
        for _key, grp_iter in groupby(ordered, key=lambda x: _group_sort_key(x.get(gf))):
            grp = list(grp_iter)
            gval = grp[0].get(gf)
            _write_group_banner(ws, r, ncol, f"{glabel}: {gval if gval not in (None, '') else '(blank)'}")
            r += 1
            sub: dict[str, float] = {}
            for row in grp:
                _write_data_row(ws, r, metas, row, data_n % 2 == 1, sub)
                r += 1
                data_n += 1
            _write_total_row(ws, r, metas, sub, f"Total \u2014 {gval if gval not in (None, '') else '(blank)'}")
            r += 1
            for k, val in sub.items():
                grand[k] = grand.get(k, 0.0) + val
        if rows:
            _write_total_row(ws, r, metas, grand, "Grand total")
    else:
        for idx, row in enumerate(rows):
            _write_data_row(ws, idx + 2, metas, row, idx % 2 == 1, {})
        if rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(ncol)}{len(rows) + 1}"

    ws.freeze_panes = "A2"
    _autosize(ws, metas)


def _write_commission(ws, tab: dict) -> None:
    """Per-salesman monthly + YTD block (live-style commissions pivot)."""
    year = tab.get("year") or ""
    labels = list(tab.get("month_labels") or [])
    salesmen = tab.get("salesmen") or []
    ws.cell(row=1, column=1, value=f"Commissions Summary {year}".strip()).font = Font(bold=True, size=14)
    if not salesmen:
        ws.cell(row=3, column=1, value="No commissioned salesmen for this period.")
        ws.column_dimensions["A"].width = 40
        return

    lines = [
        ("SubTotal Invoices", "subtotal_invoices"),
        ("Total Invoices", "total_invoices"),
        ("Credits", "credits"),
        ("Net Commission", "net_commission"),
        ("Commission", "commission"),
    ]
    first_col = 2
    r = 3
    for s in salesmen:
        title = f"{s.get('salesman_number', '')} - {s.get('salesman_name', '')}".strip(" -")
        ytd_col = first_col + len(labels)
        banner = ws.cell(row=r, column=1, value=title)
        banner.font, banner.fill = _GROUP_FONT, _GROUP_FILL
        for mi, lab in enumerate(labels):
            c = ws.cell(row=r, column=first_col + mi, value=lab)
            c.font, c.fill = _GROUP_FONT, _GROUP_FILL
            c.alignment = Alignment(horizontal="center")
        c = ws.cell(row=r, column=ytd_col, value="YTD")
        c.font, c.fill = _GROUP_FONT, _GROUP_FILL
        r += 1
        monthly = s.get("monthly") or []
        ytd = s.get("ytd") or {}
        for label, field in lines:
            ws.cell(row=r, column=1, value=label).font = Font(bold=True)
            for mi in range(len(labels)):
                m = monthly[mi] if mi < len(monthly) else {}
                cell = ws.cell(row=r, column=first_col + mi, value=float(m.get(field) or 0.0))
                cell.number_format = _FMT["money"]
            cell = ws.cell(row=r, column=ytd_col, value=float(ytd.get(field) or 0.0))
            cell.number_format, cell.font = _FMT["money"], Font(bold=True)
            r += 1
        r += 1  # blank row between salesmen
    ws.column_dimensions["A"].width = 30
    ws.freeze_panes = "A2"


def build_workbook(payload: dict[str, Any], layout: dict | None = None) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    views = (layout or {}).get("views") or {}
    tabs = payload.get("tabs") or []
    if not tabs:
        wb.create_sheet(_safe_sheet_title("Report", used))
    for tab in tabs:
        ws = wb.create_sheet(_safe_sheet_title(tab.get("name", "Report"), used))
        if tab.get("layout") == "commission_cards" and tab.get("salesmen") is not None:
            _write_commission(ws, tab)
            continue
        rows = list(tab.get("rows") or [])
        metas = _columns_meta(list(tab.get("columns") or []), rows)
        v = views.get(tab.get("key")) or {}
        group_fields = [g for g in (v.get("group") or []) if any(f == g for _h, f, _t in metas)]
        _write_grid(ws, metas, rows, group_fields)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def payload_to_xlsx(payload: dict[str, Any]) -> bytes:
    """No-layout styled export (one styled sheet per tab, no grouping)."""
    return build_workbook(payload, None)
