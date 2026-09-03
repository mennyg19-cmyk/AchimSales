"""Durable state for individual outbound email delivery attempts."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from web.data.connection import Database


@dataclass(frozen=True)
class DeliveryLeg:
    id: int
    job_id: str | None
    run_id: int | None
    slot_id: str
    kind: str
    status: str
    error: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DeliveryLeg":
        return cls(**{key: row[key] for key in cls.__dataclass_fields__})


class DeliveryLegRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, *, job_id: str | None, run_id: int | None, slot_id: str) -> int:
        with self.db.precious() as conn:
            cur = conn.execute(
                "INSERT INTO delivery_legs(job_id, run_id, slot_id, kind, status)"
                " VALUES (?, ?, ?, 'email', 'prepared')",
                (job_id, run_id, slot_id),
            )
            return cur.lastrowid

    def update(self, leg_id: int, *, status: str, error: str = "") -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE delivery_legs SET status=?, error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, error, leg_id),
            )

    def get_by_job(self, job_id: str) -> list[DeliveryLeg]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT id, job_id, run_id, slot_id, kind, status, error"
                " FROM delivery_legs WHERE job_id=? ORDER BY id",
                (job_id,),
            ).fetchall()
        return [DeliveryLeg.from_row(row) for row in rows]

    def prune(self, *, older_than_days: int = 90) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        with self.db.precious() as conn:
            return conn.execute(
                "DELETE FROM delivery_legs WHERE julianday(created_at) < julianday(?)",
                (cutoff,),
            ).rowcount
