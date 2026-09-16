"""Read/write helpers for sqlite. Sales facts stay in catalog mocks."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import cadence
import views as view_tables
from config import db_path
from db import db


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def setting(key: str, default: str = "") -> str:
    with db() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def list_users() -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY email").fetchall()
    return [dict(row) for row in rows]


def get_user(email: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE lower(email) = ?",
            ((email or "").strip().lower(),),
        ).fetchone()
    return dict(row) if row else None


def user_count() -> int:
    with db() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])


_ACHIM_MAIL = "@achimonline.com"
_ACHIM_AD = "@ad.achimonline.com"


def login_email_aliases(email: str) -> list[str]:
    """Entra often returns the AD UPN (mennyg@ad.achimonline.com) while People has the mailbox."""
    raw = (email or "").strip().lower()
    if not raw:
        return []
    aliases = [raw]
    if raw.endswith(_ACHIM_AD):
        aliases.append(raw[: -len(_ACHIM_AD)] + _ACHIM_MAIL)
    elif raw.endswith(_ACHIM_MAIL):
        aliases.append(raw[: -len(_ACHIM_MAIL)] + _ACHIM_AD)
    return aliases


def get_user_for_login(email: str) -> dict | None:
    seen: set[str] = set()
    for candidate in login_email_aliases(email):
        if candidate in seen:
            continue
        seen.add(candidate)
        row = get_user(candidate)
        if row:
            return row
    return None


def preview_login_row() -> dict | None:
    row = get_user("preview@achimonline.com")
    if row and row.get("is_active"):
        return row
    with db() as conn:
        row = conn.execute(
            """SELECT * FROM users
               WHERE is_active = 1 AND role IN ('admin', 'developer')
               ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END, id
               LIMIT 1"""
        ).fetchone()
    return dict(row) if row else None


def add_user(email: str, display_name: str, role: str, is_external: int, sales_group: str) -> None:
    with db() as conn:
        conn.execute(
            """INSERT INTO users (email, display_name, role, is_active, is_external, sales_group)
               VALUES (?, ?, ?, 1, ?, ?)""",
            (email.lower(), display_name or email, role, is_external, sales_group),
        )


def update_user(user_id: int, fields: dict) -> None:
    allowed = {
        "display_name", "role", "is_active", "is_external", "sales_group",
        "can_see_company_views", "sharepoint_access",
        "dashboard_enabled", "test_access", "theme",
    }
    sets = []
    values = []
    for key, value in fields.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(value)
    if not sets:
        return
    values.append(user_id)
    with db() as conn:
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", values)


def delete_user(user_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM user_sales_groups WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_report_access WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def visibility_map() -> dict[str, bool]:
    with db() as conn:
        rows = conn.execute("SELECT report_key, enabled FROM report_visibility").fetchall()
    return {row["report_key"]: bool(row["enabled"]) for row in rows}


def set_visibility(report_key: str, enabled: bool) -> None:
    with db() as conn:
        conn.execute(
            """INSERT INTO report_visibility (report_key, enabled) VALUES (?, ?)
               ON CONFLICT(report_key) DO UPDATE SET enabled = excluded.enabled""",
            (report_key, 1 if enabled else 0),
        )


def _hydrate_view(row, conn) -> dict:
    return view_tables.hydrate(row, conn)


def _attach_view_to_schedule(row, conn) -> dict:
    out = dict(row)
    view_row = conn.execute("SELECT * FROM views WHERE id = ?", (out["view_id"],)).fetchone()
    if view_row is None:
        out["params"] = {}
        out["layout"] = {}
        return out
    hydrated = _hydrate_view(view_row, conn)
    out["params"] = hydrated["params"]
    out["layout"] = hydrated["layout"]
    out["include_period"] = hydrated.get("include_period")
    return out


def list_views(email: str, privileged: bool) -> list[dict]:
    with db() as conn:
        if privileged:
            rows = conn.execute("SELECT * FROM views ORDER BY kind, name").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM views WHERE owner_email = ? OR kind = 'company' ORDER BY name",
                (email,),
            ).fetchall()
        return [_hydrate_view(row, conn) for row in rows]


def validate_view_params(params: dict) -> str | None:
    group = params.get("group")
    if group is not None and not isinstance(group, list):
        return "views.group must stay an array"
    return None


def validate_layout(layout: dict | None) -> str | None:
    if layout is None:
        return None
    if not isinstance(layout, dict):
        return "layout must be a JSON object"
    tabs = layout.get("views")
    if tabs is None:
        return None
    if not isinstance(tabs, dict):
        return "layout.views must be an object"
    for spec in tabs.values():
        if isinstance(spec, dict) and isinstance(spec.get("group"), str):
            return "views.group must stay an array"
    return None


def add_view(
    owner_email: str | None,
    report_key: str,
    name: str,
    kind: str,
    params: dict,
    include_period: int,
    layout: dict | None = None,
) -> int:
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO views (owner_email, report_key, name, kind, include_period)
               VALUES (?, ?, ?, ?, ?)""",
            (owner_email, report_key, name, kind, include_period),
        )
        view_id = int(cur.lastrowid)
        view_tables.save_filters_and_layout(conn, view_id, params, layout, include_period)
        return view_id


