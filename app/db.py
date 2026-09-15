"""SQLite for users, views, schedules, jobs, outbox — not sales facts."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from catalog import REPORTS
from config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    is_external INTEGER NOT NULL DEFAULT 0,
    sales_group TEXT NOT NULL DEFAULT '',
    can_see_company_views INTEGER NOT NULL DEFAULT 0,
    sharepoint_access INTEGER NOT NULL DEFAULT 0,
    dashboard_enabled INTEGER NOT NULL DEFAULT 0,
    test_access INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS user_sales_groups (
    user_id INTEGER NOT NULL,
    sales_group TEXT NOT NULL,
    PRIMARY KEY (user_id, sales_group)
);
CREATE TABLE IF NOT EXISTS user_report_access (
    user_id INTEGER NOT NULL,
    report_key TEXT NOT NULL,
    allowed INTEGER NOT NULL,
    PRIMARY KEY (user_id, report_key)
);
CREATE TABLE IF NOT EXISTS report_visibility (
    report_key TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS views (
    id INTEGER PRIMARY KEY,
    owner_email TEXT,
    report_key TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'personal',
    params_json TEXT NOT NULL DEFAULT '{}',
    include_period INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY,
    view_id INTEGER NOT NULL,
    owner_email TEXT NOT NULL,
    freq TEXT NOT NULL,
    run_time TEXT NOT NULL DEFAULT '08:00',
    weekdays TEXT NOT NULL DEFAULT '',
    monthday INTEGER,
    recipients TEXT NOT NULL DEFAULT '',
    cc TEXT NOT NULL DEFAULT '',
    bcc TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '',
    sharepoint_folder TEXT NOT NULL DEFAULT '',
    onedrive_folder TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    last_run TEXT,
    last_status TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    report_key TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    kept INTEGER NOT NULL DEFAULT 0,
    keep_name TEXT,
    payload_json TEXT NOT NULL,
    owner_email TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    recipients TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schedule_runs (
    id INTEGER PRIMARY KEY,
    schedule_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lookup_cache (
    cache_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

SEED_USERS = (
    ("preview@achimonline.com", "Preview Admin", "admin", 1, 0, "", 1, 1),
    ("manager@achimonline.com", "Preview Manager", "manager", 1, 0, "", 1, 0),
    ("salesman@achimonline.com", "Preview Salesman", "salesman", 1, 0, "HKaufman", 0, 0),
    ("external@example.com", "Preview External", "salesman", 1, 1, "DDweck", 0, 0),
)


def _connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db():
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
    with db() as conn:
        conn.executescript(SCHEMA)
        user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "INTEGER" in user_cols:
            # one bad ALTER named the column INTEGER; drop it before adding real flags
            conn.execute('ALTER TABLE users DROP COLUMN "INTEGER"')

        def ensure_column(table: str, name: str, ddl: str) -> None:
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if name not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

        ensure_column("jobs", "owner_email", "TEXT NOT NULL DEFAULT ''")
        ensure_column("users", "dashboard_enabled", "INTEGER NOT NULL DEFAULT 0")
        ensure_column("users", "test_access", "INTEGER NOT NULL DEFAULT 0")
        ensure_column("schedules", "cc", "TEXT NOT NULL DEFAULT ''")
        ensure_column("schedules", "bcc", "TEXT NOT NULL DEFAULT ''")
        ensure_column("schedules", "subject", "TEXT NOT NULL DEFAULT ''")
        ensure_column("schedules", "filename", "TEXT NOT NULL DEFAULT ''")
        ensure_column("schedules", "sharepoint_folder", "TEXT NOT NULL DEFAULT ''")
        ensure_column("schedules", "onedrive_folder", "TEXT NOT NULL DEFAULT ''")
        for row in SEED_USERS:
            conn.execute(
                """INSERT OR IGNORE INTO users
                   (email, display_name, role, is_active, is_external,
                    sales_group, can_see_company_views, sharepoint_access)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                row,
            )
        if conn.execute("SELECT COUNT(*) FROM views").fetchone()[0] == 0:
            conn.execute(
                """INSERT INTO views (owner_email, report_key, name, kind, params_json, include_period)
                   VALUES ('preview@achimonline.com', 'invoiced', 'Daily Invoiced', 'personal',
                           '{"period":"last_7_days"}', 1)"""
            )
            conn.execute(
                """INSERT INTO views (owner_email, report_key, name, kind, params_json, include_period)
                   VALUES (NULL, 'ordered', 'Daily Ordered', 'company',
                           '{"period":"this_week"}', 1)"""
            )
        for item in REPORTS:
            conn.execute(
                "INSERT OR IGNORE INTO report_visibility (report_key, enabled) VALUES (?, 1)",
                (item["key"],),
            )
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('schedule_test_mode', '0')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('test_emails', 'preview@achimonline.com')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('show_company_schedule_setup', '0')"
        )
        if conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 0:
            view_id = conn.execute(
                "SELECT id FROM views WHERE name = 'Daily Ordered' AND kind = 'company'"
            ).fetchone()
            if view_id:
                conn.execute(
                    """INSERT INTO schedules (view_id, owner_email, freq, run_time, recipients, is_active)
                       VALUES (?, 'preview@achimonline.com', 'daily', '08:00', 'preview@achimonline.com', 1)""",
                    (view_id[0],),
                )
