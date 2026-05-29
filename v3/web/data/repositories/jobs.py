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
    params: dict
    result_ref: str
    error: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Job":
        return cls(
            id=r["id"], type=r["type"], status=r["status"],
            owner_user_id=r["owner_user_id"], dedup_key=r["dedup_key"],
            progress=r["progress"], params=json.loads(r["params_json"] or "{}"),
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
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE jobs SET status='success', progress=100, result_ref=?, finished_at=? WHERE id=?",
                (result_ref, _now(), job_id),
            )

    def mark_failure(self, job_id: str, error: str) -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE jobs SET status='failure', error=?, finished_at=? WHERE id=?",
                (error, _now(), job_id),
            )

    def cancel(self, job_id: str) -> bool:
        with self.db.precious() as conn:
            updated = conn.execute(
                "UPDATE jobs SET status='cancelled', finished_at=? WHERE id=? AND status IN (?, ?)",
                (_now(), job_id, *_ACTIVE),
            )
            return updated.rowcount == 1

    def list_for_user(self, user_id: int, limit: int = 50) -> list[Job]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE owner_user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [Job.from_row(r) for r in rows]
