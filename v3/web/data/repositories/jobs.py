"""Durable job repository (precious.db `jobs` table).

The job table is the source of truth for job state/progress/result so jobs
survive B1 restarts and dedup works across restarts (plan section 10). Dedup is
enforced at the DB level by a partial unique index on dedup_key for active jobs;
enqueue() races safely.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from web.data.connection import Database

_ACTIVE = ("queued", "running")

# How many times crash-recovery will requeue a job before giving up on it. A job
# that keeps dying mid-run (an out-of-memory report the OS SIGKILLs never gets to
# mark itself failed, so it stays 'running' and gets requeued on every restart)
# would otherwise loop forever and keep crashing the whole app. After this many
# automatic retries we fail the job instead of requeuing it again. One retry
# covers a benign restart-mid-run while still stopping a genuine crash loop fast.
_MAX_RECOVERY_RETRIES = 1
_RETRY_EXHAUSTED_ERROR = (
    "Stopped after the run kept crashing its worker - it most likely ran out of "
    "memory. Try a smaller date range or fewer customers, or export instead of "
    "viewing on screen."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Job:
    id: str
    type: str
    status: str
    owner_user_id: int | None
    dedup_key: str | None
    progress: int
    attempts: int
    params: dict
    result_ref: str
    error: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Job":
        return cls(
            id=r["id"], type=r["type"], status=r["status"],
            owner_user_id=r["owner_user_id"], dedup_key=r["dedup_key"],
            progress=r["progress"], attempts=r["attempts"],
            params=json.loads(r["params_json"] or "{}"),
            result_ref=r["result_ref"], error=r["error"],
        )


class JobRepository:
    def __init__(self, db: Database):
        self.db = db

    def enqueue(self, job_type: str, *, owner_user_id: int | None = None,
                dedup_key: str | None = None, params: dict[str, Any] | None = None) -> str:
        """Create a job, or return the existing active job id for the same dedup_key."""
        job_id = uuid.uuid4().hex
        with self.db.precious() as conn:
            if dedup_key:
                existing = conn.execute(
                    "SELECT id FROM jobs WHERE dedup_key = ? AND status IN (?, ?)",
                    (dedup_key, *_ACTIVE),
                ).fetchone()
                if existing:
                    return existing["id"]
            try:
                conn.execute(
                    "INSERT INTO jobs(id, type, status, owner_user_id, dedup_key, params_json)"
                    " VALUES (?, ?, 'queued', ?, ?, ?)",
                    (job_id, job_type, owner_user_id, dedup_key, json.dumps(params or {})),
                )
            except sqlite3.IntegrityError:
                # Lost a race against a concurrent enqueue with the same dedup_key.
                row = conn.execute(
                    "SELECT id FROM jobs WHERE dedup_key = ? AND status IN (?, ?)",
                    (dedup_key, *_ACTIVE),
                ).fetchone()
                if row:
                    return row["id"]
                raise
        return job_id

    def get(self, job_id: str) -> Job | None:
        with self.db.precious() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return Job.from_row(row) if row else None

    def claim_next(self) -> Job | None:
        """Atomically move the oldest queued job to running and return it."""
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            updated = conn.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE id=? AND status='queued'",
                (_now(), row["id"]),
            )
            if updated.rowcount != 1:
                return None  # another worker claimed it
            return Job.from_row(conn.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def set_progress(self, job_id: str, progress: int) -> None:
        with self.db.precious() as conn:
            conn.execute("UPDATE jobs SET progress=? WHERE id=?", (max(0, min(100, progress)), job_id))

    def mark_success(self, job_id: str, result_ref: str = "") -> None:
        # Guarded to 'running': never resurrect a terminal (e.g. cancelled) job.
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE jobs SET status='success', progress=100, result_ref=?, finished_at=?"
                " WHERE id=? AND status='running'",
                (result_ref, _now(), job_id),
            )

    def mark_failure(self, job_id: str, error: str) -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE jobs SET status='failure', error=?, finished_at=?"
                " WHERE id=? AND status='running'",
                (error, _now(), job_id),
            )

    def cancel(self, job_id: str) -> bool:
        """Cancel a queued OR running job. Returns True if it was active to cancel.

        A queued job never starts. A running job can't be yanked out of its
        upstream call mid-flight (e.g. a slow Reporting API request that hasn't
        returned yet), so that worker thread keeps going until the call ends -
        but marking the row 'cancelled' lets the screen stop waiting on it right
        away, and `mark_success`/`mark_failure` are guarded to 'running' so when
        the call finally finishes it can't overwrite the cancellation.
        """
        with self.db.precious() as conn:
            updated = conn.execute(
                "UPDATE jobs SET status='cancelled', finished_at=?"
                " WHERE id=? AND status IN (?, ?)",
                (_now(), job_id, *_ACTIVE),
            )
            return updated.rowcount == 1

    def recover_orphans(self, running_older_than_seconds: float | None = None,
                        max_retries: int = _MAX_RECOVERY_RETRIES) -> int:
        """Requeue 'running' jobs (orphaned by a crash) so work survives restarts,
        but only up to `max_retries` times.

        Called at worker startup (single instance => nothing is truly running when
        we boot) and usable as a periodic stale-job reaper. A job that has already
        used up its retries is marked 'failure' instead of being requeued again,
        so a run that keeps killing its process (e.g. an OOM report) can never
        loop forever and take the site down with it. Returns the count requeued
        (not the ones failed). Clears the dedup block an orphaned row would hold.
        """
        where = "status='running'"
        cutoff_params: tuple = ()
        if running_older_than_seconds is not None:
            cutoff = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() - running_older_than_seconds,
                tz=timezone.utc,
            ).isoformat()
            where += " AND (started_at IS NULL OR started_at < ?)"
            cutoff_params = (cutoff,)
        with self.db.precious() as conn:
            # Jobs that already exhausted their retries: fail them so they stop
            # being requeued (and crashing) on every restart.
            conn.execute(
                f"UPDATE jobs SET status='failure', error=?, finished_at=?"
                f" WHERE {where} AND attempts >= ?",
                (_RETRY_EXHAUSTED_ERROR, _now(), *cutoff_params, max_retries),
            )
            # The rest: requeue and count this attempt.
            cur = conn.execute(
                f"UPDATE jobs SET status='queued', started_at=NULL, progress=0,"
                f" attempts=attempts+1 WHERE {where}",
                cutoff_params,
            )
            return cur.rowcount

    def status_summary(self, active_limit: int = 20) -> dict:
        """Counts of jobs by status plus the currently active (queued/running)
        jobs with their age. Lets the admin diagnostic tell a worker stuck behind
        a hung run (jobs piling up 'queued') apart from a job that ran and called
        out. Ages are seconds since the row was created."""
        # created_at is naive UTC (SQLite CURRENT_TIMESTAMP); compare in naive UTC.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self.db.precious() as conn:
            by_status = {r["status"]: r["n"] for r in conn.execute(
                "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()}
            rows = conn.execute(
                "SELECT id, type, status, created_at, started_at FROM jobs"
                " WHERE status IN (?, ?) ORDER BY created_at LIMIT ?",
                (*_ACTIVE, active_limit),
            ).fetchall()
        active = []
        for r in rows:
            age = None
            if r["created_at"]:
                try:
                    created = datetime.fromisoformat(r["created_at"])
                    if created.tzinfo is not None:
                        created = created.astimezone(timezone.utc).replace(tzinfo=None)
                    age = int((now - created).total_seconds())
                except ValueError:
                    age = None
            active.append({"id": r["id"], "type": r["type"], "status": r["status"],
                           "age_seconds": age})
        return {"by_status": by_status, "active": active, "active_count": len(active)}

    def list_for_user(self, user_id: int, limit: int = 50) -> list[Job]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE owner_user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [Job.from_row(r) for r in rows]
