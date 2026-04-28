"""SQLite layer for the v2 app.

All paths live under test/app.db -- completely separate from the live app.
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Iterator

from test.config.settings import APP_DB_PATH

log = logging.getLogger(__name__)

_lock = threading.Lock()


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS app_users (
        email                     TEXT PRIMARY KEY,
        display_name              TEXT,
        is_admin                  INTEGER NOT NULL DEFAULT 0,
        sharepoint_access_enabled INTEGER NOT NULL DEFAULT 0,
        first_login_utc           TEXT,
        last_login_utc            TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_email     TEXT PRIMARY KEY,
        theme          TEXT NOT NULL DEFAULT 'light',      -- light | dark
        landing_page   TEXT NOT NULL DEFAULT 'reports',    -- reports | dashboard | schedules
        default_tab    TEXT NOT NULL DEFAULT 'all',        -- all | presets
        updated_utc    TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_exclusions (
        user_email       TEXT NOT NULL,
        customer_account TEXT NOT NULL,
        PRIMARY KEY (user_email, customer_account)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS saved_reports (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email   TEXT    NOT NULL,
        name         TEXT    NOT NULL,
        report_key   TEXT    NOT NULL,
        report_name  TEXT    NOT NULL,
        params_json  TEXT    NOT NULL DEFAULT '{}',
        layouts_json TEXT    NOT NULL DEFAULT '{}',
        created_utc  TEXT    NOT NULL,
        UNIQUE(user_email, name)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_saved_reports_user
        ON saved_reports(user_email, created_utc DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS schedules (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email      TEXT    NOT NULL,
        name            TEXT    NOT NULL,
        report_key      TEXT    NOT NULL,
        report_name     TEXT    NOT NULL,
        params_json     TEXT    NOT NULL DEFAULT '{}',
        layouts_json    TEXT    NOT NULL DEFAULT '{}',
        cadence         TEXT    NOT NULL,
        weekdays        TEXT    NOT NULL DEFAULT '',
        monthdays       TEXT    NOT NULL DEFAULT '',
        time_hhmm       TEXT    NOT NULL,
        start_date      TEXT    NOT NULL,
        end_date        TEXT,
        recipients      TEXT    NOT NULL DEFAULT '',
        sharepoint_path TEXT,
        active          INTEGER NOT NULL DEFAULT 1,
        created_utc     TEXT    NOT NULL,
        last_run_utc    TEXT,
        next_run_utc    TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_schedules_user
        ON schedules(user_email, created_utc DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS master_schedules (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        report_key      TEXT    NOT NULL,
        report_name     TEXT    NOT NULL,
        params_json     TEXT    NOT NULL DEFAULT '{}',
        layouts_json    TEXT    NOT NULL DEFAULT '{}',
        cadence         TEXT    NOT NULL,
        weekdays        TEXT    NOT NULL DEFAULT '',
        monthdays       TEXT    NOT NULL DEFAULT '',
        time_hhmm       TEXT    NOT NULL,
        start_date      TEXT    NOT NULL,
        end_date        TEXT,
        recipients      TEXT    NOT NULL DEFAULT '',
        sharepoint_path TEXT,
        active          INTEGER NOT NULL DEFAULT 1,
        created_by      TEXT    NOT NULL,
        created_utc     TEXT    NOT NULL,
        updated_by      TEXT,
        updated_utc     TEXT,
        last_run_utc    TEXT,
        next_run_utc    TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_master_schedules_created
        ON master_schedules(created_utc DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS schedule_runs (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        schedule_type    TEXT    NOT NULL,     -- 'master' | 'personal'
        schedule_id      INTEGER NOT NULL,
        schedule_name    TEXT,
        report_key       TEXT,
        report_name      TEXT,
        triggered_by     TEXT,                 -- email of user, NULL for automatic
        started_utc      TEXT    NOT NULL,
        finished_utc     TEXT,
        status           TEXT    NOT NULL,     -- 'running' | 'success' | 'failed'
        rows_returned    INTEGER,
        email_sent       INTEGER NOT NULL DEFAULT 0,
        email_recipients TEXT,
        sharepoint_saved INTEGER NOT NULL DEFAULT 0,
        sharepoint_path  TEXT,
        error_message    TEXT,
        debug_log        TEXT    NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_schedule_runs_lookup
        ON schedule_runs(schedule_type, schedule_id, started_utc DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_schedule_runs_started
        ON schedule_runs(started_utc DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS report_run_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email      TEXT    NOT NULL,
        report_key      TEXT    NOT NULL,
        report_name     TEXT    NOT NULL,
        params_json     TEXT,
        rows_returned   INTEGER,
        duration_ms     INTEGER,
        status          TEXT    NOT NULL,  -- 'success' | 'failed'
        error_message   TEXT,
        started_utc     TEXT    NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_report_run_log_time
        ON report_run_log(started_utc DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_report_run_log_user
        ON report_run_log(user_email, started_utc DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS outbox (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email       TEXT    NOT NULL,
        report_key       TEXT    NOT NULL,
        report_name      TEXT    NOT NULL,
        subject          TEXT    NOT NULL,
        recipients       TEXT    NOT NULL,
        eml_path         TEXT    NOT NULL,
        sharepoint_saved INTEGER NOT NULL DEFAULT 0,
        sharepoint_path  TEXT,
        created_utc      TEXT    NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_outbox_user
        ON outbox(user_email, created_utc DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS feature_flags (
        flag_key    TEXT PRIMARY KEY,
        enabled     INTEGER NOT NULL DEFAULT 0,
        description TEXT
    )
    """,
]


