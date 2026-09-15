"""Build an .xlsx of data.tabs for download. Dummy-site export; no office call."""

from __future__ import annotations

import io

from openpyxl import Workbook


def workbook_bytes(payload: dict) -> bytes:
    data = payload.get("data") or {}
    tabs = data.get("tabs") or {}
    book = Workbook()
    first = True
    for key, tab in tabs.items():
        sheet = book.active if first else book.create_sheet()
        first = False
        sheet.title = str(tab.get("name") or key)[:31]
        rows = tab.get("rows") or []
        if not rows:
            sheet.append(["(no rows)"])
            continue
        headers = list(rows[0].keys())
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(col) for col in headers])
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()
