"""The incident-proof audit log of report runs, exports, and deliveries."""

# === What's in this file ===
# A permanent record of what actually happened, written by the job handlers (the
# job is the source of truth, not the web request). When someone asks "did my
# report run and how long did it take", this table answers it.
#
# RunLogRepository.record() -- write one audit entry
# RunLogRepository.recent() -- read the latest entries (admin/debug view)

from __future__ import annotations

from typing import Optional

from ..connection import Database, utc_now_iso


class RunLogRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def record(
        self,
        action: str,
        *,
        user_email: Optional[str] = None,
        report_key: Optional[str] = None,
        job_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        status: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        with self._db.precious() as conn:
            conn.execute(
                "INSERT INTO audit_run_log (ts, user_email, report_key, job_id, action, duration_ms, status, message) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (utc_now_iso(), user_email, report_key, job_id, action, duration_ms, status, message),
            )

    def recent(self, limit: int = 100) -> list[dict]:
        with self._db.precious() as conn:
            rows = conn.fetchall(
                "SELECT * FROM audit_run_log ORDER BY ts DESC LIMIT ?", (int(limit),)
            )
            return [dict(r) for r in rows]
