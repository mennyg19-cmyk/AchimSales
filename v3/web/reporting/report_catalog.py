"""Remember the tabs and columns a report build actually produced."""

from __future__ import annotations

import sqlite3

from web.data.connection import Database


def remember_catalog(db: Database, report_key: str, payload: dict | None) -> None:
    tabs = normalize_tabs(payload)
    if not tabs or not report_key:
        return
    with db.precious() as conn:
        for pos, tab in enumerate(tabs, start=1):
            conn.execute(
                """INSERT INTO report_catalog_tabs (report_key, tab_key, tab_name, position)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(report_key, tab_key) DO UPDATE SET
                     tab_name = excluded.tab_name,
                     position = excluded.position""",
                (report_key, tab["key"], tab["name"], pos),
            )
            if not tab["columns"]:
                continue
            conn.execute(
                "DELETE FROM report_catalog_columns WHERE report_key = ? AND tab_key = ?",
                (report_key, tab["key"]),
            )
            for cpos, col in enumerate(tab["columns"], start=1):
                conn.execute(
                    """INSERT INTO report_catalog_columns
                       (report_key, tab_key, position, field, header)
                       VALUES (?, ?, ?, ?, ?)""",
                    (report_key, tab["key"], cpos, col["field"], col["header"]),
                )


def read_catalog(db: Database, report_key: str) -> list[dict]:
    try:
        with db.precious() as conn:
            rows = conn.execute(
                """SELECT tab_key, tab_name FROM report_catalog_tabs
                   WHERE report_key = ? ORDER BY position, tab_key""",
                (report_key,),
            ).fetchall()
            if not rows:
                return []
            out = []
            for row in rows:
                cols = conn.execute(
                    """SELECT field, header FROM report_catalog_columns
                       WHERE report_key = ? AND tab_key = ? ORDER BY position, field""",
                    (report_key, row["tab_key"]),
                ).fetchall()
                out.append({
                    "key": row["tab_key"],
                    "name": row["tab_name"],
                    "columns": [{"field": col["field"], "header": col["header"]} for col in cols],
                })
            return out
    except sqlite3.OperationalError:
        return []


def normalize_tabs(payload: dict | None) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("tabs")
    if raw is None and isinstance(payload.get("data"), dict):
        raw = payload["data"].get("tabs")
    items: list[tuple[str, dict]] = []
    if isinstance(raw, list):
        for index, tab in enumerate(raw):
            if isinstance(tab, dict):
                key = str(tab.get("key") or tab.get("name") or f"tab_{index}").strip()
                if key:
                    items.append((key, tab))
    elif isinstance(raw, dict):
        for key, tab in raw.items():
            if isinstance(tab, dict):
                items.append((str(key), tab))
    out = []
    for key, tab in items:
        name = str(tab.get("name") or key)
        out.append({"key": key, "name": name, "columns": _columns(tab)})
    return out


def _columns(tab: dict) -> list[dict]:
    cols = []
    seen: set[str] = set()
    for col in tab.get("columns") or []:
        if isinstance(col, dict):
            field = str(col.get("field") or col.get("header") or "").strip()
            header = str(col.get("header") or field)
        else:
            field = header = str(col).strip()
        if field and field not in seen:
            seen.add(field)
            cols.append({"field": field, "header": header})
    if cols:
        return cols
    for row in tab.get("rows") or []:
        if not isinstance(row, dict):
            continue
        for field in row:
            text = str(field).strip()
            if text and text not in seen:
                seen.add(text)
                cols.append({"field": text, "header": text})
    return cols
