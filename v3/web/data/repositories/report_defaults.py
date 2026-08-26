"""Company-wide Default view per report (layout + filters).

Personal saved views stay in ``saved_reports``. Default is shared so schedules
that use it pick up edits on the next send when they have no locked snapshot.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from web.data.connection import Database

DEFAULT_VIEW_NAME = "Default"
CUSTOM_VIEW_NAME = "Custom"
_NAME_MAX = 120


def normalize_view_name(raw: str | None) -> str:
    name = (raw or "").strip()
    if not name or name.lower() == "default":
        return DEFAULT_VIEW_NAME
    return name[:_NAME_MAX]


def layout_has_snapshot(layout: dict | None) -> bool:
    if not isinstance(layout, dict) or not layout:
        return False
    return bool(layout.get("views") or layout.get("order") or layout.get("clones"))


def resolve_send_layout(view_name: str | None, stored: dict | None,
                        company_default: dict | None) -> dict:
    """Layout to apply at send time.

    Named/Custom views use the snapshot on the schedule. Default with no
    snapshot uses the company Default. Default that already has a snapshot
    (seeded tab lists, report-page lock-in) keeps that snapshot so a Default
    edit does not rewrite those files.
    """
    stored_layout = stored if isinstance(stored, dict) else {}
    if normalize_view_name(view_name) != DEFAULT_VIEW_NAME:
        return stored_layout
    if layout_has_snapshot(stored_layout):
        return stored_layout
    return company_default if isinstance(company_default, dict) else {}


def view_and_layout_for_create(body: dict) -> tuple[str, dict]:
    incoming = body.get("layout") if isinstance(body.get("layout"), dict) else {}
    raw = body.get("view_name")
    if raw is None:
        if layout_has_snapshot(incoming):
            return CUSTOM_VIEW_NAME, incoming
        return DEFAULT_VIEW_NAME, incoming or {}
    name = normalize_view_name(raw if isinstance(raw, str) else "")
    if name == DEFAULT_VIEW_NAME:
        return DEFAULT_VIEW_NAME, {}
    return name, incoming or {}


def view_and_layout_for_update(body: dict, existing_view: str | None,
                               existing_layout: dict | None) -> tuple[str, dict]:
    existing_name = normalize_view_name(existing_view)
    existing = existing_layout if isinstance(existing_layout, dict) else {}
    incoming = body.get("layout") if isinstance(body.get("layout"), dict) else None
    if "view_name" not in body:
        if incoming:
            return existing_name, incoming
        return existing_name, existing
    name = normalize_view_name(body.get("view_name") if isinstance(body.get("view_name"), str) else "")
    if name == DEFAULT_VIEW_NAME:
        if existing_name == DEFAULT_VIEW_NAME:
            return DEFAULT_VIEW_NAME, incoming if incoming else existing
        return DEFAULT_VIEW_NAME, {}
    if incoming:
        return name, incoming
    return name, existing


@dataclass(frozen=True)
class ReportDefault:
    report_key: str
    params: dict
    layout: dict
    updated_at: str
    updated_by: int | None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "ReportDefault":
        keys = r.keys()
        updated_by = r["updated_by"] if "updated_by" in keys else None
        return cls(
            report_key=r["report_key"],
            params=json.loads(r["params_json"] or "{}"),
            layout=json.loads(r["layout_json"] or "{}"),
            updated_at=r["updated_at"],
            updated_by=int(updated_by) if updated_by is not None else None,
        )


class ReportDefaultRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, report_key: str) -> ReportDefault | None:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT * FROM report_defaults WHERE report_key=?",
                (report_key,),
            ).fetchone()
            return ReportDefault.from_row(row) if row else None

    def get_layout(self, report_key: str) -> dict:
        row = self.get(report_key)
        return dict(row.layout) if row and isinstance(row.layout, dict) else {}

    def upsert(self, report_key: str, *, params: dict, layout: dict,
               updated_by: int | None) -> ReportDefault:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        with self.db.precious() as conn:
            conn.execute(
                "INSERT INTO report_defaults(report_key, params_json, layout_json,"
                " updated_at, updated_by) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(report_key) DO UPDATE SET"
                " params_json=excluded.params_json, layout_json=excluded.layout_json,"
                " updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                (report_key, json.dumps(params or {}), json.dumps(layout or {}),
                 ts, updated_by),
            )
        saved = self.get(report_key)
        if saved is None:
            raise RuntimeError(f"failed to save Default view for {report_key}")
        return saved
