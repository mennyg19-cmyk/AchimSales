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

Built in openpyxl **write-only (streaming) mode**: rows are appended top-to-bottom
and flushed to a temp file as they go, so a six-tab report with hundreds of
thousands of rows builds in seconds with flat memory instead of materialising
every styled cell in RAM (which made big exports time out).
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from io import BytesIO
from itertools import groupby
from typing import Any

from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from report_engine.lib import iso_date

# Excel sheet-title constraints: <=31 chars, none of : \ / ? * [ ]
_INVALID_SHEET = re.compile(r"[:\\/?*\[\]]")
# CSV/Excel formula-injection: a cell whose text starts with one of these can be
# executed as a formula. Prefix with an apostrophe to force it to literal text.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n")
# openpyxl rejects these ASCII control chars in cell text; strip them.
_BAD_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MAX_CELL_CHARS = 32767

_NUMERIC_TYPES = {"money", "int", "percent"}
# Columns that can be meaningfully summed for subtotal/grand-total rows. Percent
# is deliberately excluded: summing raw percentages is nonsense (the on-screen
# grid excludes percent bottom-calcs too), so percent total cells stay blank.
_SUMMABLE_TYPES = {"money", "int"}

# --- Number formats (match the on-screen grid + the live exports) ---
_FMT = {
    "money": '"$"#,##0.00',
    "int": "#,##0",
    "percent": "0.0%",
    "date": "YYYY-MM-DD",
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
# Live salesman YoY column bands (month / YTD / full-year) + red negatives.
_FONT_BAND_BLUE = Font(color="0000CC")
_FONT_BAND_GREEN = Font(color="008000")
_FONT_BAND_PURPLE = Font(color="800080")
_FONT_BAND_RED = Font(color="FF0000")
_BAND_FONTS = (_FONT_BAND_BLUE, _FONT_BAND_GREEN, _FONT_BAND_PURPLE)
_FILL_LIGHT_GREY = PatternFill("solid", fgColor="E8E8E8")


def _fulfillment_fill(score: Any) -> PatternFill | None:
    """Red (0) → yellow (0.5) → green (1). Same RGB as the old Ordered writer."""
    try:
        s = float(score)
        if s < 0 or s != s:
            return _FILL_LIGHT_GREY
    except (TypeError, ValueError):
        return None
    s = max(0.0, min(1.0, s))
    red, yellow, green = (255, 199, 206), (255, 235, 156), (198, 239, 206)
    if s <= 0:
        r, g, b = red
    elif s >= 1:
        r, g, b = green
    elif s < 0.5:
        t = s * 2
        r = int(red[0] + (yellow[0] - red[0]) * t)
        g = int(red[1] + (yellow[1] - red[1]) * t)
        b = int(red[2] + (yellow[2] - red[2]) * t)
    else:
        t = (s - 0.5) * 2
        r = int(yellow[0] + (green[0] - yellow[0]) * t)
        g = int(yellow[1] + (green[1] - yellow[1]) * t)
        b = int(yellow[2] + (green[2] - yellow[2]) * t)
    return PatternFill("solid", fgColor=f"{r:02X}{g:02X}{b:02X}")


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
        s = iso_date(value)
        if s and len(s) == 10 and s[4] == "-" and s[7] == "-":
            try:
                return date.fromisoformat(s), _FMT["date"]
            except ValueError:
                pass
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


def _cell(ws, value: Any, *, fmt: str | None = None, font: Font | None = None,
          fill: PatternFill | None = None, align: Alignment | None = None,
          border: Border | None = None) -> WriteOnlyCell:
    """A styled write-only cell. Styles (Font/Fill/Border) are shared singletons
    so openpyxl dedups them; only the lightweight cell object is per-value."""
    c = WriteOnlyCell(ws, value=value)
    if font:
        c.font = font
    if fill:
        c.fill = fill
    if border:
        c.border = border
    if align:
        c.alignment = align
    if fmt:
        c.number_format = fmt
    return c


def _header_cells(ws, metas) -> list[WriteOnlyCell]:
    return [_cell(ws, _safe_text(h), font=_HEADER_FONT, fill=_HEADER_FILL,
                  align=_HEADER_ALIGN, border=_BORDER) for h, _f, _t in metas]


def _data_cells(ws, metas, row: dict, acc: dict[str, float],
                *, salesman_bands: bool = False) -> list[WriteOnlyCell]:
    """Data row cells — styled lightly (number formats only, no borders/zebra).

    The live app applies no per-cell borders or zebra on data rows; only headers,
    totals, and group banners get fills/borders. Skipping these two style objects
    on every cell is the single biggest speedup for large exports (borders alone
    were ~40% of openpyxl's write-time on a 120k-row grid).

    Salesman month tabs optionally get Live's blue/green/purple font bands
    (and red for negatives) while still using write-only streaming.
    """
    cells = []
    for idx, (_header, field, ctype) in enumerate(metas):
        value, fmt = _coerce(row.get(field), ctype)
        font = None
        fill = _fulfillment_fill(row.get(field)) if field == "Fulfillment %" else None
        if salesman_bands and idx >= 4:
            band = _BAND_FONTS[min((idx - 4) // 4, 2)]
            n = _num(row.get(field))
            font = _FONT_BAND_RED if n is not None and n < 0 else band
        cells.append(_cell(ws, value, fmt=fmt, font=font, fill=fill))
        if ctype in _SUMMABLE_TYPES:
            x = _num(row.get(field))
            if x is not None:
                acc[field] = acc.get(field, 0.0) + x
    return cells


def _total_cells(ws, metas, sums: dict[str, float], label: str) -> list[WriteOnlyCell]:
    # Put the "Total"/"Grand total" label in the first NON-summable column so a
    # numeric first column (e.g. an order number is text, but a money/qty first
    # column isn't) keeps its own subtotal instead of being overwritten by text.
    label_idx = next((i for i, (_h, _f, t) in enumerate(metas) if t not in _SUMMABLE_TYPES), 0)
    cells = []
    for i, (_header, field, ctype) in enumerate(metas):
        if i == label_idx:
            value, fmt = label, None
        elif ctype in _NUMERIC_TYPES and field in sums:
            value, fmt = sums[field], _FMT[ctype]
        else:
            value, fmt = None, None
        cells.append(_cell(ws, value, fmt=fmt, font=_TOTAL_FONT, fill=_TOTAL_FILL, border=_BORDER))
    return cells


def _banner_cells(ws, ncol: int, text: str) -> list[WriteOnlyCell]:
    cells = [_cell(ws, _safe_text(text), font=_GROUP_FONT, fill=_GROUP_FILL, border=_BORDER)]
    cells += [_cell(ws, None, font=_GROUP_FONT, fill=_GROUP_FILL, border=_BORDER) for _ in range(ncol - 1)]
    return cells


def _stream_grid(ws, metas, rows: list, group_fields: list[str],
                 *, salesman_bands: bool = False) -> None:
    if not metas:
        return
    ncol = len(metas)
    # Worksheet-level properties are written at save time, so they can be set
    # before appending rows (write-only mode only forbids per-cell random access).
    ws.freeze_panes = "A2"
    _autosize(ws, metas)
    if not group_fields and rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(ncol)}{len(rows) + 1}"
    ws.append(_header_cells(ws, metas))

    if group_fields:
        gf = group_fields[0]
        glabel = next((h for h, f, _t in metas if f == gf), gf)
        ordered = sorted(rows, key=lambda x: _group_sort_key(x.get(gf)))
        grand: dict[str, float] = {}
        for _key, grp_iter in groupby(ordered, key=lambda x: _group_sort_key(x.get(gf))):
            grp = list(grp_iter)
            gval = grp[0].get(gf)
            label = gval if gval not in (None, "") else "(blank)"
            ws.append(_banner_cells(ws, ncol, f"{glabel}: {label}"))
            sub: dict[str, float] = {}
            for row in grp:
                ws.append(_data_cells(ws, metas, row, sub, salesman_bands=salesman_bands))
            ws.append(_total_cells(ws, metas, sub, f"Total \u2014 {label}"))
            for k, val in sub.items():
                grand[k] = grand.get(k, 0.0) + val
        if rows:
            ws.append(_total_cells(ws, metas, grand, "Grand total"))
    else:
        grand: dict[str, float] = {}
        for row in rows:
            ws.append(_data_cells(ws, metas, row, grand, salesman_bands=salesman_bands))
        if rows:
            ws.append(_total_cells(ws, metas, grand, "Total"))


def _stream_commission(ws, tab: dict) -> None:
    """Per-salesman monthly + YTD block (live Excel commissions layout)."""
    year = tab.get("year") or ""
    labels = list(tab.get("month_labels") or [])
    salesmen = tab.get("salesmen") or []
    ws.freeze_panes = "A2"
    title = f"Commissions Summary ({year})" if year else "Commissions Summary"
    ws.append([_cell(ws, title, font=Font(bold=True, size=14))])
    if not salesmen:
        ws.column_dimensions["A"].width = 48
        ws.append([])
        ws.append([_cell(ws, "No commissioned salesmen for this period.")])
        return
    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 8

    lines = [
        ("SubTotal Invoices:", "subtotal_invoices"),
        ("Total Tariff Charges:", "tariff_charges"),
        ("Total Freight Charges:", "freight_charges"),
        ("Total CC Charges:", "cc_charges"),
        ("Total Invoices: (SubTotal+Tariff+Freight+CC)", "total_invoices"),
        ("Total Credits:", "credits"),
        ("Net Commission Amount (Less Freight and CC)", "net_commission"),
        ("Commission:", "commission"),
    ]
    ws.append([])  # row 2 spacer (block starts on row 3, matching the live layout)
    center = Alignment(horizontal="center")
    yy = str(year)[-2:] if year else ""
    for s in salesmen:
        num = str(s.get("salesman_number") or s.get("salesman") or "").strip()
        name = str(s.get("salesman_name") or "").strip()
        title_sm = f"{num} - {name}".strip(" -")
        banner = [_cell(ws, _safe_text(title_sm), font=_GROUP_FONT, fill=_GROUP_FILL)]
        banner.append(_cell(ws, "", font=_GROUP_FONT, fill=_GROUP_FILL))
        for lab in labels:
            hdr = f"{lab}-{yy}" if yy else lab
            banner.append(_cell(ws, _safe_text(hdr), font=_GROUP_FONT, fill=_GROUP_FILL, align=center))
        banner.append(_cell(ws, "YTD Total", font=_GROUP_FONT, fill=_GROUP_FILL, align=center))
        ws.append(banner)
        monthly = s.get("monthly") or []
        ytd = s.get("ytd") or {}
        pct = float(s.get("commission_pct") or 0.0)
        for label, field in lines:
            line = [_cell(ws, _safe_text(label), font=_TOTAL_FONT)]
            if field == "commission":
                line.append(_cell(ws, pct, fmt=_FMT["percent"]))
            else:
                line.append(_cell(ws, ""))
            for mi in range(len(labels)):
                m = monthly[mi] if mi < len(monthly) else {}
                line.append(_cell(ws, float(m.get(field) or 0.0), fmt=_FMT["money"]))
            line.append(_cell(ws, float(ytd.get(field) or 0.0), fmt=_FMT["money"], font=_TOTAL_FONT))
            ws.append(line)
        pay = [_cell(ws, _safe_text(f"Total Payable: {title_sm}"), font=_TOTAL_FONT)]
        pay.append(_cell(ws, ""))
        for _ in labels:
            pay.append(_cell(ws, ""))
        pay.append(_cell(
            ws,
            float(ytd.get("total_payable") or ytd.get("commission") or 0.0),
            fmt=_FMT["money"],
            font=_TOTAL_FONT,
        ))
        ws.append(pay)
        ws.append([])  # blank row between salesmen

def build_workbook(payload: dict[str, Any], layout: dict | None = None) -> bytes:
    from openpyxl import Workbook

    wb = Workbook(write_only=True)  # streaming: flat memory, fast on huge reports
    used: set[str] = set()
    views = (layout or {}).get("views") if isinstance(layout, dict) else None
    views = views if isinstance(views, dict) else {}
    tabs = payload.get("tabs") or []
    if not tabs:
        wb.create_sheet(_safe_sheet_title("Report", used))
    for tab in tabs:
        ws = wb.create_sheet(_safe_sheet_title(tab.get("name", "Report"), used))
        if tab.get("layout") == "commission_cards" and tab.get("salesmen") is not None:
            _stream_commission(ws, tab)
            continue
        rows = list(tab.get("rows") or [])
        metas = _columns_meta(list(tab.get("columns") or []), rows)
        v = views.get(tab.get("key"))
        v = v if isinstance(v, dict) else {}
        # A group field may be hidden (so absent from metas) yet still present in
        # the row dicts - honour it from the row data, not just visible columns.
        known = {f for _h, f, _t in metas} | (set(rows[0].keys()) if rows else set())
        wanted = v.get("group") if isinstance(v.get("group"), list) else []
        if not wanted:
            wanted = tab.get("default_group") if isinstance(tab.get("default_group"), list) else []
        group_fields = [g for g in wanted if g in known]
        salesman_bands = (payload.get("report_key") == "salesman"
                          and tab.get("layout") != "commission_cards")
        _stream_grid(ws, metas, rows, group_fields, salesman_bands=salesman_bands)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def payload_to_xlsx(payload: dict[str, Any]) -> bytes:
    """No-layout styled export (one styled sheet per tab, no grouping)."""
    return build_workbook(payload, None)
