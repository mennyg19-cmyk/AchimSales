"""The durable job queue: reading and writing the jobs table."""

# === What's in this file ===
# Reports don't run inside the web request -- the web side drops a job row here
# and a worker picks it up. This module is the only code that touches the jobs
# table, so the queue rules (dedup, backpressure, atomic claim, heartbeats,
# recovery) all live in one place.
#
# QueueFull -- raised when too many jobs are already waiting (the route turns it into 503)
# Job -- a plain snapshot of one job row (params decoded from JSON)
# JobRepository.enqueue() -- add a job, reusing an identical one that's still active
# JobRepository.claim_next() -- atomically grab the next queued job (the Postgres seam)
# JobRepository.heartbeat() -- a running job says "still alive"
# JobRepository.mark_done() / mark_failed() / cancel() -- finish a job
# JobRepository.get() -- look up one job
# JobRepository.queue_depth() -- how many jobs are waiting
# JobRepository.recover_orphans() -- requeue jobs whose worker died (capped retries)

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from ..connection import Database, utc_now_iso

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

_MAX_ATTEMPTS = 2  # one original try + one recovery, then give up (BH10)


class QueueFull(Exception):
    """Too many jobs are already queued; the caller should back off and retry."""


@dataclass(frozen=True)
class Job:
    id: str
    job_type: str
    report_key: Optional[str]
    cache_key: Optional[str]
    params: dict
    status: str
    attempts: int
    requested_by: Optional[str]
    scope_token: Optional[str]
    result_ref: Optional[str]
    error: Optional[str]
    created_at: str
    claimed_at: Optional[str]
    heartbeat_at: Optional[str]
    finished_at: Optional[str]

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Job":
        return cls(
            id=row["id"],
            job_type=row["job_type"],
            report_key=row["report_key"],
            cache_key=row["cache_key"],
            params=json.loads(row["params"] or "{}"),
            status=row["status"],
            attempts=row["attempts"],
            requested_by=row["requested_by"],
            scope_token=row["scope_token"],
            result_ref=row["result_ref"],
            error=row["error"],
            created_at=row["created_at"],
            claimed_at=row["claimed_at"],
            heartbeat_at=row["heartbeat_at"],
            finished_at=row["finished_at"],
        )


