"""Durable delivery legs (precious.db). Retry only failed legs; never re-send sent/pending."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

from web.data.connection import Database
from web.scheduling import cadence as C

_SETTLED = ("sent", "pending")


def attempt_key(*, schedule_type: str, schedule_id: int, trigger: str,
                run_id: int, window: dict | None, kind: str, target: str,
                salesman: str = "") -> str:
    """Deterministic id for one email or folder leg.

    Clock runs key off schedule + Eastern day + window so a crash after Graph
    accepts cannot enqueue a second copy. Manual Send now keys off run_id so
    tapping Send now twice still sends twice.
    """
    window = window or {}
    window_from = str(window.get("start_date") or window.get("period") or "")
    window_to = str(window.get("end_date") or "")
    if trigger == "manual":
        raw = f"run:{run_id}|{kind}|{target}|{salesman}"
    else:
        day = C.eastern_date_iso()
        raw = (
            f"{schedule_type}|{schedule_id}|{day}|{window_from}|{window_to}|"
            f"{kind}|{target}|{salesman}"
        )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


@dataclass(frozen=True)
class DeliveryLeg:
    attempt_key: str
    kind: str
    target: str
    salesman_key: str
    status: str
    error: str
    row_count: int
    remote_id: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "DeliveryLeg":
        return cls(
            attempt_key=r["attempt_key"], kind=r["kind"], target=r["target"],
            salesman_key=r["salesman_key"] or "", status=r["status"],
            error=r["error"] or "", row_count=int(r["row_count"] or 0),
            remote_id=r["remote_id"] or "",
        )


class DeliveryLegRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str) -> DeliveryLeg | None:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_legs WHERE attempt_key=?", (key,)
            ).fetchone()
        return DeliveryLeg.from_row(row) if row else None

    def is_settled(self, key: str) -> bool:
        leg = self.get(key)
        return leg is not None and leg.status in _SETTLED

    def begin(self, key: str, *, run_id: int | None, kind: str, target: str,
              salesman_key: str = "") -> str:
        """Insert or reopen a failed row as pending. Returns 'send' or 'skip'."""
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT status FROM delivery_legs WHERE attempt_key=?", (key,)
            ).fetchone()
            if row and row["status"] in _SETTLED:
                return "skip"
            if row:
                conn.execute(
                    "UPDATE delivery_legs SET status='pending', error='',"
                    " updated_at=datetime('now') WHERE attempt_key=?",
                    (key,),
                )
                return "send"
            conn.execute(
                "INSERT INTO delivery_legs(run_id, attempt_key, kind, target,"
                " salesman_key, status) VALUES (?, ?, ?, ?, ?, 'pending')",
                (run_id, key, kind, target, salesman_key or ""),
            )
            return "send"

    def mark_sent(self, key: str, *, row_count: int = 0, remote_id: str = "") -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE delivery_legs SET status='sent', error='', row_count=?,"
                " remote_id=?, updated_at=datetime('now') WHERE attempt_key=?",
                (row_count, remote_id or "", key),
            )

    def mark_failed(self, key: str, error: str) -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE delivery_legs SET status='failed', error=?,"
                " updated_at=datetime('now') WHERE attempt_key=?",
                ((error or "")[:500], key),
            )
