"""Reading and writing the report definitions (config, filters, columns, tabs)."""

# === What's in this file ===
# A report is defined by data, not code: which stored procedure feeds it, which
# columns it has, which filters it offers, and which tabs to build. This module
# is the only code that reads/writes those four tables. The seed script writes
# them; the config loader reads them at run time. JSON columns are decoded here
# so the rest of the app never sees raw JSON text.
#
# ReportConfigRepository.get_config() -- the report row (or None)
# ReportConfigRepository.list_active() -- reports a user can run
# ReportConfigRepository.get_filters/get_columns/get_tabs() -- the decoded pieces
# ReportConfigRepository.upsert_config() + set_filters/set_columns/set_tabs() --
#   used by the seed; replace-all so re-seeding is idempotent

from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from ..connection import Database, utc_now_iso

STATUS_ACTIVE = "active"


def _row_to_dict(row: Mapping[str, Any]) -> dict:
    return dict(row)


class ReportConfigRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get_config(self, report_key: str) -> Optional[dict]:
        with self._db.precious() as conn:
            row = conn.fetchone(
                "SELECT * FROM report_configs WHERE report_key = ?", (report_key,)
            )
            if not row:
                return None
            data = _row_to_dict(row)
            data["default_params"] = json.loads(data.get("default_params") or "{}")
            return data

    def list_active(self) -> list[dict]:
        with self._db.precious() as conn:
            rows = conn.fetchall(
                "SELECT * FROM report_configs WHERE status = ? ORDER BY title", (STATUS_ACTIVE,)
            )
            return [_row_to_dict(r) for r in rows]

    def get_filters(self, report_key: str) -> list[dict]:
        with self._db.precious() as conn:
            rows = conn.fetchall(
                "SELECT * FROM report_filters WHERE report_key = ? ORDER BY sort_order, id",
                (report_key,),
            )
            out = []
            for r in rows:
                d = _row_to_dict(r)
                d["options"] = json.loads(d.get("options") or "[]")
                out.append(d)
            return out

    def get_columns(self, report_key: str) -> list[dict]:
        with self._db.precious() as conn:
            rows = conn.fetchall(
                "SELECT * FROM report_columns WHERE report_key = ? ORDER BY sort_order, id",
                (report_key,),
            )
            return [_row_to_dict(r) for r in rows]

    def get_tabs(self, report_key: str) -> list[dict]:
        with self._db.precious() as conn:
            rows = conn.fetchall(
                "SELECT * FROM report_tabs WHERE report_key = ? ORDER BY sort_order, id",
                (report_key,),
            )
            out = []
            for r in rows:
                d = _row_to_dict(r)
                for json_field in ("group_by", "aggregations", "column_keys", "sorters"):
                    d[json_field] = json.loads(d.get(json_field) or ("{}" if json_field == "aggregations" else "[]"))
                out.append(d)
            return out

    def upsert_config(
        self,
        report_key: str,
        *,
        title: str,
        sp_name: str,
        status: str = STATUS_ACTIVE,
        default_params: Optional[dict] = None,
    ) -> None:
        now = utc_now_iso()
        with self._db.precious() as conn:
            conn.execute(
                "INSERT INTO report_configs (report_key, title, status, sp_name, default_params, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(report_key) DO UPDATE SET title=excluded.title, status=excluded.status, "
                "sp_name=excluded.sp_name, default_params=excluded.default_params, updated_at=excluded.updated_at",
                (report_key, title, status, sp_name, json.dumps(default_params or {}), now, now),
            )

    def set_filters(self, report_key: str, filters: list[dict]) -> None:
        with self._db.precious() as conn:
            with conn.transaction():
                conn.execute("DELETE FROM report_filters WHERE report_key = ?", (report_key,))
                for i, f in enumerate(filters):
                    conn.execute(
                        "INSERT INTO report_filters (report_key, filter_key, label, kind, default_value, options, sort_order) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            report_key,
                            f["filter_key"],
                            f["label"],
                            f["kind"],
                            f.get("default_value"),
                            json.dumps(f.get("options", [])),
                            f.get("sort_order", i),
                        ),
                    )

    def set_columns(self, report_key: str, columns: list[dict]) -> None:
        with self._db.precious() as conn:
            with conn.transaction():
                conn.execute("DELETE FROM report_columns WHERE report_key = ?", (report_key,))
                for i, c in enumerate(columns):
                    conn.execute(
                        "INSERT INTO report_columns (report_key, column_key, label, data_type, format, sort_order, default_hidden) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            report_key,
                            c["column_key"],
                            c["label"],
                            c.get("data_type", "text"),
                            c.get("format"),
                            c.get("sort_order", i),
                            1 if c.get("default_hidden") else 0,
                        ),
                    )

    def set_tabs(self, report_key: str, tabs: list[dict]) -> None:
        with self._db.precious() as conn:
            with conn.transaction():
                conn.execute("DELETE FROM report_tabs WHERE report_key = ?", (report_key,))
                for i, t in enumerate(tabs):
                    conn.execute(
                        "INSERT INTO report_tabs (report_key, tab_key, label, sort_order, filter_expr, "
                        "group_by, aggregations, column_keys, sorters, transform, layout, condition) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            report_key,
                            t["tab_key"],
                            t["label"],
                            t.get("sort_order", i),
                            t.get("filter_expr"),
                            json.dumps(t.get("group_by", [])),
                            json.dumps(t.get("aggregations", {})),
                            json.dumps(t.get("column_keys", [])),
                            json.dumps(t.get("sorters", [])),
                            t.get("transform"),
                            t.get("layout"),
                            t.get("condition"),
                        ),
                    )