def get_view(view_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM views WHERE id = ?", (view_id,)).fetchone()
        if row is None:
            return None
        return _hydrate_view(row, conn)


def delete_view(view_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM views WHERE id = ?", (view_id,))


def save_job(
    report_key: str,
    title: str,
    payload: dict,
    owner_email: str = "",
    kept: int = 0,
    keep_name: str | None = None,
    status: str = "success",
) -> int:
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO jobs (report_key, title, status, created_at, kept, keep_name, payload_json, owner_email)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (report_key, title, status, now_iso(), kept, keep_name, json.dumps(payload), owner_email),
        )
        return int(cur.lastrowid)


KEEP_CAP = 5
KEEP_DAYS = 30


def keep_job(job_id: int, name: str, *, cap: int = KEEP_CAP, days: int = KEEP_DAYS) -> None:
    until = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    label = (name or "").strip()[:80] or "Kept run"
    with db() as conn:
        row = conn.execute("SELECT owner_email FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return
        conn.execute(
            "UPDATE jobs SET kept = 1, keep_name = ?, kept_until = ? WHERE id = ?",
            (label, until, job_id),
        )
        owner = row["owner_email"] or ""
        kept = conn.execute(
            """SELECT id FROM jobs WHERE kept = 1 AND owner_email = ?
               ORDER BY kept_until DESC, id DESC""",
            (owner,),
        ).fetchall()
        if len(kept) > cap:
            drop_ids = [item["id"] for item in kept[cap:]]
            conn.executemany(
                "UPDATE jobs SET kept = 0, keep_name = '', kept_until = NULL WHERE id = ?",
                [(item,) for item in drop_ids],
            )


def cancel_job(job_id: int) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'cancelled' WHERE id = ? AND status IN ('running', 'queued')",
            (job_id,),
        )


def list_jobs(kept_only: bool = False, owner_email: str | None = None) -> list[dict]:
    sql = "SELECT id, report_key, title, status, created_at, kept, keep_name, owner_email FROM jobs"
    clauses = []
    args: list = []
    if kept_only:
        clauses.append("kept = 1")
    if owner_email is not None:
        clauses.append("owner_email = ?")
        args.append(owner_email)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id DESC LIMIT 30"
    with db() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(row) for row in rows]


def get_job(job_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    out = dict(row)
    out["payload"] = json.loads(out.pop("payload_json"))
    return out


def add_outbox(recipients: str, subject: str, body: str) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO outbox (created_at, recipients, subject, body) VALUES (?, ?, ?, ?)",
            (now_iso(), recipients, subject, body),
        )
        return int(cur.lastrowid)


def list_outbox() -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM outbox ORDER BY id DESC LIMIT 50").fetchall()
    return [dict(row) for row in rows]


def _weekday_csv(numbers: list[int]) -> str:
    names = []
    for day in numbers:
        if 0 <= day < len(cadence.WEEKDAY_NAMES):
            names.append(cadence.WEEKDAY_NAMES[day])
    return ",".join(names)


def _weekday_numbers(csv_text: str) -> list[int]:
    out = []
    for part in str(csv_text or "").split(","):
        name = part.strip().lower()[:3]
        if name in cadence.WEEKDAY_NAMES:
            out.append(cadence.WEEKDAY_NAMES.index(name))
    return out


def _split_addr_list(raw: str) -> list[str]:
    return [part.strip().lower() for part in str(raw or "").replace(";", ",").split(",") if "@" in part]


