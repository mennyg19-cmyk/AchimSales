"""Durable delivery legs (precious.db). Auto-retry only failed/prepared legs."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

from web.data.connection import Database
from web.delivery.states import (
    ACCEPTED,
    EMAIL_KINDS,
    FAILED,
    FOLDER_KINDS,
    LEG_RETENTION_DAYS,
    PREPARED,
    SENDING,
    SENT,
    SETTLED,
    UNKNOWN,
)


def attempt_key(*, slot_id: str, kind: str, target: str, salesman: str = "",
                window: dict | None = None) -> str:
    """Deterministic id for one email, notice, or folder leg.

    `slot_id` is frozen at enqueue (clock Eastern day + schedule, or a manual
    uuid). Window dates distinguish catch-up vs regular in the same job. The
    attempt day is never read from the clock here.
    """
    window = window or {}
    window_from = str(window.get("start_date") or window.get("period") or "")
    window_to = str(window.get("end_date") or "")
    raw = f"{slot_id}|{window_from}|{window_to}|{kind}|{target}|{salesman}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def scheduled_slot_id(*, schedule_type: str, schedule_id: int, slot_day: str,
                      catch_up_for_date: str = "", include_regular: bool = True) -> str:
    cu = catch_up_for_date or "-"
    return f"{schedule_type}:{schedule_id}:{slot_day}:cu={cu}:reg={int(include_regular)}"


def parse_scheduled_slot_id(slot_id: str) -> dict | None:
    """Clock slot_id → enqueue fields. Manual uuids return None."""
    parts = (slot_id or "").split(":")
    if len(parts) != 5:
        return None
    kind, sid, day, cu_part, reg_part = parts
    if kind not in ("master", "personal"):
        return None
    if not cu_part.startswith("cu=") or not reg_part.startswith("reg="):
        return None
    try:
        schedule_id = int(sid)
    except ValueError:
        return None
    cu = cu_part[3:]
    return {
        "schedule_type": kind,
        "schedule_id": schedule_id,
        "slot_day": day,
        "catch_up_for_date": "" if cu in ("", "-") else cu,
        "include_regular": reg_part[4:] != "0",
    }


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
    slot_id: str
    job_id: str
    upload_session_url: str
    run_id: int | None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "DeliveryLeg":
        keys = r.keys()
        return cls(
            attempt_key=r["attempt_key"], kind=r["kind"], target=r["target"],
            salesman_key=r["salesman_key"] or "", status=r["status"],
            error=r["error"] or "", row_count=int(r["row_count"] or 0),
            remote_id=r["remote_id"] or "",
            slot_id=(r["slot_id"] if "slot_id" in keys else "") or "",
            job_id=(r["job_id"] if "job_id" in keys else "") or "",
            upload_session_url=(
                r["upload_session_url"] if "upload_session_url" in keys else ""
            ) or "",
            run_id=r["run_id"] if "run_id" in keys else None,
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
        return leg is not None and leg.status in SETTLED

    def list_for_run(self, run_id: int) -> list[DeliveryLeg]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM delivery_legs WHERE run_id=? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [DeliveryLeg.from_row(r) for r in rows]

    def list_for_job(self, job_id: str) -> list[DeliveryLeg]:
        if not job_id:
            return []
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM delivery_legs WHERE job_id=? ORDER BY id",
                (job_id,),
            ).fetchall()
        return [DeliveryLeg.from_row(r) for r in rows]

    def prepare(self, key: str, *, run_id: int | None, kind: str, target: str,
                salesman_key: str = "", slot_id: str = "", job_id: str = "") -> str:
        """Insert or reopen a retryable row as prepared. Returns 'send' or 'skip'."""
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT status FROM delivery_legs WHERE attempt_key=?", (key,)
            ).fetchone()
            if row and row["status"] in SETTLED:
                return "skip"
            if row:
                conn.execute(
                    "UPDATE delivery_legs SET status=?, error='', slot_id=?,"
                    " job_id=?, updated_at=datetime('now') WHERE attempt_key=?",
                    (PREPARED, slot_id or "", job_id or "", key),
                )
                return "send"
            conn.execute(
                "INSERT INTO delivery_legs(run_id, attempt_key, kind, target,"
                " salesman_key, status, slot_id, job_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, key, kind, target, salesman_key or "", PREPARED,
                 slot_id or "", job_id or ""),
            )
            return "send"

    def mark_sending(self, key: str) -> None:
        self._set_status(key, SENDING)

    def mark_accepted(self, key: str, *, remote_id: str = "") -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE delivery_legs SET status=?, error='', remote_id=?,"
                " updated_at=datetime('now') WHERE attempt_key=? AND status IN (?, ?)",
                (ACCEPTED, remote_id or "", key, SENDING, PREPARED),
            )

    def mark_sent(self, key: str, *, row_count: int = 0, remote_id: str = "") -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE delivery_legs SET status=?, error='', row_count=?,"
                " remote_id=?, updated_at=datetime('now') WHERE attempt_key=?"
                " AND status IN (?, ?, ?, ?)",
                (SENT, row_count, remote_id or "", key,
                 PREPARED, SENDING, ACCEPTED, UNKNOWN),
            )

    def mark_failed(self, key: str, error: str) -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE delivery_legs SET status=?, error=?,"
                " updated_at=datetime('now') WHERE attempt_key=?"
                " AND status NOT IN (?, ?)",
                (FAILED, (error or "")[:500], key, SENT, UNKNOWN),
            )

    def mark_unknown(self, key: str, error: str) -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE delivery_legs SET status=?, error=?,"
                " updated_at=datetime('now') WHERE attempt_key=?"
                " AND status IN (?, ?, ?)",
                (UNKNOWN, (error or "")[:500], key, SENDING, ACCEPTED, PREPARED),
            )

    def set_upload_session(self, key: str, url: str) -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE delivery_legs SET upload_session_url=?, updated_at=datetime('now')"
                " WHERE attempt_key=?",
                (url or "", key),
            )

    def list_unattached_unknown(self, limit: int = 50) -> list[DeliveryLeg]:
        """Email-now (and other) unknown legs with no schedule run to hang History on."""
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM delivery_legs WHERE status=? AND run_id IS NULL"
                " ORDER BY id DESC LIMIT ?",
                (UNKNOWN, max(1, int(limit))),
            ).fetchall()
        return [DeliveryLeg.from_row(r) for r in rows]

    def reopen_for_retry(self, key: str) -> bool:
        """Operator retry: unknown or failed → prepared. Keep any upload session."""
        with self.db.precious() as conn:
            cur = conn.execute(
                "UPDATE delivery_legs SET status=?, error='',"
                " updated_at=datetime('now') WHERE attempt_key=? AND status IN (?, ?)",
                (PREPARED, key, UNKNOWN, FAILED),
            )
            return cur.rowcount == 1

    def interrupt_orphaned_legs(self) -> list[DeliveryLeg]:
        """Settle legs whose job is gone and not running. Returns newly unknown email legs."""
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT l.* FROM delivery_legs l"
                " LEFT JOIN jobs j ON j.id = l.job_id"
                " WHERE l.status IN (?, ?, ?)"
                " AND (l.job_id = '' OR j.id IS NULL OR j.status NOT IN ('queued', 'running'))",
                (PREPARED, SENDING, ACCEPTED),
            ).fetchall()
        newly_unknown: list[DeliveryLeg] = []
        for row in rows:
            leg = DeliveryLeg.from_row(row)
            if leg.kind in EMAIL_KINDS and leg.status == SENDING:
                self.mark_unknown(
                    leg.attempt_key,
                    "Worker died after this send may have been accepted; not retried.",
                )
                updated = self.get(leg.attempt_key)
                if updated is not None:
                    newly_unknown.append(updated)
            elif leg.kind in EMAIL_KINDS and leg.status == ACCEPTED:
                self.mark_sent(leg.attempt_key, row_count=leg.row_count,
                               remote_id=leg.remote_id)
            elif leg.kind in FOLDER_KINDS and leg.status == ACCEPTED:
                self.mark_sent(leg.attempt_key, row_count=leg.row_count,
                               remote_id=leg.remote_id)
            elif leg.kind in FOLDER_KINDS and leg.status == SENDING:
                self.mark_failed(
                    leg.attempt_key,
                    "Upload interrupted; retry will check the folder before sending again.",
                )
            elif leg.status == PREPARED:
                self.mark_failed(leg.attempt_key, "Interrupted before send.")
        return newly_unknown

    def prune(self, older_than_days: int = LEG_RETENTION_DAYS) -> int:
        days = max(1, int(older_than_days))
        with self.db.precious() as conn:
            cur = conn.execute(
                "DELETE FROM delivery_legs WHERE updated_at < datetime('now', ?)",
                (f"-{days} days",),
            )
            return cur.rowcount

    def _set_status(self, key: str, status: str) -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE delivery_legs SET status=?, updated_at=datetime('now')"
                " WHERE attempt_key=?",
                (status, key),
            )
