"""Company-wide Default view per report (layout + filters).

Stored on ``views`` (kind ``default``) plus the layout tables. Schedules that
use Default pick up the next edit. There is no JSON copy.
"""

from __future__ import annotations

from dataclasses import dataclass

from web.data.connection import Database
from web.data.normalized_views import (
    _legacy_int,
    _upsert_view,
    assemble_layout,
    assemble_params,
    assign_handles,
    canonicalize_layout,
    canonicalize_params,
    default_view_id,
)

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
                        company_default: dict | None,
                        company_named: dict | None = None) -> dict:
    """Layout to apply at send time — assembled live views only.

    ``stored`` (schedule layout_json snapshot) is ignored. Named views use the
    live assembled layout when present; otherwise company Default. Default
    always uses the live company Default, never a frozen schedule copy.
    """
    del stored  # schedule layout_json is garbage for live sends
    named = company_named if isinstance(company_named, dict) else {}
    default = company_default if isinstance(company_default, dict) else {}
    if normalize_view_name(view_name) != DEFAULT_VIEW_NAME:
        if layout_has_snapshot(named):
            return named
        return default
    return default

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


class ReportDefaultRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, report_key: str) -> ReportDefault | None:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT * FROM views WHERE kind='default' AND report_key=?",
                (report_key,),
            ).fetchone()
            if row is None:
                return None
            updated_by = None
            if row["updated_by_handle"]:
                user = conn.execute(
                    "SELECT id FROM users WHERE handle=?",
                    (row["updated_by_handle"],),
                ).fetchone()
                updated_by = int(user["id"]) if user else None
            return ReportDefault(
                report_key=row["report_key"],
                params=assemble_params(conn, row["id"]),
                layout=assemble_layout(conn, row["id"]),
                updated_at=row["updated_at"],
                updated_by=updated_by,
            )

    def get_layout(self, report_key: str) -> dict:
        row = self.get(report_key)
        return dict(row.layout) if row and isinstance(row.layout, dict) else {}

    def upsert(self, report_key: str, *, params: dict, layout: dict,
               updated_by: int | None) -> ReportDefault:
        from datetime import datetime, timezone

        with self.db.precious() as conn:
            handles = assign_handles(conn)
            _upsert_view(
                conn, view_id=default_view_id(report_key), kind="default",
                report_key=report_key, name=DEFAULT_VIEW_NAME, owner_handle=None,
                params=canonicalize_params(params),
                layout=canonicalize_layout(layout),
                updated_by_handle=handles.get(updated_by) if updated_by else None,
                legacy_source="report_defaults",
                legacy_id=_legacy_int(report_key),
            )
        saved = self.get(report_key)
        if saved is None:
            raise RuntimeError(f"failed to save Default view for {report_key}")
        return saved