def write_schedule_children(
    conn,
    schedule_id: int,
    *,
    weekdays: str = "",
    monthday: int | None = None,
    recipients: str = "",
    cc: str = "",
    bcc: str = "",
    salesmen: list[str] | None = None,
) -> None:
    conn.execute("DELETE FROM schedule_weekdays WHERE schedule_id = ?", (schedule_id,))
    conn.execute("DELETE FROM schedule_monthdays WHERE schedule_id = ?", (schedule_id,))
    conn.execute("DELETE FROM schedule_recipients WHERE schedule_id = ?", (schedule_id,))
    conn.execute("DELETE FROM schedule_email_salesmen WHERE schedule_id = ?", (schedule_id,))
    for day in _weekday_numbers(weekdays):
        conn.execute(
            "INSERT OR IGNORE INTO schedule_weekdays (schedule_id, weekday) VALUES (?, ?)",
            (schedule_id, day),
        )
    if monthday not in (None, ""):
        conn.execute(
            "INSERT OR IGNORE INTO schedule_monthdays (schedule_id, monthday) VALUES (?, ?)",
            (schedule_id, int(monthday)),
        )
    for email in _split_addr_list(recipients):
        conn.execute(
            "INSERT OR IGNORE INTO schedule_recipients (schedule_id, email, role) VALUES (?, ?, 'to')",
            (schedule_id, email),
        )
    for email in _split_addr_list(cc):
        conn.execute(
            "INSERT OR IGNORE INTO schedule_recipients (schedule_id, email, role) VALUES (?, ?, 'cc')",
            (schedule_id, email),
        )
    for email in _split_addr_list(bcc):
        conn.execute(
            "INSERT OR IGNORE INTO schedule_recipients (schedule_id, email, role) VALUES (?, ?, 'bcc')",
            (schedule_id, email),
        )
    for salesman in salesmen or []:
        if salesman:
            conn.execute(
                "INSERT OR IGNORE INTO schedule_email_salesmen (schedule_id, salesman) VALUES (?, ?)",
                (schedule_id, salesman),
            )


def hydrate_schedule_row(row, conn) -> dict:
    out = dict(row)
    sid = out["id"]
    days = [
        int(r["weekday"])
        for r in conn.execute(
            "SELECT weekday FROM schedule_weekdays WHERE schedule_id = ? ORDER BY weekday",
            (sid,),
        )
    ]
    if days:
        out["weekdays"] = _weekday_csv(days)
    month = conn.execute(
        "SELECT monthday FROM schedule_monthdays WHERE schedule_id = ? ORDER BY monthday LIMIT 1",
        (sid,),
    ).fetchone()
    if month:
        out["monthday"] = int(month["monthday"])
    to_addrs, cc_addrs, bcc_addrs = [], [], []
    for rec in conn.execute(
        "SELECT email, role FROM schedule_recipients WHERE schedule_id = ? ORDER BY role, email",
        (sid,),
    ):
        email = rec["email"] or ""
        if rec["role"] == "cc":
            cc_addrs.append(email)
        elif rec["role"] == "bcc":
            bcc_addrs.append(email)
        else:
            to_addrs.append(email)
    if to_addrs or cc_addrs or bcc_addrs:
        out["recipients"] = ", ".join(to_addrs)
        out["cc"] = ", ".join(cc_addrs)
        out["bcc"] = ", ".join(bcc_addrs)
    out["email_salesmen"] = [
        r["salesman"]
        for r in conn.execute(
            "SELECT salesman FROM schedule_email_salesmen WHERE schedule_id = ? ORDER BY salesman",
            (sid,),
        )
    ]
    return out


def list_schedules() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT s.*, v.name AS view_name, v.report_key, v.kind AS view_kind
               FROM schedules s JOIN views v ON v.id = s.view_id
               ORDER BY s.id"""
        ).fetchall()
        return [hydrate_schedule_row(row, conn) for row in rows]


def list_active_schedules() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT s.*, v.name AS view_name, v.report_key, v.kind AS view_kind
               FROM schedules s JOIN views v ON v.id = s.view_id
               WHERE s.is_active = 1 AND ifnull(s.kind, 'personal') != 'company'
               ORDER BY s.id"""
        ).fetchall()
        return [_attach_view_to_schedule(hydrate_schedule_row(row, conn), conn) for row in rows]


