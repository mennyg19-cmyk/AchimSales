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
_NAME_MAX = 120


def next_copy_name(base: str, existing: set[str]) -> str:
    """`Daily 9am (copy)`, then `(copy 2)` if that name is taken."""
    stem = (base or "Schedule").strip() or "Schedule"
    n = 1
    while True:
        suffix = " (copy)" if n == 1 else f" (copy {n})"
        room = max(1, _NAME_MAX - len(suffix))
        candidate = (stem[:room] + suffix)[:_NAME_MAX]
        if candidate not in existing:
            return candidate
        n += 1


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
    catch_up_pending: bool = False
    catch_up_for_date: str | None = None
    last_claimed_at: str | None = None
    view_name: str = "Default"

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
            catch_up_pending=bool(r["catch_up_pending"]) if "catch_up_pending" in keys else False,
            catch_up_for_date=(r["catch_up_for_date"] if "catch_up_for_date" in keys else None),
            last_claimed_at=(r["last_claimed_at"] if "last_claimed_at" in keys else None),
            view_name=(r["view_name"] if "view_name" in keys else "") or "Default",
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
    catch_up_pending: bool = False
    catch_up_for_date: str | None = None
    last_claimed_at: str | None = None
    view_name: str = "Default"

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
            catch_up_pending=bool(r["catch_up_pending"]) if "catch_up_pending" in keys else False,
            catch_up_for_date=(r["catch_up_for_date"] if "catch_up_for_date" in keys else None),
            last_claimed_at=(r["last_claimed_at"] if "last_claimed_at" in keys else None),
            view_name=(r["view_name"] if "view_name" in keys else "") or "Default",
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


def _set_catch_up(db: Database, table: str, schedule_id: int, pending: bool,
                  for_date: str | None) -> None:
    if table not in ("schedules", "master_schedules"):
        raise ValueError(f"unknown schedule table {table!r}")
    with db.precious() as conn:
        if not pending:
            conn.execute(
                f"UPDATE {table} SET catch_up_pending=0, catch_up_for_date=NULL WHERE id=?",
                (schedule_id,),
            )
            return
        row = conn.execute(
            f"SELECT catch_up_for_date FROM {table} WHERE id=?", (schedule_id,),
        ).fetchone()
        existing = None
        if row is not None and "catch_up_for_date" in row.keys():
            existing = row["catch_up_for_date"]
        kept = existing
        if for_date:
            kept = min(x for x in (existing, for_date) if x) if existing else for_date
        conn.execute(
            f"UPDATE {table} SET catch_up_pending=1, catch_up_for_date=? WHERE id=?",
            (kept, schedule_id),
        )


class ScheduleRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, owner_user_id: int, report_key: str, *, params: dict,
               layout: dict, cadence: dict, recipients: str = "",
               sharepoint_path: str = "", start_date: str | None = None,
               end_date: str | None = None, filename_template: str = "",
               view_name: str = "Default") -> int:
        with self.db.precious() as conn:
            cur = conn.execute(
                "INSERT INTO schedules(owner_user_id, report_key, params_json, layout_json,"
                " cadence, recipients, sharepoint_path, start_date, end_date,"
                " filename_template, view_name)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (owner_user_id, report_key, json.dumps(params or {}),
                 json.dumps(layout or {}), json.dumps(cadence or {}),
                 recipients or "", sharepoint_path or "", start_date, end_date,
                 (filename_template or "").strip(),
                 (view_name or "Default").strip() or "Default"),
            )
            return cur.lastrowid

    def update(self, schedule_id: int, owner_user_id: int, *, params: dict,
               layout: dict, cadence: dict, recipients: str = "",
               sharepoint_path: str = "", start_date: str | None = None,
               end_date: str | None = None, filename_template: str | None = None,
               view_name: str | None = None) -> bool:
        with self.db.precious() as conn:
            sets = ["params_json=?", "layout_json=?", "cadence=?",
                    "recipients=?", "sharepoint_path=?", "start_date=?", "end_date=?"]
            vals: list = [json.dumps(params or {}), json.dumps(layout or {}),
                          json.dumps(cadence or {}), recipients or "", sharepoint_path or "",
                          start_date, end_date]
            if filename_template is not None:
                sets.append("filename_template=?")
                vals.append(filename_template.strip())
            if view_name is not None:
                sets.append("view_name=?")
                vals.append(view_name.strip() or "Default")
            vals.extend([schedule_id, owner_user_id])
            cur = conn.execute(
                f"UPDATE schedules SET {', '.join(sets)} WHERE id=? AND owner_user_id=?",
                vals,
            )
            return cur.rowcount == 1

    def set_active(self, schedule_id: int, owner_user_id: int, active: bool) -> bool:
        with self.db.precious() as conn:
            cur = conn.execute(
                "UPDATE schedules SET is_active=? WHERE id=? AND owner_user_id=?",
                (1 if active else 0, schedule_id, owner_user_id),
            )
            return cur.rowcount == 1

    def claim_slot(self, schedule_id: int, when_iso: str) -> None:
        """Mark today's slot taken so a save/On does not catch up a missed send."""
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE schedules SET last_claimed_at=? WHERE id=?",
                (when_iso, schedule_id),
            )

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

    def list_all(self) -> list[Schedule]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM schedules ORDER BY owner_user_id, created_at DESC",
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

    def set_catch_up(self, schedule_id: int, pending: bool,
                     for_date: str | None = None) -> None:
        _set_catch_up(self.db, "schedules", schedule_id, pending, for_date)


class MasterScheduleRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, report_key: str, name: str, *, params: dict, layout: dict,
               cadence: dict, recipients: str = "", sharepoint_path: str = "",
               filename_template: str = "", owner_user_id: int | None = None,
               is_shared: bool = True, run_as_user_id: int | None = None,
               is_active: bool = True, view_name: str = "Default") -> int:
        with self.db.precious() as conn:
            cur = conn.execute(
                "INSERT INTO master_schedules(report_key, name, params_json, layout_json,"
                " cadence, recipients, sharepoint_path, filename_template, is_active,"
                " owner_user_id, is_shared, run_as_user_id, view_name)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (report_key, name.strip(), json.dumps(params or {}),
                 json.dumps(layout or {}), json.dumps(cadence or {}),
                 recipients or "", sharepoint_path or "",
                 (filename_template or "").strip(),
                 1 if is_active else 0,
                 owner_user_id, 1 if is_shared else 0, run_as_user_id,
                 (view_name or "Default").strip() or "Default"),
            )
            return cur.lastrowid

    def unused_copy_name(self, base: str) -> str:
        with self.db.precious() as conn:
            rows = conn.execute("SELECT name FROM master_schedules").fetchall()
        return next_copy_name(base, {r["name"] for r in rows})

    def copy(self, src: MasterSchedule, *, owner_user_id: int) -> int:
        """Inactive duplicate. Unique name so shared copies don't trip the index."""
        fields = dict(
            params=dict(src.params or {}), layout=dict(src.layout or {}),
            cadence=dict(src.cadence or {}), recipients=src.recipients,
            sharepoint_path=src.sharepoint_path,
            filename_template=src.filename_template or "",
            owner_user_id=owner_user_id, is_shared=src.is_shared,
            run_as_user_id=src.run_as_user_id, is_active=False,
            view_name=getattr(src, "view_name", None) or "Default",
        )
        for _ in range(8):
            name = self.unused_copy_name(src.name)
            try:
                return self.create(src.report_key, name, **fields)
            except sqlite3.IntegrityError:
                continue
        raise sqlite3.IntegrityError("Could not find an unused copy name")

    def update(self, schedule_id: int, *, name: str, params: dict, layout: dict,
               cadence: dict, recipients: str = "", sharepoint_path: str = "",
               report_key: str | None = None, filename_template: str | None = None,
               is_shared: bool | None = None, run_as_user_id: int | None | object = _UNSET,
               view_name: str | None = None) -> bool:
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
            if view_name is not None:
                sets.append("view_name=?")
                vals.append(view_name.strip() or "Default")
            vals.append(schedule_id)
            cur = conn.execute(
                f"UPDATE master_schedules SET {', '.join(sets)} WHERE id=?", vals,
            )
            return cur.rowcount == 1

    def enable_split_all_if_plain(self, name: str) -> bool:
        """Turn on split-all when this schedule has no salesman-delivery flags yet."""
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT id, params_json FROM master_schedules WHERE name=?", (name,),
            ).fetchone()
            if row is None:
                return False
            params = _loads(row["params_json"])
            if not isinstance(params, dict):
                params = {}
            if (
                "split_by_salesman" in params
                or params.get("email_salesman_keys")
                or params.get("email_to_salesmen")
            ):
                return False
            params["split_by_salesman"] = True
            conn.execute(
                "UPDATE master_schedules SET params_json=? WHERE id=?",
                (json.dumps(params), row["id"]),
            )
            return True

    def fill_layout_if_blank(self, name: str, layout: dict) -> bool:
        """Stamp a tab layout onto an existing schedule that has none yet."""
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT id, layout_json FROM master_schedules WHERE name=?", (name,),
            ).fetchone()
            if row is None:
                return False
            current = _loads(row["layout_json"])
            if isinstance(current, dict) and current.get("order"):
                return False
            conn.execute(
                "UPDATE master_schedules SET layout_json=? WHERE id=?",
                (json.dumps(layout or {}), row["id"]),
            )
            return True

    def set_view(self, schedule_id: int, view_name: str, layout: dict) -> bool:
        with self.db.precious() as conn:
            cur = conn.execute(
                "UPDATE master_schedules SET view_name=?, layout_json=? WHERE id=?",
                ((view_name or "Default").strip() or "Default",
                 json.dumps(layout or {}), schedule_id),
            )
            return cur.rowcount == 1

    def set_active(self, schedule_id: int, active: bool) -> bool:
        with self.db.precious() as conn:
            cur = conn.execute(
                "UPDATE master_schedules SET is_active=? WHERE id=?",
                (1 if active else 0, schedule_id),
            )
            return cur.rowcount == 1

    def claim_slot(self, schedule_id: int, when_iso: str) -> None:
        """Mark today's slot taken so a save/On does not catch up a missed send."""
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE master_schedules SET last_claimed_at=? WHERE id=?",
                (when_iso, schedule_id),
            )

    def set_catch_up(self, schedule_id: int, pending: bool,
                     for_date: str | None = None) -> None:
        _set_catch_up(self.db, "master_schedules", schedule_id, pending, for_date)

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

    def start(self, schedule_id: int | None, schedule_type: str = PERSONAL,
              started_at: str | None = None) -> int:
        with self.db.precious() as conn:
            cur = conn.execute(
                "INSERT INTO schedule_runs(schedule_id, schedule_type, status, started_at)"
                " VALUES (?, ?, 'running', ?)",
                (schedule_id, schedule_type, started_at or _now()),
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
        """Most recent attributable run for due-time calculation by the cron tick."""
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT MAX(started_at) AS t FROM schedule_runs"
                " WHERE schedule_id=? AND schedule_type=?"
                " AND status NOT IN ('legacy', 'unknown')"
                " AND COALESCE(json_extract(output_meta, '$.legacy'), 0) != 1",
                (schedule_id, schedule_type),
            ).fetchone()
            return row["t"] if row else None

    def last_success_at(self, schedule_id: int, schedule_type: str = PERSONAL) -> str | None:
        """Most recent successful started_at (skips/failures do not count)."""
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT MAX(started_at) AS t FROM schedule_runs"
                " WHERE schedule_id=? AND schedule_type=? AND status='success'",
                (schedule_id, schedule_type),
            ).fetchone()
            return row["t"] if row else None

    def patch_output_meta(self, run_id: int, output_meta: dict) -> None:
        with self.db.precious() as conn:
            conn.execute(
                "UPDATE schedule_runs SET output_meta=? WHERE id=?",
                (json.dumps(output_meta or {}), run_id),
            )

    def list_recent_failures(self, *, limit: int = 80) -> list[ScheduleRun]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM schedule_runs WHERE status='failure'"
                " ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [ScheduleRun.from_row(r) for r in rows]
