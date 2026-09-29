"""Saved-report (preset) repository.

A preset is a named, per-user shortcut: filter params + grid layout on the
``views`` table (kind ``personal``). Integer ids are ``views.legacy_id`` so
existing links keep working after the JSON table is gone.
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
    next_legacy_id,
    personal_view_id,
)

_SOURCE = "saved_reports"


@dataclass(frozen=True)
class SavedReport:
    id: int
    user_id: int
    report_key: str
    name: str
    params: dict
    layout: dict
    created_at: str


def _select() -> str:
    return (
        "SELECT v.legacy_id AS id, u.id AS user_id, v.report_key, v.name,"
        " v.updated_at AS created_at, v.id AS view_id"
        " FROM views v JOIN users u ON u.handle = v.owner_handle"
        " WHERE v.kind='personal' AND v.legacy_source=?"
    )


def _one(conn: sqlite3.Connection, row: sqlite3.Row | None) -> SavedReport | None:
    if row is None:
        return None
    return SavedReport(
        id=int(row["id"]), user_id=int(row["user_id"]),
        report_key=row["report_key"], name=row["name"],
        params=assemble_params(conn, row["view_id"]),
        layout=assemble_layout(conn, row["view_id"]),
        created_at=row["created_at"] or "",
    )


def _write(conn: sqlite3.Connection, user_id: int, report_key: str, name: str,
           params: dict, layout: dict, legacy_id: int) -> None:
    handles = assign_handles(conn)
    handle = handles.get(user_id)
    if not handle:
        raise RuntimeError(f"user {user_id} has no handle")
    _upsert_view(
        conn, view_id=personal_view_id(handle, report_key, name),
        kind="personal", report_key=report_key, name=name, owner_handle=handle,
        params=canonicalize_params(params), layout=canonicalize_layout(layout),
        updated_by_handle=handle, legacy_source=_SOURCE, legacy_id=legacy_id,
    )


class SavedReportRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, user_id: int, report_key: str, name: str,
               params: dict, layout: dict) -> int:
        """Create or overwrite (by name) a preset; returns its id."""
        name = name.strip()
        with self.db.precious() as conn:
            existing = conn.execute(
                _select() + " AND u.id=? AND v.report_key=? AND v.name=?",
                (_SOURCE, user_id, report_key, name),
            ).fetchone()
            legacy_id = int(existing["id"]) if existing else next_legacy_id(conn, _SOURCE)
            _write(conn, user_id, report_key, name, params, layout, legacy_id)
            return legacy_id

    def list_for_user(self, user_id: int) -> list[SavedReport]:
        with self.db.precious() as conn:
            rows = conn.execute(
                _select() + " AND u.id=? ORDER BY v.report_key, v.name",
                (_SOURCE, user_id),
            ).fetchall()
            return [s for r in rows if (s := _one(conn, r))]

    def list_all(self) -> list[SavedReport]:
        with self.db.precious() as conn:
            rows = conn.execute(
                _select() + " ORDER BY u.id, v.report_key, v.name",
                (_SOURCE,),
            ).fetchall()
            return [s for r in rows if (s := _one(conn, r))]

    def get_any(self, preset_id: int) -> SavedReport | None:
        with self.db.precious() as conn:
            row = conn.execute(
                _select() + " AND v.legacy_id=?", (_SOURCE, preset_id),
            ).fetchone()
            return _one(conn, row)

    def get_by_name(self, user_id: int, report_key: str, name: str) -> SavedReport | None:
        with self.db.precious() as conn:
            row = conn.execute(
                _select() + " AND u.id=? AND v.report_key=? AND v.name=?",
                (_SOURCE, user_id, report_key, name.strip()),
            ).fetchone()
            return _one(conn, row)

    def get(self, preset_id: int, user_id: int) -> SavedReport | None:
        with self.db.precious() as conn:
            row = conn.execute(
                _select() + " AND v.legacy_id=? AND u.id=?",
                (_SOURCE, preset_id, user_id),
            ).fetchone()
            return _one(conn, row)

    def update(self, preset_id: int, user_id: int, *, name: str | None = None,
               params: dict | None = None, layout: dict | None = None) -> bool:
        """Rename and/or replace filters/layout. Owner-scoped."""
        with self.db.precious() as conn:
            row = conn.execute(
                _select() + " AND v.legacy_id=? AND u.id=?",
                (_SOURCE, preset_id, user_id),
            ).fetchone()
            current = _one(conn, row)
            if current is None:
                return False
            new_name = current.name if name is None else name.strip()
            if not new_name:
                return False
            try:
                _write(
                    conn, user_id, current.report_key, new_name,
                    current.params if params is None else params,
                    current.layout if layout is None else layout,
                    preset_id,
                )
            except sqlite3.IntegrityError:
                return False
            return True

    def delete(self, preset_id: int, user_id: int) -> bool:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT v.id FROM views v JOIN users u ON u.handle = v.owner_handle"
                " WHERE v.legacy_source=? AND v.legacy_id=? AND u.id=?",
                (_SOURCE, preset_id, user_id),
            ).fetchone()
            if row is None:
                return False
            try:
                cur = conn.execute("DELETE FROM views WHERE id=?", (row["id"],))
            except sqlite3.IntegrityError:
                return False
            return cur.rowcount == 1
