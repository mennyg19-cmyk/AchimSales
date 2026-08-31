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
from web.jobs.limits import (
    ADMISSION_EXEMPT_TYPES,
    MAX_QUEUE_AGE_SECONDS,
    MAX_QUEUED_JOBS,
    PRIORITY_SQL,
    UNSAFE_RECOVERY_TYPES,
)

_ACTIVE = ("queued", "running")


class QueueAdmissionError(Exception):
    """Interactive enqueue refused because the durable queue is backed up."""

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
_UNSAFE_ORPHAN_ERROR = (
    "Worker died while this delivery was running; not retried."
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
    kept_until: str | None = None
    keep_name: str = ""

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Job":
        keys = r.keys()
        return cls(
            id=r["id"], type=r["type"], status=r["status"],
            owner_user_id=r["owner_user_id"], dedup_key=r["dedup_key"],
            progress=r["progress"], attempts=r["attempts"],
            params=json.loads(r["params_json"] or "{}"),
            result_ref=r["result_ref"], error=r["error"],
            kept_until=r["kept_until"] if "kept_until" in keys else None,
            keep_name=(r["keep_name"] if "keep_name" in keys else "") or "",
        )


class JobRepository:
    def __init__(self, db: Database):
        self.db = db

    def enqueue(self, job_type: str, *, owner_user_id: int | None = None,
                dedup_key: str | None = None, params: dict[str, Any] | None = None) -> str:
        """Create a job, or return the existing active job id for the same dedup_key."""
        if dedup_key:
            with self.db.precious() as conn:
                existing = conn.execute(
                    "SELECT id FROM jobs WHERE dedup_key = ? AND status IN (?, ?)",
                    (dedup_key, *_ACTIVE),
                ).fetchone()
                if existing:
                    return existing["id"]
        if job_type not in ADMISSION_EXEMPT_TYPES:
            self._assert_admission()
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

    def _assert_admission(self) -> None:
        """Refuse interactive work when the queue is already too deep or too old.

        Clock `schedule.run` (and worker-owned mirror refreshes) skip this so
        exports cannot starve deliveries.
        """
        with self.db.precious() as conn:
            queued = conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE status='queued'"
            ).fetchone()["n"]
            oldest = conn.execute(
                "SELECT MIN(created_at) AS t FROM jobs WHERE status='queued'"
            ).fetchone()["t"]
        if queued >= MAX_QUEUED_JOBS:
            raise QueueAdmissionError(
                "The report queue is busy. Try again in a few minutes."
            )
        if queued and oldest:
            try:
                created = datetime.fromisoformat(str(oldest))
            except ValueError:
                created = None
            if created is not None:
                if created.tzinfo is not None:
                    created = created.astimezone(timezone.utc).replace(tzinfo=None)
                age = (datetime.now(timezone.utc).replace(tzinfo=None) - created).total_seconds()
                if age > MAX_QUEUE_AGE_SECONDS:
                    raise QueueAdmissionError(
                        "The report queue is backed up. Try again in a few minutes."
                    )

    def get(self, job_id: str) -> Job | None:
        with self.db.precious() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return Job.from_row(row) if row else None

    def claim_next(self) -> Job | None:
        """Atomically move the next queued job to running.

        Scheduled deliveries win over interactive exports so a busy viewer
        cannot starve the clock.
        """
        with self.db.precious() as conn:
            row = conn.execute(
                f"SELECT * FROM jobs WHERE status = 'queued' "
                f"ORDER BY {PRIORITY_SQL}, created_at LIMIT 1"
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

    def cancel(self, job_id: str, *, error: str = "") -> bool:
        """Cancel a queued OR running job. Returns True if it was active to cancel.

        A queued job never starts. A running job's child is killed by the
        worker on timeout; this row update is what the UI sees. mark_success
        / mark_failure are guarded to 'running' so a late child cannot
        overwrite the cancellation.
        """
        with self.db.precious() as conn:
            if error:
                updated = conn.execute(
                    "UPDATE jobs SET status='cancelled', error=?, finished_at=?"
                    " WHERE id=? AND status IN (?, ?)",
                    (error, _now(), job_id, *_ACTIVE),
                )
            else:
                updated = conn.execute(
                    "UPDATE jobs SET status='cancelled', finished_at=?"
                    " WHERE id=? AND status IN (?, ?)",
                    (_now(), job_id, *_ACTIVE),
                )
            return updated.rowcount == 1

    def recover_orphans(self, running_older_than_seconds: float | None = None,
                        max_retries: int = _MAX_RECOVERY_RETRIES) -> int:
        """Requeue safe 'running' jobs orphaned by a crash; cancel side-effect jobs.

        Called at worker startup (single instance => the previous worker is gone)
        and usable as a periodic stale-job reaper. Report/export/mirror work is
        requeued up to `max_retries` times. `schedule.run` and `report.deliver`
        are cancelled even at the retry cap so a restart cannot send the same
        mail twice. A safe job that already used up its retries is marked
        'failure' instead of requeued. Returns the count requeued (not cancelled
        or failed). mark_success is guarded to 'running', so a surviving child
        cannot resurrect a cancelled delivery.
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
        unsafe = tuple(sorted(UNSAFE_RECOVERY_TYPES))
        in_sql = ",".join("?" * len(unsafe))
        with self.db.precious() as conn:
            # Side-effect jobs first: never requeue, never the report OOM failure.
            conn.execute(
                f"UPDATE jobs SET status='cancelled', error=?, finished_at=?"
                f" WHERE {where} AND type IN ({in_sql})",
                (_UNSAFE_ORPHAN_ERROR, _now(), *cutoff_params, *unsafe),
            )
            # Safe jobs that already exhausted retries: fail so they stop looping.
            conn.execute(
                f"UPDATE jobs SET status='failure', error=?, finished_at=?"
                f" WHERE {where} AND attempts >= ? AND type NOT IN ({in_sql})",
                (_RETRY_EXHAUSTED_ERROR, _now(), *cutoff_params, max_retries, *unsafe),
            )
            cur = conn.execute(
                f"UPDATE jobs SET status='queued', started_at=NULL, progress=0,"
                f" attempts=attempts+1 WHERE {where} AND type NOT IN ({in_sql})",
                (*cutoff_params, *unsafe),
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

    def report_runs_for_user(self, user_id: int, limit: int = 30) -> list[dict]:
        """Recent report.run jobs for one user, newest first, with the timestamps
        the status bar needs. Powers the always-on "where are my reports up to"
        bar and the resume-on-return behaviour."""
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT id, status, progress, params_json, created_at, finished_at,"
                " kept_until, keep_name"
                " FROM jobs WHERE owner_user_id = ? AND type = 'report.run'"
                " ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def keep_run(self, job_id: str, owner_user_id: int, *, kept_until: str,
                 name: str = "", cap: int = 5, payload_json: str | None = None) -> bool:
        """Mark a finished run as Kept until kept_until. Copies the payload into
        precious when given so recycle/cache prune cannot drop a Kept run."""
        label = (name or "").strip()[:80]
        with self.db.precious() as conn:
            cur = conn.execute(
                "UPDATE jobs SET kept_until=?, keep_name=? WHERE id=? AND owner_user_id=?"
                " AND type='report.run' AND status='success'",
                (kept_until, label, job_id, owner_user_id),
            )
            if cur.rowcount != 1:
                return False
            if payload_json:
                conn.execute(
                    "INSERT INTO kept_run_payloads(job_id, payload_json, copied_at)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(job_id) DO UPDATE SET"
                    "   payload_json=excluded.payload_json, copied_at=excluded.copied_at",
                    (job_id, payload_json, _now()),
                )
            rows = conn.execute(
                "SELECT id FROM jobs WHERE owner_user_id=? AND type='report.run'"
                " AND kept_until IS NOT NULL AND kept_until != ''"
                " ORDER BY kept_until DESC, finished_at DESC",
                (owner_user_id,),
            ).fetchall()
            if len(rows) > cap:
                drop_ids = [r["id"] for r in rows[cap:]]
                conn.executemany(
                    "UPDATE jobs SET kept_until=NULL, keep_name='' WHERE id=?",
                    [(i,) for i in drop_ids],
                )
                conn.executemany(
                    "DELETE FROM kept_run_payloads WHERE job_id=?",
                    [(i,) for i in drop_ids],
                )
            return True

    def get_kept_payload(self, job_id: str) -> dict | None:
        """Payload copied at Keep this run, or None if never kept / already dropped."""
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT payload_json FROM kept_run_payloads WHERE job_id=?",
                (job_id,),
            ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def has_kept_payload(self, job_id: str) -> bool:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT 1 FROM kept_run_payloads WHERE job_id=? LIMIT 1",
                (job_id,),
            ).fetchone()
        return row is not None

    def fail_hung(self, older_than_seconds: float, *,
                  error: str = "Timed out (hung job cap)") -> int:
        """Cancel long-running jobs the child killer missed. Does not requeue
        (that would double-send). mark_success is guarded to status='running'."""
        cutoff = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() - older_than_seconds,
            tz=timezone.utc,
        ).isoformat()
        with self.db.precious() as conn:
            cur = conn.execute(
                "UPDATE jobs SET status='cancelled', error=?, finished_at=?"
                " WHERE status='running' AND started_at IS NOT NULL AND started_at < ?",
                (error, _now(), cutoff),
            )
            return cur.rowcount
