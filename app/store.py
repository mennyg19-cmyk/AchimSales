"""Read/write helpers for sqlite. Sales facts stay in catalog mocks."""

from __future__ import annotations

import json
from datetime import datetime, timezone

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
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
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


def list_views(email: str, privileged: bool) -> list[dict]:
    with db() as conn:
        if privileged:
            rows = conn.execute("SELECT * FROM views ORDER BY kind, name").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM views WHERE owner_email = ? OR kind = 'company' ORDER BY name",
                (email,),
            ).fetchall()
    return [dict(row) for row in rows]


def add_view(owner_email: str | None, report_key: str, name: str, kind: str, params: dict, include_period: int) -> int:
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO views (owner_email, report_key, name, kind, params_json, include_period)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (owner_email, report_key, name, kind, json.dumps(params), include_period),
        )
        return int(cur.lastrowid)


def get_view(view_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM views WHERE id = ?", (view_id,)).fetchone()
    if row is None:
        return None
    out = dict(row)
    out["params"] = json.loads(out.pop("params_json") or "{}")
    return out


def delete_view(view_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM views WHERE id = ?", (view_id,))


def save_job(report_key: str, title: str, payload: dict, kept: int = 0, keep_name: str | None = None) -> int:
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO jobs (report_key, title, status, created_at, kept, keep_name, payload_json)
               VALUES (?, ?, 'success', ?, ?, ?, ?)""",
            (report_key, title, now_iso(), kept, keep_name, json.dumps(payload)),
        )
        return int(cur.lastrowid)


def keep_job(job_id: int, name: str) -> None:
    with db() as conn:
        conn.execute("UPDATE jobs SET kept = 1, keep_name = ? WHERE id = ?", (name, job_id))


def list_jobs(kept_only: bool = False) -> list[dict]:
    sql = "SELECT id, report_key, title, status, created_at, kept, keep_name FROM jobs"
    if kept_only:
        sql += " WHERE kept = 1"
    sql += " ORDER BY id DESC LIMIT 30"
    with db() as conn:
        rows = conn.execute(sql).fetchall()
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


def list_schedules() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT s.*, v.name AS view_name, v.report_key
               FROM schedules s JOIN views v ON v.id = s.view_id
               ORDER BY s.id"""
        ).fetchall()
    return [dict(row) for row in rows]


def add_schedule(view_id: int, owner_email: str, freq: str, run_time: str, recipients: str) -> int:
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO schedules (view_id, owner_email, freq, run_time, recipients, is_active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (view_id, owner_email, freq, run_time, recipients),
        )
        return int(cur.lastrowid)


def toggle_schedule(schedule_id: int) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE schedules SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE id = ?",
            (schedule_id,),
        )


def delete_schedule(schedule_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))


def mark_schedule_run(schedule_id: int, status: str, message: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE schedules SET last_run = ?, last_status = ? WHERE id = ?",
            (now_iso(), status, schedule_id),
        )
        conn.execute(
            "INSERT INTO schedule_runs (schedule_id, started_at, status, message) VALUES (?, ?, ?, ?)",
            (schedule_id, now_iso(), status, message),
        )


def list_schedule_runs() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT r.*, s.owner_email, v.name AS view_name, v.report_key
               FROM schedule_runs r
               JOIN schedules s ON s.id = r.schedule_id
               JOIN views v ON v.id = s.view_id
               ORDER BY r.id DESC LIMIT 100"""
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_by_id(user_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def user_groups(user_id: int) -> list[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT sales_group FROM user_sales_groups WHERE user_id = ? ORDER BY sales_group",
            (user_id,),
        ).fetchall()
    return [row["sales_group"] for row in rows]


def set_user_groups(user_id: int, groups: list[str]) -> None:
    with db() as conn:
        conn.execute("DELETE FROM user_sales_groups WHERE user_id = ?", (user_id,))
        for group in groups:
            if group:
                conn.execute(
                    "INSERT OR IGNORE INTO user_sales_groups (user_id, sales_group) VALUES (?, ?)",
                    (user_id, group),
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
    out = []
    for row in rows:
        item = dict(row)
        item["params"] = json.loads(item.pop("params_json") or "{}")
        out.append(item)
    return out


def update_view(view_id: int, name: str, params: dict, include_period: int) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE views SET name = ?, params_json = ?, include_period = ? WHERE id = ?",
            (name, json.dumps(params), include_period, view_id),
        )


def get_schedule(schedule_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute(
            """SELECT s.*, v.name AS view_name, v.report_key, v.params_json, v.kind AS view_kind
               FROM schedules s JOIN views v ON v.id = s.view_id
               WHERE s.id = ?""",
            (schedule_id,),
        ).fetchone()
    if row is None:
        return None
    out = dict(row)
    out["params"] = json.loads(out.pop("params_json") or "{}")
    return out


def test_emails() -> list[str]:
    raw = setting("test_emails", "preview@achimonline.com")
    return [part.strip() for part in raw.split(",") if part.strip()]


def set_test_emails(emails: list[str]) -> None:
    set_setting("test_emails", ",".join(emails))


def exclusions_for(email: str) -> list[str]:
    raw = setting(f"exclusions:{email.lower()}", "[]")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def set_exclusions(email: str, accounts: list[str]) -> None:
    set_setting(f"exclusions:{email.lower()}", json.dumps(accounts))


def prune_old_jobs(days: int = 90) -> int:
    with db() as conn:
        cur = conn.execute(
            """DELETE FROM jobs WHERE kept = 0
               AND datetime(created_at) < datetime('now', ?)""",
            (f"-{days} days",),
        )
        return cur.rowcount


def abandon_orphan_runs() -> int:
    with db() as conn:
        cur = conn.execute(
            """UPDATE schedule_runs SET status = 'abandoned',
               message = 'Worker recycled before the run finished'
               WHERE status IN ('running', 'queued')"""
        )
        return cur.rowcount


def delete_job(job_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ? AND kept = 0", (job_id,))