# Columns added after the initial schema was shipped. Each entry is
# (table, column, column_def). Guarded by PRAGMA table_info so re-runs are safe.
_COLUMN_MIGRATIONS = [
    ("saved_reports", "layouts_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("app_users",     "sharepoint_access_enabled", "INTEGER NOT NULL DEFAULT 0"),
    ("schedules",     "sharepoint_path", "TEXT"),
    ("outbox",        "sharepoint_saved", "INTEGER NOT NULL DEFAULT 0"),
    ("outbox",        "sharepoint_path",  "TEXT"),
]


_DEFAULT_FEATURE_FLAGS = [
    ("dashboard_enabled", 1, "Show the Dashboard tab for all users"),
    ("sharepoint_enabled", 0, "Globally allow SharePoint saves (per-user flag also required)"),
]


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Bring existing DBs forward without a formal migration system."""
    for table, column, coldef in _COLUMN_MIGRATIONS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")
            log.info("%s: added %s column", table, column)


def _seed_feature_flags(conn: sqlite3.Connection) -> None:
    for key, enabled, desc in _DEFAULT_FEATURE_FLAGS:
        conn.execute(
            "INSERT OR IGNORE INTO feature_flags (flag_key, enabled, description) VALUES (?, ?, ?)",
            (key, enabled, desc),
        )


def _connect() -> sqlite3.Connection:
    APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(APP_DB_PATH), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextlib.contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist. Idempotent; safe on every boot."""
    with _lock, connect() as conn:
        for stmt in SCHEMA_STATEMENTS:
            conn.execute(stmt)
        _ensure_columns(conn)
        _seed_feature_flags(conn)
        log.info("v2 db initialized at %s", APP_DB_PATH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


# -- Preferences ------------------------------------------------------------

DEFAULT_PREFERENCES = {
    "theme": "light",
    "landing_page": "reports",
    "default_tab": "all",
}


def get_user_preferences(email: str) -> dict:
    email = _norm_email(email)
    if not email:
        return dict(DEFAULT_PREFERENCES)
    with connect() as conn:
        row = conn.execute(
            "SELECT theme, landing_page, default_tab FROM user_preferences WHERE user_email = ?",
            (email,),
        ).fetchone()
    if not row:
        return dict(DEFAULT_PREFERENCES)
    return {
        "theme":        row["theme"] or "light",
        "landing_page": row["landing_page"] or "reports",
        "default_tab":  row["default_tab"] or "all",
    }


def set_user_preferences(email: str, prefs: dict) -> None:
    email = _norm_email(email)
    if not email:
        return
    merged = {**DEFAULT_PREFERENCES, **get_user_preferences(email), **(prefs or {})}
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO user_preferences (user_email, theme, landing_page, default_tab, updated_utc)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_email) DO UPDATE SET
                theme        = excluded.theme,
                landing_page = excluded.landing_page,
                default_tab  = excluded.default_tab,
                updated_utc  = excluded.updated_utc
            """,
            (email, merged["theme"], merged["landing_page"], merged["default_tab"], _now_utc()),
        )


# -- Customer exclusions ----------------------------------------------------

def get_user_exclusions(email: str) -> list[str]:
    email = _norm_email(email)
    if not email:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT customer_account FROM user_exclusions WHERE user_email = ? ORDER BY customer_account",
            (email,),
        ).fetchall()
    return [r["customer_account"] for r in rows]


def set_user_exclusions(email: str, accounts: list[str]) -> None:
    email = _norm_email(email)
    if not email:
        return
    accounts = [a.strip() for a in (accounts or []) if a and a.strip()]
    with connect() as conn:
        conn.execute("DELETE FROM user_exclusions WHERE user_email = ?", (email,))
        if accounts:
            conn.executemany(
                "INSERT OR IGNORE INTO user_exclusions (user_email, customer_account) VALUES (?, ?)",
                [(email, a) for a in accounts],
            )


# -- App users / permissions ------------------------------------------------

def upsert_user_login(email: str, display_name: str | None = None) -> None:
    """Called on successful login. Creates row if absent, updates last_login."""
    email = _norm_email(email)
    if not email:
        return
    now = _now_utc()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO app_users (email, display_name, first_login_utc, last_login_utc)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                display_name   = COALESCE(excluded.display_name, app_users.display_name),
                last_login_utc = excluded.last_login_utc
            """,
            (email, display_name, now, now),
        )


