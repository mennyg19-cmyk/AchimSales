"""Turns one finished tab into a downloadable CSV or Excel file."""

# === What's in this file ===
# The viewer shows a tab on screen; these build the same tab as a file to save.
# Both read the tab payload the engine already built (columns + rows + total),
# so a download is always exactly what's on screen. CSV uses the standard
# library; Excel uses openpyxl (already installed for the live app's exports).
#
# to_csv() -- columns + rows + total -> CSV bytes
# to_xlsx() -- columns + rows + total -> .xlsx bytes (money/percent formatted)
# filename_for() -- a safe "report_tab.ext" download name

from __future__ import annotations

import csv
import io
import re
from typing import Any

_NUMBER_FORMATS = {
    "money": "#,##0.00",
    "int": "#,##0",
    "percent": "0.00%",
}


def _headers(tab: dict[str, Any]) -> list[dict]:
    return tab.get("columns", []) or []


# A leading =, +, -, @ (or tab/CR) makes a spreadsheet treat a text cell as a
# formula. Prefix such text with a quote so it stays plain text on open.
_FORMULA_LEADERS = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    # Keep real numbers numeric so Excel can format them; only text needs guarding.
    if isinstance(value, (int, float, bool)):
        return value
    text = value if isinstance(value, str) else str(value)
    if text and text[0] in _FORMULA_LEADERS:
        return "'" + text
    return text


def to_csv(tab: dict[str, Any]) -> bytes:
    columns = _headers(tab)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([c.get("label") or c.get("field") for c in columns])
    for row in tab.get("rows", []):
        writer.writerow([_cell(row.get(c["field"])) for c in columns])
    if tab.get("total"):
        writer.writerow([_cell(tab["total"].get(c["field"])) for c in columns])
    # Excel opens UTF-8 CSV cleanly when it sees a BOM.
    return buffer.getvalue().encode("utf-8-sig")


def to_xlsx(tab: dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    columns = _headers(tab)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = (tab.get("label") or "Report")[:31]

    bold = Font(bold=True)
    sheet.append([c.get("label") or c.get("field") for c in columns])
    for cell in sheet[1]:
        cell.font = bold

    def write_row(row: dict[str, Any], is_total: bool) -> None:
        sheet.append([_cell(row.get(c["field"])) for c in columns])
        written = sheet[sheet.max_row]
        for cell, column in zip(written, columns):
            number_format = _NUMBER_FORMATS.get(column.get("type"))
            if number_format and isinstance(cell.value, (int, float)):
                cell.number_format = number_format
            if is_total:
                cell.font = bold

    for row in tab.get("rows", []):
        write_row(row, False)
    if tab.get("total"):
        write_row(tab["total"], True)

    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def filename_for(report_key: str, tab_key: str, ext: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{report_key}_{tab_key}").strip("_") or "report"
    return f"{stem}.{ext}"