def claim_today_slot(schedule_id: int, now: datetime | None = None) -> bool:
    """True if this process owns today's Eastern slot (once per day, race-safe)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = sqlite3.connect(db_path(), isolation_level="IMMEDIATE")
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT last_run FROM schedules WHERE id = ?",
            (schedule_id,),
        ).fetchone()
        if row is None:
            conn.rollback()
            return False
        if cadence.ran_today(row["last_run"], now.astimezone(cadence.EASTERN)):
            conn.rollback()
            return False
        conn.execute(
            "UPDATE schedules SET last_run = ? WHERE id = ?",
            (stamp, schedule_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def add_schedule(
    view_id: int,
    owner_email: str,
    freq: str,
    run_time: str,
    recipients: str,
    weekdays: str = "",
    monthday: int | None = None,
    cc: str = "",
    bcc: str = "",
    subject: str = "",
    filename: str = "",
    sharepoint_folder: str = "",
    onedrive_folder: str = "",
    name: str = "",
    kind: str = "personal",
) -> int:
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO schedules (
                   view_id, owner_email, name, kind, freq, run_time, weekdays, monthday,
                   recipients, cc, bcc, subject, filename, sharepoint_folder,
                   onedrive_folder, is_active
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                view_id, owner_email, name or "", kind, freq, run_time, weekdays, monthday,
                recipients, cc, bcc, subject, filename, sharepoint_folder,
                onedrive_folder,
            ),
        )
        schedule_id = int(cur.lastrowid)
        write_schedule_children(
            conn,
            schedule_id,
            weekdays=weekdays,
            monthday=monthday,
            recipients=recipients,
            cc=cc,
            bcc=bcc,
        )
        return schedule_id


def toggle_schedule(schedule_id: int) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE schedules SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE id = ?",
            (schedule_id,),
        )


def delete_schedule(schedule_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))


def mark_schedule_run(
    schedule_id: int, status: str, message: str, at: datetime | None = None
) -> None:
    if at is None:
        stamp = now_iso()
    else:
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        stamp = at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db() as conn:
        conn.execute(
            "UPDATE schedules SET last_run = ?, last_status = ? WHERE id = ?",
            (stamp, status, schedule_id),
        )
        conn.execute(
            "INSERT INTO schedule_runs (schedule_id, started_at, status, message) VALUES (?, ?, ?, ?)",
            (schedule_id, stamp, status, message),
        )


def list_schedule_runs() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT r.*, s.owner_email, v.name AS view_name, v.report_key, v.kind AS view_kind
               FROM schedule_runs r
               JOIN schedules s ON s.id = r.schedule_id
               JOIN views v ON v.id = s.view_id
               ORDER BY r.id DESC LIMIT 100"""
        ).fetchall()
    return [dict(row) for row in rows]


def list_schedule_runs_for(schedule_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT r.*, s.owner_email, v.name AS view_name, v.report_key, v.kind AS view_kind
               FROM schedule_runs r
               JOIN schedules s ON s.id = r.schedule_id
               JOIN views v ON v.id = s.view_id
               WHERE r.schedule_id = ?
               ORDER BY r.id DESC""",
            (schedule_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_schedule_run(run_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute(
            """SELECT r.*, s.owner_email, v.name AS view_name, v.report_key, v.kind AS view_kind
               FROM schedule_runs r
               JOIN schedules s ON s.id = r.schedule_id
               JOIN views v ON v.id = s.view_id
               WHERE r.id = ?""",
            (run_id,),
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def set_user_groups(user_id: int, groups: list[str]) -> None:
    with db() as conn:
        conn.execute("DELETE FROM user_sales_groups WHERE user_id = ?", (user_id,))
        for group in groups:
            if group:
                conn.execute(
                    "INSERT OR IGNORE INTO user_sales_groups (user_id, sales_group) VALUES (?, ?)",
                    (user_id, group),
                )


def list_user_groups(user_id: int) -> list[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT sales_group FROM user_sales_groups WHERE user_id = ? ORDER BY sales_group",
            (user_id,),
        ).fetchall()
    return [row["sales_group"] for row in rows]


def report_access_map(user_id: int) -> dict[str, bool]:
    if not user_id:
        return {}
    with db() as conn:
        rows = conn.execute(
            "SELECT report_key, allowed FROM user_report_access WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {row["report_key"]: bool(row["allowed"]) for row in rows}


def set_report_access(user_id: int, report_key: str, mode: str) -> None:
    with db() as conn:
        conn.execute(
            "DELETE FROM user_report_access WHERE user_id = ? AND report_key = ?",
            (user_id, report_key),
        )
        if mode == "allow":
            conn.execute(
                "INSERT INTO user_report_access (user_id, report_key, allowed) VALUES (?, ?, 1)",
                (user_id, report_key),
            )
        elif mode == "deny":
            conn.execute(
                "INSERT INTO user_report_access (user_id, report_key, allowed) VALUES (?, ?, 0)",
                (user_id, report_key),
            )


def list_views_for_report(email: str, report_key: str, privileged: bool) -> list[dict]:
    with db() as conn:
        if privileged:
            rows = conn.execute(
                "SELECT * FROM views WHERE report_key = ? ORDER BY kind, name",
                (report_key,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM views WHERE report_key = ?
                   AND (owner_email = ? OR kind = 'company')
                   ORDER BY name""",
                (report_key, email),
            ).fetchall()
        return [_hydrate_view(row, conn) for row in rows]