class JobRepository:
    def __init__(self, db: Database, queue_max: int = 25, stale_seconds: int = 180) -> None:
        self._db = db
        self._queue_max = queue_max
        self._stale_seconds = stale_seconds

    def enqueue(
        self,
        job_type: str,
        *,
        report_key: Optional[str] = None,
        cache_key: Optional[str] = None,
        params: Optional[dict] = None,
        requested_by: Optional[str] = None,
        scope_token: Optional[str] = None,
    ) -> Job:
        """Add a job. If an identical one is still active, reuse it; if the queue
        is too deep, refuse with QueueFull so the caller can return 503."""
        params_json = json.dumps(params or {})
        with self._db.precious() as conn:
            with conn.transaction():
                if cache_key:
                    existing = conn.fetchone(
                        "SELECT * FROM jobs WHERE cache_key = ? AND status IN (?, ?) LIMIT 1",
                        (cache_key, STATUS_QUEUED, STATUS_RUNNING),
                    )
                    if existing:
                        return Job.from_row(existing)
                depth = conn.fetchone(
                    "SELECT COUNT(*) AS n FROM jobs WHERE status = ?", (STATUS_QUEUED,)
                )["n"]
                if depth >= self._queue_max:
                    raise QueueFull(f"{depth} jobs already waiting (limit {self._queue_max})")
                job_id = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO jobs (id, job_type, report_key, cache_key, params, status, "
                    "attempts, requested_by, scope_token, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
                    (
                        job_id,
                        job_type,
                        report_key,
                        cache_key,
                        params_json,
                        STATUS_QUEUED,
                        requested_by,
                        scope_token,
                        utc_now_iso(),
                    ),
                )
                row = conn.fetchone("SELECT * FROM jobs WHERE id = ?", (job_id,))
                return Job.from_row(row)

    def claim_next(self) -> Optional[Job]:
        """Atomically take the oldest queued job and mark it running.

        Postgres off-ramp seam: a Postgres version would use
        SELECT ... FOR UPDATE SKIP LOCKED. Here BEGIN IMMEDIATE plus the
        status guard makes the claim race-free across workers.
        """
        now = utc_now_iso()
        with self._db.precious() as conn:
            with conn.transaction():
                row = conn.fetchone(
                    "SELECT * FROM jobs WHERE status = ? ORDER BY created_at LIMIT 1",
                    (STATUS_QUEUED,),
                )
                if not row:
                    return None
                conn.execute(
                    "UPDATE jobs SET status = ?, claimed_at = ?, heartbeat_at = ?, "
                    "attempts = attempts + 1 WHERE id = ?",
                    (STATUS_RUNNING, now, now, row["id"]),
                )
                return Job.from_row(conn.fetchone("SELECT * FROM jobs WHERE id = ?", (row["id"],)))

    def heartbeat(self, job_id: str) -> None:
        with self._db.precious() as conn:
            conn.execute("UPDATE jobs SET heartbeat_at = ? WHERE id = ?", (utc_now_iso(), job_id))

    def mark_done(self, job_id: str, result_ref: Optional[str] = None) -> None:
        with self._db.precious() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, result_ref = ?, error = NULL, finished_at = ? WHERE id = ?",
                (STATUS_DONE, result_ref, utc_now_iso(), job_id),
            )

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._db.precious() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
                (STATUS_FAILED, error[:2000], utc_now_iso(), job_id),
            )

    def cancel(self, job_id: str) -> bool:
        """Request cancellation. A queued job stops immediately; a running job is
        flagged and the worker stops at its next cooperative checkpoint."""
        with self._db.precious() as conn:
            with conn.transaction():
                row = conn.fetchone("SELECT status FROM jobs WHERE id = ?", (job_id,))
                if not row or row["status"] not in (STATUS_QUEUED, STATUS_RUNNING):
                    return False
                conn.execute(
                    "UPDATE jobs SET status = ?, finished_at = ? WHERE id = ?",
                    (STATUS_CANCELLED, utc_now_iso(), job_id),
                )
                return True

    def is_cancelled(self, job_id: str) -> bool:
        with self._db.precious() as conn:
            row = conn.fetchone("SELECT status FROM jobs WHERE id = ?", (job_id,))
            return bool(row) and row["status"] == STATUS_CANCELLED

    def get(self, job_id: str) -> Optional[Job]:
        with self._db.precious() as conn:
            row = conn.fetchone("SELECT * FROM jobs WHERE id = ?", (job_id,))
            return Job.from_row(row) if row else None

    def queue_depth(self) -> int:
        with self._db.precious() as conn:
            return conn.fetchone(
                "SELECT COUNT(*) AS n FROM jobs WHERE status = ?", (STATUS_QUEUED,)
            )["n"]

    def latest_heartbeat(self) -> Optional[str]:
        with self._db.precious() as conn:
            row = conn.fetchone(
                "SELECT heartbeat_at FROM jobs WHERE heartbeat_at IS NOT NULL "
                "ORDER BY heartbeat_at DESC LIMIT 1"
            )
            return row["heartbeat_at"] if row else None

    def recover_orphans(self) -> int:
        """Find jobs marked running whose worker went silent and either requeue
        them (if they have a retry left) or fail them. Capped so a poison job
        can't loop forever and OOM the box (BH10)."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=self._stale_seconds)
        ).isoformat()
        recovered = 0
        with self._db.precious() as conn:
            with conn.transaction():
                stale = conn.fetchall(
                    "SELECT id, attempts FROM jobs WHERE status = ? AND "
                    "(heartbeat_at IS NULL OR heartbeat_at < ?)",
                    (STATUS_RUNNING, cutoff),
                )
                for row in stale:
                    if row["attempts"] >= _MAX_ATTEMPTS:
                        conn.execute(
                            "UPDATE jobs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
                            (
                                STATUS_FAILED,
                                "Job failed twice (worker stopped responding), not retrying.",
                                utc_now_iso(),
                                row["id"],
                            ),
                        )
                    else:
                        conn.execute(
                            "UPDATE jobs SET status = ?, claimed_at = NULL, heartbeat_at = NULL WHERE id = ?",
                            (STATUS_QUEUED, row["id"]),
                        )
                    recovered += 1
        return recovered
