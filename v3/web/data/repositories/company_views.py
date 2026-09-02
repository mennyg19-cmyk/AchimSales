"""Named company-wide views (shared filters + layout).

Default is still one-per-report in ``report_defaults``. These are extra named
views everyone can pick in Saved views and on schedules.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from web.data.connection import Database
from web.data.repositories.report_defaults import CUSTOM_VIEW_NAME, DEFAULT_VIEW_NAME, normalize_view_name

_NAME_MAX = 120


@dataclass(frozen=True)
class CompanyView:
    id: int
    report_key: str
    name: str
    params: dict
    layout: dict
    updated_at: str
    updated_by: int | None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "CompanyView":
        keys = r.keys()
        updated_by = r["updated_by"] if "updated_by" in keys else None
        return cls(
            id=r["id"], report_key=r["report_key"], name=r["name"],
            params=json.loads(r["params_json"] or "{}"),
            layout=json.loads(r["layout_json"] or "{}"),
            updated_at=r["updated_at"],
            updated_by=int(updated_by) if updated_by is not None else None,
        )


class CompanyViewRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, view_id: int) -> CompanyView | None:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT * FROM company_views WHERE id=?", (view_id,),
            ).fetchone()
            return CompanyView.from_row(row) if row else None

    def get_by_name(self, report_key: str, name: str) -> CompanyView | None:
        wanted = normalize_view_name(name)
        if wanted in (DEFAULT_VIEW_NAME, CUSTOM_VIEW_NAME):
            return None
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT * FROM company_views WHERE report_key=? AND name=?",
                (report_key, wanted),
            ).fetchone()
            return CompanyView.from_row(row) if row else None

    def get_layout(self, report_key: str, name: str) -> dict:
        row = self.get_by_name(report_key, name)
        return dict(row.layout) if row and isinstance(row.layout, dict) else {}

    def list_for_report(self, report_key: str) -> list[CompanyView]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM company_views WHERE report_key=? ORDER BY name COLLATE NOCASE",
                (report_key,),
            ).fetchall()
            return [CompanyView.from_row(r) for r in rows]

    def list_all(self) -> list[CompanyView]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM company_views ORDER BY report_key, name COLLATE NOCASE",
            ).fetchall()
            return [CompanyView.from_row(r) for r in rows]

    def upsert(self, report_key: str, name: str, *, params: dict, layout: dict,
               updated_by: int | None) -> CompanyView:
        stripped = normalize_view_name(name)
        if stripped in (DEFAULT_VIEW_NAME, CUSTOM_VIEW_NAME):
            raise ValueError("That name is reserved.")
        ts = datetime.now(timezone.utc).isoformat()
        with self.db.precious() as conn:
            conn.execute(
                "INSERT INTO company_views(report_key, name, params_json, layout_json,"
                " updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(report_key, name) DO UPDATE SET"
                " params_json=excluded.params_json, layout_json=excluded.layout_json,"
                " updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                (report_key, stripped, json.dumps(params or {}),
                 json.dumps(layout or {}), ts, updated_by),
            )
        saved = self.get_by_name(report_key, stripped)
        if saved is None:
            raise RuntimeError(f"failed to save company view {report_key}/{stripped}")
        return saved

    def delete(self, view_id: int, report_key: str) -> bool:
        with self.db.precious() as conn:
            cur = conn.execute(
                "DELETE FROM company_views WHERE id=? AND report_key=?",
                (view_id, report_key),
            )
            return cur.rowcount > 0
