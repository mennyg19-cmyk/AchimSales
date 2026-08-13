"""Schedule repositories (precious.db `schedules`, `master_schedules`,
`schedule_runs`).

Three closely-related concerns, colocated:

* ``ScheduleRepository``       - per-user recurring report deliveries.
* ``MasterScheduleRepository`` - admin-owned shared schedules (sensitive
  recipients; admin-only).
* ``ScheduleRunRepository``    - the run-history ledger for both kinds, used by
  the history UI and by the cron tick to decide whether a schedule is due.

``cadence`` is stored as a JSON string in the TEXT column, e.g.
``{"freq": "weekly", "time": "08:00", "weekdays": [1, 3]}``. Keeping it as JSON
avoids a schema migration and lets the cron tick compute the next due time
without an extra ``next_run_utc`` column.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from web.data.connection import Database

_UNSET = object()

PERSONAL = "personal"
MASTER = "master"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(s: str | None) -> dict:
    try:
        return json.loads(s or "{}")
    except (TypeError, ValueError):
        return {}


@dataclass(frozen=True)
class Schedule:
    id: int
    owner_user_id: int
    report_key: str
    params: dict
    layout: dict
    cadence: dict
    recipients: str
    sharepoint_path: str
    is_active: bool
    start_date: str | None
    end_date: str | None
    created_at: str
    filename_template: str = ""

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Schedule":
        keys = r.keys()
        return cls(
            id=r["id"], owner_user_id=r["owner_user_id"], report_key=r["report_key"],
            params=_loads(r["params_json"]), layout=_loads(r["layout_json"]),
            cadence=_loads(r["cadence"]), recipients=r["recipients"],
            sharepoint_path=r["sharepoint_path"], is_active=bool(r["is_active"]),
            start_date=r["start_date"], end_date=r["end_date"], created_at=r["created_at"],
            filename_template=(r["filename_template"] if "filename_template" in keys else "") or "",
        )


@dataclass(frozen=True)
class MasterSchedule:
    id: int
    report_key: str
    name: str
    params: dict
    layout: dict
    cadence: dict
    recipients: str
    sharepoint_path: str
    is_active: bool
    created_at: str
    filename_template: str = ""
    owner_user_id: int | None = None
    is_shared: bool = True
    run_as_user_id: int | None = None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "MasterSchedule":
        keys = r.keys()
        owner = r["owner_user_id"] if "owner_user_id" in keys else None
        run_as = r["run_as_user_id"] if "run_as_user_id" in keys else None
        shared = r["is_shared"] if "is_shared" in keys else 1
        return cls(
            id=r["id"], report_key=r["report_key"], name=r["name"],
            params=_loads(r["params_json"]), layout=_loads(r["layout_json"]),
            cadence=_loads(r["cadence"]), recipients=r["recipients"],
            sharepoint_path=r["sharepoint_path"], is_active=bool(r["is_active"]),
            created_at=r["created_at"],
            filename_template=(r["filename_template"] if "filename_template" in keys else "") or "",
            owner_user_id=int(owner) if owner is not None else None,
            is_shared=bool(shared),
            run_as_user_id=int(run_as) if run_as is not None else None,
        )


@dataclass(frozen=True)
class ScheduleRun:
    id: int
    schedule_id: int | None
    schedule_type: str
    status: str
    started_at: str | None
    finished_at: str | None
    rows: int | None
    output_meta: dict
    debug_log: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "ScheduleRun":
        return cls(
            id=r["id"], schedule_id=r["schedule_id"], schedule_type=r["schedule_type"],
            status=r["status"], started_at=r["started_at"], finished_at=r["finished_at"],
            rows=r["rows"], output_meta=_loads(r["output_meta"]), debug_log=r["debug_log"],
        )


class ScheduleRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, owner_user_id: int, report_key: str, *, params: dict,
               layout: dict, cadence: dict, recipients: str = "",
               sharepoint_path: str = "", start_date: str | None = None,
               end_date: str | None = None, filename_template: str = "") -> int:
        with self.db.precious() as conn:
            cur = conn.execute(
                "INSERT INTO schedules(owner_user_id, report_key, params_json, layout_json,"
                " cadence, recipients, sharepoint_path, start_date, end_date, filename_template)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (owner_user_id, report_key, json.dumps(params or {}),
                 json.dumps(layout or {}), json.dumps(cadence or {}),
                 recipients or "", sharepoint_path or "", start_date, end_date,
                 (filename_template or "").strip()),
            )
            return cur.lastrowid

    def update(self, schedule_id: int, owner_user_id: int, *, params: dict,
               layout: dict, cadence: dict, recipients: str = "",
               sharepoint_path: str = "", start_date: str | None = None,
               end_date: str | None = None, filename_template: str | None = None) -> bool:
        with self.db.precious() as conn:
            if filename_template is None:
                cur = conn.execute(
                    "UPDATE schedules SET params_json=?, layout_json=?, cadence=?,"
                    " recipients=?, sharepoint_path=?, start_date=?, end_date=?"
                    " WHERE id=? AND owner_user_id=?",
                    (json.dumps(params or {}), json.dumps(layout or {}),
                     json.dumps(cadence or {}), recipients or "", sharepoint_path or "",
                     start_date, end_date, schedule_id, owner_user_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE schedules SET params_json=?, layout_json=?, cadence=?,"
                    " recipients=?, sharepoint_path=?, start_date=?, end_date=?,"
                    " filename_template=?"
                    " WHERE id=? AND owner_user_id=?",
                    (json.dumps(params or {}), json.dumps(layout or {}),
                     json.dumps(cadence or {}), recipients or "", sharepoint_path or "",
                     start_date, end_date, filename_template.strip(),
                     schedule_id, owner_user_id),
                )
            return cur.rowcount == 1

    def set_active(self, schedule_id: int, owner_user_id: int, active: bool) -> bool:
        with self.db.precious() as conn:
            cur = conn.execute(
                "UPDATE schedules SET is_active=? WHERE id=? AND owner_user_id=?",
                (1 if active else 0, schedule_id, owner_user_id),
            )
            return cur.rowcount == 1

    def delete(self, schedule_id: int, owner_user_id: int) -> bool:
        with self.db.precious() as conn:
            cur = conn.execute(
                "DELETE FROM schedules WHERE id=? AND owner_user_id=?",
                (schedule_id, owner_user_id),
            )
            return cur.rowcount == 1

    def list_for_user(self, user_id: int) -> list[Schedule]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM schedules WHERE owner_user_id=? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [Schedule.from_row(r) for r in rows]

    def get(self, schedule_id: int, owner_user_id: int) -> Schedule | None:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT * FROM schedules WHERE id=? AND owner_user_id=?",
                (schedule_id, owner_user_id),
            ).fetchone()
            return Schedule.from_row(row) if row else None

    def get_any(self, schedule_id: int) -> Schedule | None:
        """Owner-agnostic fetch for the worker/cron (which has no principal)."""
        with self.db.precious() as conn:
            row = conn.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone()
            return Schedule.from_row(row) if row else None

    def list_active(self) -> list[Schedule]:
        with self.db.precious() as conn:
            rows = conn.execute("SELECT * FROM schedules WHERE is_active=1").fetchall()
            return [Schedule.from_row(r) for r in rows]


class MasterScheduleRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, report_key: str, name: str, *, params: dict, layout: dict,
               cadence: dict, recipients: str = "", sharepoint_path: str = "",
               filename_template: str = "", owner_user_id: int | None = None,
               is_shared: bool = True, run_as_user_id: int | None = None,
               is_active: bool = True) -> int:
        with self.db.precious() as conn:
            cur = conn.execute(
                "INSERT INTO master_schedules(report_key, name, params_json, layout_json,"
                " cadence, recipients, sharepoint_path, filename_template, is_active,"
                " owner_user_id, is_shared, run_as_user_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (report_key, name.strip(), json.dumps(params or {}),
                 json.dumps(layout or {}), json.dumps(cadence or {}),
                 recipients or "", sharepoint_path or "",
                 (filename_template or "").strip(),
                 1 if is_active else 0,
                 owner_user_id, 1 if is_shared else 0, run_as_user_id),
            )
            return cur.lastrowid

    def update(self, schedule_id: int, *, name: str, params: dict, layout: dict,
               cadence: dict, recipients: str = "", sharepoint_path: str = "",
               report_key: str | None = None, filename_template: str | None = None,
               is_shared: bool | None = None, run_as_user_id: int | None | object = _UNSET) -> bool:
        with self.db.precious() as conn:
            tmpl = None if filename_template is None else filename_template.strip()
            sets = ["name=?", "params_json=?", "layout_json=?", "cadence=?",
                    "recipients=?", "sharepoint_path=?"]
            vals: list = [name.strip(), json.dumps(params or {}), json.dumps(layout or {}),
                          json.dumps(cadence or {}), recipients or "", sharepoint_path or ""]
            if report_key:
                sets.append("report_key=?")
                vals.append(report_key.strip())
            if tmpl is not None:
                sets.append("filename_template=?")
                vals.append(tmpl)
            if is_shared is not None:
                sets.append("is_shared=?")
                vals.append(1 if is_shared else 0)
            if run_as_user_id is not _UNSET:
                sets.append("run_as_user_id=?")
                vals.append(run_as_user_id)
            vals.append(schedule_id)
            cur = conn.execute(
                f"UPDATE master_schedules SET {', '.join(sets)} WHERE id=?", vals,
            )
            return cur.rowcount == 1

    def set_active(self, schedule_id: int, active: bool) -> bool:
        with self.db.precious() as conn:
            cur = conn.execute(
                "UPDATE master_schedules SET is_active=? WHERE id=?",
                (1 if active else 0, schedule_id),
            )
            return cur.rowcount == 1

    def delete(self, schedule_id: int) -> bool:
        with self.db.precious() as conn:
            cur = conn.execute("DELETE FROM master_schedules WHERE id=?", (schedule_id,))
            return cur.rowcount == 1

    def list_all(self) -> list[MasterSchedule]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM master_schedules ORDER BY created_at DESC"
            ).fetchall()
            return [MasterSchedule.from_row(r) for r in rows]

    def list_shared(self) -> list[MasterSchedule]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM master_schedules WHERE is_shared=1 ORDER BY created_at DESC"
            ).fetchall()
            return [MasterSchedule.from_row(r) for r in rows]

    def list_private_for_user(self, user_id: int) -> list[MasterSchedule]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM master_schedules WHERE is_shared=0 AND owner_user_id=?"
                " ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [MasterSchedule.from_row(r) for r in rows]

    def get(self, schedule_id: int) -> MasterSchedule | None:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT * FROM master_schedules WHERE id=?", (schedule_id,)
            ).fetchone()
            return MasterSchedule.from_row(row) if row else None

    def list_active(self) -> list[MasterSchedule]:
        with self.db.precious() as conn:
            rows = conn.execute("SELECT * FROM master_schedules WHERE is_active=1").fetchall()
            return [MasterSchedule.from_row(r) for r in rows]


class ScheduleRunRepository:
    def __init__(self, db: Database):
        self.db = db

    def start(self, schedule_id: int | None, schedule_type: str = PERSONAL) -> int:
        with self.db.precious() as conn:
            cur = conn.execute(
                "INSERT INTO schedule_runs(schedule_id, schedule_type, status, started_at)"
                " VALUES (?, ?, 'running', ?)",
                (schedule_id, schedule_type, _now()),
            )
            return cur.lastrowid

    def finish(self, run_id: int, *, status: str, rows: int | None = None,
               output_meta: dict | None = None, debug_log: str = "") -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE schedule_runs SET status=?, finished_at=?, rows=?, output_meta=?,"
                " debug_log=? WHERE id=?",
                (status, _now(), rows, json.dumps(output_meta or {}), debug_log, run_id),
            )

    def get(self, run_id: int) -> ScheduleRun | None:
        with self.db.precious() as conn:
            row = conn.execute("SELECT * FROM schedule_runs WHERE id=?", (run_id,)).fetchone()
            return ScheduleRun.from_row(row) if row else None

    def list_for_schedule(self, schedule_id: int, schedule_type: str = PERSONAL,
                          limit: int = 50) -> list[ScheduleRun]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM schedule_runs WHERE schedule_id=? AND schedule_type=?"
                " ORDER BY id DESC LIMIT ?",
                (schedule_id, schedule_type, limit),
            ).fetchall()
            return [ScheduleRun.from_row(r) for r in rows]

    def list_recent(self, *, limit: int = 40) -> list[ScheduleRun]:
        """Newest schedule runs first (personal + master), for the Schedules page log."""
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM schedule_runs ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
            return [ScheduleRun.from_row(r) for r in rows]

    def last_run_at(self, schedule_id: int, schedule_type: str = PERSONAL) -> str | None:
        """Most recent started_at for due-time calculation by the cron tick."""
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT MAX(started_at) AS t FROM schedule_runs"
                " WHERE schedule_id=? AND schedule_type=?",
                (schedule_id, schedule_type),
            ).fetchone()
            return row["t"] if row else None
