"""Named company-wide views (shared filters + layout).

Default is one-per-report (kind ``default``). These are extra named views
(kind ``company``) everyone can pick in Saved views and on schedules.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from web.data.connection import Database
from web.data.normalized_views import (
    _upsert_view,
    assemble_layout,
    assemble_params,
    assign_handles,
    canonicalize_layout,
    canonicalize_params,
    company_view_id,
    next_legacy_id,
)
from web.data.repositories.report_defaults import CUSTOM_VIEW_NAME, DEFAULT_VIEW_NAME, normalize_view_name

@dataclass(frozen=True)
class CompanyView:
    id: int
    report_key: str
    name: str
    params: dict
    layout: dict
    updated_at: str
    updated_by: int | None

_SOURCE = "company_views"


def _select() -> str:
    return (
        "SELECT views.legacy_id AS id, views.report_key, views.name, views.updated_at,"
        " views.updated_by_handle, views.id AS view_id"
        " FROM views WHERE kind='company' AND legacy_source=?"
    )


def _one(conn: sqlite3.Connection, row: sqlite3.Row | None) -> CompanyView | None:
    if row is None:
        return None
    updated_by = None
    if row["updated_by_handle"]:
        user = conn.execute(
            "SELECT id FROM users WHERE handle=?", (row["updated_by_handle"],),
        ).fetchone()
        updated_by = int(user["id"]) if user else None
    return CompanyView(
        id=int(row["id"]), report_key=row["report_key"], name=row["name"],
        params=assemble_params(conn, row["view_id"]),
        layout=assemble_layout(conn, row["view_id"]),
        updated_at=row["updated_at"] or "",
        updated_by=updated_by,
    )


class CompanyViewRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, view_id: int) -> CompanyView | None:
        with self.db.precious() as conn:
            row = conn.execute(
                _select() + " AND legacy_id=?", (_SOURCE, view_id),
            ).fetchone()
            return _one(conn, row)

    def get_by_name(self, report_key: str, name: str) -> CompanyView | None:
        wanted = normalize_view_name(name)
        if wanted in (DEFAULT_VIEW_NAME, CUSTOM_VIEW_NAME):
            return None
        with self.db.precious() as conn:
            row = conn.execute(
                _select() + " AND report_key=? AND name=?",
                (_SOURCE, report_key, wanted),
            ).fetchone()
            return _one(conn, row)

    def get_layout(self, report_key: str, name: str) -> dict:
        row = self.get_by_name(report_key, name)
        return dict(row.layout) if row and isinstance(row.layout, dict) else {}

    def list_for_report(self, report_key: str) -> list[CompanyView]:
        with self.db.precious() as conn:
            rows = conn.execute(
                _select() + " AND report_key=? ORDER BY name COLLATE NOCASE",
                (_SOURCE, report_key),
            ).fetchall()
            return [v for r in rows if (v := _one(conn, r))]

    def list_all(self) -> list[CompanyView]:
        with self.db.precious() as conn:
            rows = conn.execute(
                _select() + " ORDER BY report_key, name COLLATE NOCASE",
                (_SOURCE,),
            ).fetchall()
            return [v for r in rows if (v := _one(conn, r))]

    def upsert(self, report_key: str, name: str, *, params: dict, layout: dict,
               updated_by: int | None) -> CompanyView:
        stripped = normalize_view_name(name)
        if stripped in (DEFAULT_VIEW_NAME, CUSTOM_VIEW_NAME):
            raise ValueError("That name is reserved.")
        with self.db.precious() as conn:
            handles = assign_handles(conn)
            existing = conn.execute(
                _select() + " AND report_key=? AND name=?",
                (_SOURCE, report_key, stripped),
            ).fetchone()
            legacy_id = int(existing["id"]) if existing else next_legacy_id(conn, _SOURCE)
            _upsert_view(
                conn, view_id=company_view_id(report_key, stripped), kind="company",
                report_key=report_key, name=stripped, owner_handle=None,
                params=canonicalize_params(params),
                layout=canonicalize_layout(layout),
                updated_by_handle=handles.get(updated_by) if updated_by else None,
                legacy_source=_SOURCE, legacy_id=legacy_id,
            )
        saved = self.get_by_name(report_key, stripped)
        if saved is None:
            raise RuntimeError(f"failed to save company view {report_key}/{stripped}")
        return saved

    def delete(self, view_id: int, report_key: str) -> bool:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT id FROM views WHERE legacy_source=? AND legacy_id=? AND report_key=?",
                (_SOURCE, view_id, report_key),
            ).fetchone()
            if row is None:
                return False
            try:
                cur = conn.execute("DELETE FROM views WHERE id=?", (row["id"],))
            except sqlite3.IntegrityError:
                return False
            return cur.rowcount > 0
