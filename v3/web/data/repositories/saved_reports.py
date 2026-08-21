"""Saved-report (preset) repository (precious.db `saved_reports` table).

A preset is a named, per-user shortcut that captures a report's filter params +
grid layout so the owner can re-open "My March Ordered view" in one click. All
reads/writes are owner-scoped (user_id) so one user can never see or mutate
another's presets.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from web.data.connection import Database


@dataclass(frozen=True)
class SavedReport:
    id: int
    user_id: int
    report_key: str
    name: str
    params: dict
    layout: dict
    created_at: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "SavedReport":
        return cls(
            id=r["id"], user_id=r["user_id"], report_key=r["report_key"],
            name=r["name"], params=json.loads(r["params_json"] or "{}"),
            layout=json.loads(r["layout_json"] or "{}"), created_at=r["created_at"],
        )


class SavedReportRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, user_id: int, report_key: str, name: str,
               params: dict, layout: dict) -> int:
        """Create or overwrite (by name) a preset; returns its id."""
        with self.db.precious() as conn:
            conn.execute(
                "INSERT INTO saved_reports(user_id, report_key, name, params_json, layout_json)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(user_id, report_key, name) DO UPDATE SET"
                "   params_json=excluded.params_json, layout_json=excluded.layout_json",
                (user_id, report_key, name.strip(),
                 json.dumps(params or {}), json.dumps(layout or {})),
            )
            row = conn.execute(
                "SELECT id FROM saved_reports WHERE user_id=? AND report_key=? AND name=?",
                (user_id, report_key, name.strip()),
            ).fetchone()
            return row["id"]

    def list_for_user(self, user_id: int) -> list[SavedReport]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM saved_reports WHERE user_id=? ORDER BY report_key, name",
                (user_id,),
            ).fetchall()
            return [SavedReport.from_row(r) for r in rows]

    def get(self, preset_id: int, user_id: int) -> SavedReport | None:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT * FROM saved_reports WHERE id=? AND user_id=?",
                (preset_id, user_id),
            ).fetchone()
            return SavedReport.from_row(row) if row else None

    def update(self, preset_id: int, user_id: int, *, name: str | None = None,
               params: dict | None = None, layout: dict | None = None) -> bool:
        """Rename and/or replace filters/layout. Owner-scoped."""
        sets: list[str] = []
        vals: list = []
        if name is not None:
            stripped = name.strip()
            if not stripped:
                return False
            sets.append("name=?")
            vals.append(stripped)
        if params is not None:
            sets.append("params_json=?")
            vals.append(json.dumps(params or {}))
        if layout is not None:
            sets.append("layout_json=?")
            vals.append(json.dumps(layout or {}))
        if not sets:
            return False
        vals.extend([preset_id, user_id])
        with self.db.precious() as conn:
            try:
                cur = conn.execute(
                    f"UPDATE saved_reports SET {', '.join(sets)} WHERE id=? AND user_id=?",
                    vals,
                )
            except sqlite3.IntegrityError:
                return False
            return cur.rowcount == 1

    def delete(self, preset_id: int, user_id: int) -> bool:
        with self.db.precious() as conn:
            cur = conn.execute(
                "DELETE FROM saved_reports WHERE id=? AND user_id=?",
                (preset_id, user_id),
            )
            return cur.rowcount == 1
