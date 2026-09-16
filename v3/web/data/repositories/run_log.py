"""Report run-log repository (precious.db `report_run_log`).

An audit trail of report executions: who ran what, when, how long, and whether it
succeeded. Written by the report-run job handler; read by the admin run-log page.
A failed insert must never break a report run, so callers wrap `record()` in a
best-effort guard.
"""

from __future__ import annotations

from dataclasses import dataclass

from web.data.connection import Database


@dataclass(frozen=True)
class RunLogEntry:
    id: int
    user_email: str | None
    report_key: str
    status: str
    rows: int | None
    duration_ms: int | None
    source: str
    created_at: str


class ReportRunLogRepository:
    def __init__(self, db: Database):
        self.db = db

    def record(self, *, user_id: int | None, report_key: str, status: str,
               rows: int | None = None, duration_ms: int | None = None,
               source: str = "") -> int:
        with self.db.precious() as conn:
            cur = conn.execute(
                "INSERT INTO report_run_log(user_id, report_key, status, rows, duration_ms, source)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, report_key, status, rows, duration_ms, source),
            )
            return cur.lastrowid

    def recent(self, limit: int = 200) -> list[RunLogEntry]:
        """Most-recent runs first, joined to the user email for display."""
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT l.id, u.email AS email, l.report_key, l.status, l.rows,"
                "       l.duration_ms, l.source, l.created_at"
                " FROM report_run_log l LEFT JOIN users u ON u.id = l.user_id"
                " ORDER BY l.id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [
            RunLogEntry(
                id=r["id"], user_email=r["email"], report_key=r["report_key"],
                status=r["status"], rows=r["rows"], duration_ms=r["duration_ms"],
                source=r["source"], created_at=r["created_at"],
            )
            for r in rows
        ]