def list_app_users() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT email, display_name, is_admin, sharepoint_access_enabled,
                   first_login_utc, last_login_utc
            FROM app_users
            ORDER BY is_admin DESC, email
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_app_user(email: str) -> dict | None:
    email = _norm_email(email)
    if not email:
        return None
    with connect() as conn:
        row = conn.execute(
            """
            SELECT email, display_name, is_admin, sharepoint_access_enabled,
                   first_login_utc, last_login_utc
            FROM app_users WHERE email = ?
            """,
            (email,),
        ).fetchone()
    return dict(row) if row else None


def update_app_user(email: str, *, display_name: str | None = None,
                    is_admin: bool | None = None,
                    sharepoint_access_enabled: bool | None = None) -> None:
    email = _norm_email(email)
    if not email:
        return
    sets, params = [], []
    if display_name is not None:
        sets.append("display_name = ?"); params.append(display_name)
    if is_admin is not None:
        sets.append("is_admin = ?"); params.append(1 if is_admin else 0)
    if sharepoint_access_enabled is not None:
        sets.append("sharepoint_access_enabled = ?")
        params.append(1 if sharepoint_access_enabled else 0)
    if not sets:
        return
    params.append(email)
    with connect() as conn:
        existing = conn.execute("SELECT 1 FROM app_users WHERE email = ?", (email,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO app_users (email) VALUES (?)", (email,)
            )
        conn.execute(f"UPDATE app_users SET {', '.join(sets)} WHERE email = ?", params)


def delete_app_user(email: str) -> None:
    email = _norm_email(email)
    if not email:
        return
    with connect() as conn:
        conn.execute("DELETE FROM app_users WHERE email = ?", (email,))


def has_sharepoint_access(email: str) -> bool:
    """Admins always pass. Otherwise check per-user flag."""
    u = get_app_user(email)
    if not u:
        return False
    if u.get("is_admin"):
        return True
    return bool(u.get("sharepoint_access_enabled"))


def is_admin_email(email: str) -> bool:
    u = get_app_user(email)
    return bool(u and u.get("is_admin"))


# -- Feature flags ----------------------------------------------------------

def list_feature_flags() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT flag_key, enabled, description FROM feature_flags ORDER BY flag_key"
        ).fetchall()
    return [dict(r) for r in rows]


def get_feature_flag(key: str, default: bool = False) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT enabled FROM feature_flags WHERE flag_key = ?", (key,)
        ).fetchone()
    return bool(row["enabled"]) if row else default