def get_schedule(schedule_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute(
            """SELECT s.*, v.name AS view_name, v.report_key, v.kind AS view_kind
               FROM schedules s JOIN views v ON v.id = s.view_id
               WHERE s.id = ?""",
            (schedule_id,),
        ).fetchone()
        if row is None:
            return None
        return _attach_view_to_schedule(hydrate_schedule_row(row, conn), conn)


def test_emails() -> list[str]:
    raw = setting("test_emails", "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def set_test_emails(emails: list[str]) -> None:
    set_setting("test_emails", ",".join(emails))


def exclusions_for(email: str) -> list[str]:
    parsed = json.loads(setting(f"exclusions:{email.lower()}", "[]"))
    if not isinstance(parsed, list):
        raise ValueError(
            f"Customer exclusions for {email} must be a JSON list, got {type(parsed).__name__}."
        )
    return parsed


def mail_recipients(explicit: str) -> str:
    if setting("schedule_test_mode") == "1":
        return ", ".join(test_emails())
    return explicit


def set_exclusions(email: str, accounts: list[str]) -> None:
    set_setting(f"exclusions:{email.lower()}", json.dumps(accounts))


def prune_old_jobs(days: int = 90) -> int:
    with db() as conn:
        cur = conn.execute(
            """DELETE FROM jobs WHERE kept = 0
               AND datetime(created_at) < datetime('now', ?)""",
            (f"-{days} days",),
        )
        expired = conn.execute(
            """UPDATE jobs SET kept = 0, keep_name = '', kept_until = NULL
               WHERE kept = 1 AND kept_until IS NOT NULL
               AND datetime(kept_until) < datetime('now')"""
        )
        return cur.rowcount + expired.rowcount


def set_catch_up(schedule_id: int, pending: bool, for_date: str | None = None) -> None:
    with db() as conn:
        if not pending:
            conn.execute(
                "UPDATE schedules SET catch_up_pending = 0, catch_up_for_date = NULL WHERE id = ?",
                (schedule_id,),
            )
            return
        row = conn.execute(
            "SELECT catch_up_for_date FROM schedules WHERE id = ?",
            (schedule_id,),
        ).fetchone()
        existing = row["catch_up_for_date"] if row else None
        kept = existing
        if for_date:
            kept = min(x for x in (existing, for_date) if x) if existing else for_date
        conn.execute(
            "UPDATE schedules SET catch_up_pending = 1, catch_up_for_date = ? WHERE id = ?",
            (kept, schedule_id),
        )


def set_user_theme(user_id: int, theme: str) -> None:
    with db() as conn:
        conn.execute("UPDATE users SET theme = ? WHERE id = ?", (theme, user_id))


def abandon_orphan_runs() -> int:
    with db() as conn:
        cur = conn.execute(
            """UPDATE schedule_runs SET status = 'abandoned',
               message = 'Worker recycled before the run finished'
               WHERE status IN ('running', 'queued')"""
        )
        jobs = conn.execute(
            """UPDATE jobs SET status = 'abandoned'
               WHERE status IN ('running', 'queued')
               AND datetime(created_at) < datetime('now', '-45 minutes')"""
        )
        return cur.rowcount + jobs.rowcount
