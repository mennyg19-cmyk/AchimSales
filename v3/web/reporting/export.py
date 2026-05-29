"""Excel export from a report payload (openpyxl).

Payload shape: {"tabs": [{"name", "columns": [...], "rows": [ {col: val} ]}]}.
One worksheet per tab. Pure transform -> bytes; no Flask, no DB.
"""

from __future__ import annotations

import io
import re
from typing import Any

# Excel sheet-title constraints: <=31 chars, none of : \ / ? * [ ]
_INVALID_SHEET = re.compile(r"[:\\/?*\[\]]")

# CSV/Excel formula-injection: a cell whose text starts with one of these can be
# executed as a formula. Prefix with an apostrophe to force it to literal text.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in _FORMULA_TRIGGERS:
        return "'" + value
    return value


def _safe_sheet_title(name: str, used: set[str]) -> str:
    title = _INVALID_SHEET.sub(" ", (name or "Sheet").strip())[:31] or "Sheet"
    base, n = title, 2
    while title.lower() in used:
        suffix = f" {n}"
        title = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(title.lower())
    return title


def payload_to_xlsx(payload: dict[str, Any]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    tabs = payload.get("tabs") or []
    if not tabs:
        wb.create_sheet(_safe_sheet_title("Report", used))
    for tab in tabs:
        ws = wb.create_sheet(_safe_sheet_title(tab.get("name", "Report"), used))
        columns = list(tab.get("columns") or [])
        rows = tab.get("rows") or []
        if not columns and rows:
            columns = list(rows[0].keys())
        if columns:
            ws.append([_safe_cell(c) for c in columns])
        for row in rows:
            ws.append([_safe_cell(row.get(col)) for col in columns])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