def set_feature_flag(key: str, enabled: bool) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO feature_flags (flag_key, enabled) VALUES (?, ?)
            ON CONFLICT(flag_key) DO UPDATE SET enabled = excluded.enabled
            """,
            (key, 1 if enabled else 0),
        )


# -- Master schedules -------------------------------------------------------

def _schedule_row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def list_master_schedules() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM master_schedules ORDER BY created_utc DESC"
        ).fetchall()
    return [_schedule_row_to_dict(r) for r in rows]


def get_master_schedule(schedule_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM master_schedules WHERE id = ?", (schedule_id,)
        ).fetchone()
    return _schedule_row_to_dict(row) if row else None


def create_master_schedule(data: dict, created_by: str) -> int:
    now = _now_utc()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO master_schedules
                (name, report_key, report_name, params_json, layouts_json,
                 cadence, weekdays, monthdays, time_hhmm,
                 start_date, end_date, recipients, sharepoint_path,
                 active, created_by, created_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                data["name"],
                data["report_key"],
                data["report_name"],
                data.get("params_json", "{}"),
                data.get("layouts_json", "{}"),
                data["cadence"],
                data.get("weekdays", ""),
                data.get("monthdays", ""),
                data["time_hhmm"],
                data["start_date"],
                data.get("end_date"),
                data.get("recipients", ""),
                data.get("sharepoint_path"),
                created_by,
                now,
            ),
        )
        return cur.lastrowid


def update_master_schedule(schedule_id: int, data: dict, updated_by: str) -> None:
    fields = [
        "name", "report_key", "report_name", "params_json", "layouts_json",
        "cadence", "weekdays", "monthdays", "time_hhmm",
        "start_date", "end_date", "recipients", "sharepoint_path", "active",
    ]
    sets, params = [], []
    for f in fields:
        if f in data:
            sets.append(f"{f} = ?"); params.append(data[f])
    if not sets:
        return
    sets.append("updated_by = ?"); params.append(updated_by)
    sets.append("updated_utc = ?"); params.append(_now_utc())
    params.append(schedule_id)
    with connect() as conn:
        conn.execute(
            f"UPDATE master_schedules SET {', '.join(sets)} WHERE id = ?", params
        )


def delete_master_schedule(schedule_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM master_schedules WHERE id = ?", (schedule_id,))


def update_master_schedule_last_run(schedule_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE master_schedules SET last_run_utc = ? WHERE id = ?",
            (_now_utc(), schedule_id),
        )


def update_personal_schedule_last_run(schedule_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE schedules SET last_run_utc = ? WHERE id = ?",
            (_now_utc(), schedule_id),
        )


# -- Schedule runs (history + debug log) ------------------------------------

def create_schedule_run(
    *, schedule_type: str, schedule_id: int,
    schedule_name: str | None = None,
    report_key: str | None = None, report_name: str | None = None,
    triggered_by: str | None = None,
) -> int:
    assert schedule_type in ("master", "personal")
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO schedule_runs
                (schedule_type, schedule_id, schedule_name, report_key, report_name,
                 triggered_by, started_utc, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'running')
            """,
            (schedule_type, schedule_id, schedule_name, report_key, report_name,
             triggered_by, _now_utc()),
        )
        return cur.lastrowid


def append_schedule_run_log(run_id: int, line: str) -> None:
    ts = _now_utc()
    stamped = f"[{ts}] {line}\n"
    with connect() as conn:
        conn.execute(
            "UPDATE schedule_runs SET debug_log = COALESCE(debug_log, '') || ? WHERE id = ?",
            (stamped, run_id),
        )


def finalize_schedule_run(
    run_id: int, *, status: str,
    rows_returned: int | None = None,
    email_sent: bool = False, email_recipients: str | None = None,
    sharepoint_saved: bool = False, sharepoint_path: str | None = None,
    error_message: str | None = None,
) -> None:
    assert status in ("success", "failed")
    with connect() as conn:
        conn.execute(
            """
            UPDATE schedule_runs
            SET finished_utc = ?, status = ?, rows_returned = ?,
                email_sent = ?, email_recipients = ?,
                sharepoint_saved = ?, sharepoint_path = ?,
                error_message = ?
            WHERE id = ?
            """,
            (_now_utc(), status, rows_returned,
             1 if email_sent else 0, email_recipients,
             1 if sharepoint_saved else 0, sharepoint_path,
             error_message, run_id),
        )


def get_schedule_runs(schedule_type: str, schedule_id: int, limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM schedule_runs
            WHERE schedule_type = ? AND schedule_id = ?
            ORDER BY started_utc DESC LIMIT ?
            """,
            (schedule_type, schedule_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_schedule_run(run_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM schedule_runs WHERE id = ?", (run_id,)
        ).fetchone()
    return dict(row) if row else None


# -- Report run log ---------------------------------------------------------

def log_report_run(
    *, user_email: str, report_key: str, report_name: str,
    params: dict | None, rows_returned: int | None,
    duration_ms: int | None, status: str,
    error_message: str | None = None,
) -> int:
    assert status in ("success", "failed")
    params_json = json.dumps(params or {}, default=str)
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO report_run_log
                (user_email, report_key, report_name, params_json,
                 rows_returned, duration_ms, status, error_message, started_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_norm_email(user_email), report_key, report_name, params_json,
             rows_returned, duration_ms, status, error_message, _now_utc()),
        )
        return cur.lastrowid


def get_report_run_log(limit: int = 500, user_email: str | None = None) -> list[dict]:
    sql = "SELECT * FROM report_run_log"
    params: list[Any] = []
    if user_email:
        sql += " WHERE user_email = ?"
        params.append(_norm_email(user_email))
    sql += " ORDER BY started_utc DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
