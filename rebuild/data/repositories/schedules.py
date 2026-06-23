"""Reading and writing saved report schedules."""

# === What's in this file ===
# The only code that touches the schedules table. A schedule is a saved, repeating
# report send: who owns it, which report and filters, how often (cadence), who
# gets it, and whether to skip Saturdays/holidays. The poller reads the active
# ones to decide what's due; the run handler reads one by id to deliver it; the
# UI lists/creates/edits/deletes them.
#
# Schedule -- a plain snapshot of one row (JSON columns decoded)
# SchedulesRepository.create() / update() / delete() -- manage one schedule
# SchedulesRepository.get() -- one schedule by id
# SchedulesRepository.list_for_owner() -- a person's own schedules
# SchedulesRepository.list_all() -- every schedule (admin view)
# SchedulesRepository.list_active() -- enabled schedules the poller scans
# SchedulesRepository.mark_ran() -- stamp last_run_at after a fire

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ..connection import Database, utc_now_iso

KIND_SELF = "self"
KIND_MASTER = "master"
VALID_KINDS = (KIND_SELF, KIND_MASTER)


@dataclass(frozen=True)
class Schedule:
    id: str
    owner_email: str
    report_key: str
    title: str
    kind: str
    filters: dict
    cadence: dict
    recipients: list[str]
    salesmen: list[str]
    tab_key: Optional[str]
    skip_sabbath: bool
    enabled: bool
    last_run_at: Optional[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Schedule":
        return cls(
            id=row["id"],
            owner_email=row["owner_email"],
            report_key=row["report_key"],
            title=row["title"],
            kind=row["kind"],
            filters=json.loads(row["filters"] or "{}"),
            cadence=json.loads(row["cadence"] or "{}"),
            recipients=json.loads(row["recipients"] or "[]"),
            salesmen=json.loads(row["salesmen"] or "[]"),
            tab_key=row["tab_key"],
            skip_sabbath=bool(row["skip_sabbath"]),
            enabled=bool(row["enabled"]),
            last_run_at=row["last_run_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


class SchedulesRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self,
        *,
        owner_email: str,
        report_key: str,
        title: str,
        kind: str,
        filters: dict,
        cadence: dict,
        recipients: list[str],
        salesmen: list[str],
        tab_key: Optional[str],
        skip_sabbath: bool,
        enabled: bool = True,
    ) -> Schedule:
        schedule_id = uuid.uuid4().hex
        now = utc_now_iso()
        with self._db.precious() as conn:
            conn.execute(
                "INSERT INTO schedules (id, owner_email, report_key, title, kind, filters, "
                "cadence, recipients, salesmen, tab_key, skip_sabbath, enabled, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    schedule_id,
                    _norm_email(owner_email),
                    report_key,
                    title,
                    kind,
                    json.dumps(filters or {}),
                    json.dumps(cadence or {}),
                    json.dumps(_clean_emails(recipients)),
                    json.dumps(_clean_numbers(salesmen)),
                    tab_key or None,
                    1 if skip_sabbath else 0,
                    1 if enabled else 0,
                    now,
                    now,
                ),
            )
            return self.get(schedule_id)  # type: ignore[return-value]

    def update(
        self,
        schedule_id: str,
        *,
        title: str,
        filters: dict,
        cadence: dict,
        recipients: list[str],
        salesmen: list[str],
        tab_key: Optional[str],
        skip_sabbath: bool,
        enabled: bool,
    ) -> None:
        with self._db.precious() as conn:
            conn.execute(
                "UPDATE schedules SET title = ?, filters = ?, cadence = ?, recipients = ?, "
                "salesmen = ?, tab_key = ?, skip_sabbath = ?, enabled = ?, updated_at = ? WHERE id = ?",
                (
                    title,
                    json.dumps(filters or {}),
                    json.dumps(cadence or {}),
                    json.dumps(_clean_emails(recipients)),
                    json.dumps(_clean_numbers(salesmen)),
                    tab_key or None,
                    1 if skip_sabbath else 0,
                    1 if enabled else 0,
                    utc_now_iso(),
                    schedule_id,
                ),
            )

    def delete(self, schedule_id: str) -> None:
        with self._db.precious() as conn:
            conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))

    def get(self, schedule_id: str) -> Optional[Schedule]:
        with self._db.precious() as conn:
            row = conn.fetchone("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
            return Schedule.from_row(row) if row else None

    def list_for_owner(self, owner_email: str) -> list[Schedule]:
        with self._db.precious() as conn:
            rows = conn.fetchall(
                "SELECT * FROM schedules WHERE owner_email = ? ORDER BY created_at DESC",
                (_norm_email(owner_email),),
            )
            return [Schedule.from_row(r) for r in rows]

    def list_all(self) -> list[Schedule]:
        with self._db.precious() as conn:
            rows = conn.fetchall("SELECT * FROM schedules ORDER BY created_at DESC")
            return [Schedule.from_row(r) for r in rows]

    def list_active(self) -> list[Schedule]:
        with self._db.precious() as conn:
            rows = conn.fetchall("SELECT * FROM schedules WHERE enabled = 1")
            return [Schedule.from_row(r) for r in rows]

    def mark_ran(self, schedule_id: str, ran_at: Optional[str] = None) -> None:
        with self._db.precious() as conn:
            conn.execute(
                "UPDATE schedules SET last_run_at = ? WHERE id = ?",
                (ran_at or utc_now_iso(), schedule_id),
            )


def _clean_emails(emails: list[str]) -> list[str]:
    seen: list[str] = []
    for raw in emails or []:
        email = _norm_email(raw)
        if email and email not in seen:
            seen.append(email)
    return seen


def _clean_numbers(numbers: list[str]) -> list[str]:
    seen: list[str] = []
    for raw in numbers or []:
        number = (raw or "").strip()
        if number and number not in seen:
            seen.append(number)
    return seen
