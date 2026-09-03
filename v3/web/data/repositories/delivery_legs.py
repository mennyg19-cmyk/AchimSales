"""Durable state for individual outbound email and folder delivery attempts."""
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
        return cls(
            id=row["id"],
            job_id=row["job_id"],
            run_id=row["run_id"],
            slot_id=row["slot_id"],
            kind=row["kind"],
            status=row["status"],
            error=row["error"],
        )


_LEG_COLUMNS = "id, job_id, run_id, slot_id, kind, status, error"


class DeliveryLegRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, *, job_id: str | None, run_id: int | None, slot_id: str, kind: str) -> int:
        with self.db.precious() as conn:
            cur = conn.execute(
                "INSERT INTO delivery_legs(job_id, run_id, slot_id, kind, status)"
                " VALUES (?, ?, ?, ?, 'prepared')",
                (job_id, run_id, slot_id, kind),
            )
            return cur.lastrowid

    def update(self, leg_id: int, *, status: str, error: str = "") -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE delivery_legs SET status=?, error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, error, leg_id),
            )

    def get_by_job(self, job_id: str) -> list[DeliveryLeg]:
        return self._fetch_legs(
            "SELECT " + _LEG_COLUMNS + " FROM delivery_legs WHERE job_id=? ORDER BY id",
            (job_id,),
        )

    def list_recent(self, *, limit: int = 20) -> list[DeliveryLeg]:
        return self._fetch_legs(
            "SELECT " + _LEG_COLUMNS + " FROM delivery_legs ORDER BY id DESC LIMIT ?",
            (limit,),
        )

    def _fetch_legs(self, sql: str, params: tuple) -> list[DeliveryLeg]:
        with self.db.precious() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [DeliveryLeg.from_row(row) for row in rows]

    def prune(self, *, older_than_days: int = 90) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        with self.db.precious() as conn:
            return conn.execute(
                "DELETE FROM delivery_legs WHERE julianday(created_at) < julianday(?)",
                (cutoff,),
            ).rowcount
