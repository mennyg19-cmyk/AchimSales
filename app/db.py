"""SQLite for users, views, schedules, jobs, outbox — not sales facts."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from catalog import REPORTS
from config import PRODUCTION, db_path

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
    test_access INTEGER NOT NULL DEFAULT 0,
    theme TEXT NOT NULL DEFAULT 'light'
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
    include_period INTEGER NOT NULL DEFAULT 0,
    period TEXT,
    start_date TEXT,
    end_date TEXT,
    year TEXT,
    mode TEXT,
    active_tab_key TEXT
);
CREATE TABLE IF NOT EXISTS view_salesmen (
    view_id INTEGER NOT NULL REFERENCES views(id) ON DELETE CASCADE,
    salesman TEXT NOT NULL,
    PRIMARY KEY (view_id, salesman)
);
CREATE TABLE IF NOT EXISTS view_statuses (
    view_id INTEGER NOT NULL REFERENCES views(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    PRIMARY KEY (view_id, status)
);
CREATE TABLE IF NOT EXISTS view_customers (
    view_id INTEGER NOT NULL REFERENCES views(id) ON DELETE CASCADE,
    customer_account TEXT NOT NULL,
    PRIMARY KEY (view_id, customer_account)
);
CREATE TABLE IF NOT EXISTS layout_tabs (
    id INTEGER PRIMARY KEY,
    view_id INTEGER NOT NULL REFERENCES views(id) ON DELETE CASCADE,
    tab_key TEXT NOT NULL,
    position INTEGER,
    clone_of_tab_key TEXT,
    tab_name TEXT,
    has_view INTEGER NOT NULL DEFAULT 0,
    groups_explicit INTEGER NOT NULL DEFAULT 1,
    UNIQUE (view_id, tab_key)
);
CREATE TABLE IF NOT EXISTS layout_tab_groups (
    tab_id INTEGER NOT NULL REFERENCES layout_tabs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    column_name TEXT NOT NULL,
    PRIMARY KEY (tab_id, position)
);
CREATE TABLE IF NOT EXISTS layout_tab_sorters (
    tab_id INTEGER NOT NULL REFERENCES layout_tabs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    column_name TEXT NOT NULL,
    dir TEXT NOT NULL CHECK (dir IN ('asc', 'desc')),
    PRIMARY KEY (tab_id, position)
);
CREATE TABLE IF NOT EXISTS layout_columns (
    tab_id INTEGER NOT NULL REFERENCES layout_tabs(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    position INTEGER,
    hidden INTEGER NOT NULL DEFAULT 0,
    frozen INTEGER NOT NULL DEFAULT 0,
    width REAL,
    PRIMARY KEY (tab_id, field)
);
CREATE TABLE IF NOT EXISTS layout_column_filters (
    tab_id INTEGER NOT NULL REFERENCES layout_tabs(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    op TEXT NOT NULL DEFAULT 'contains',
    v TEXT,
    v2 TEXT,
    PRIMARY KEY (tab_id, field)
);
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY,
    view_id INTEGER NOT NULL,
    owner_email TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'personal',
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
    last_status TEXT,
    catch_up_pending INTEGER NOT NULL DEFAULT 0,
    catch_up_for_date TEXT,
    window_period TEXT,
    window_start TEXT,
    window_end TEXT
);
CREATE TABLE IF NOT EXISTS schedule_weekdays (
    schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    weekday INTEGER NOT NULL,
    PRIMARY KEY (schedule_id, weekday)
);
CREATE TABLE IF NOT EXISTS schedule_monthdays (
    schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    monthday INTEGER NOT NULL,
    PRIMARY KEY (schedule_id, monthday)
);
CREATE TABLE IF NOT EXISTS schedule_recipients (
    schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY (schedule_id, email, role)
);
CREATE TABLE IF NOT EXISTS schedule_email_salesmen (
    schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    salesman TEXT NOT NULL,
    PRIMARY KEY (schedule_id, salesman)
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    report_key TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    kept INTEGER NOT NULL DEFAULT 0,
    keep_name TEXT,
    kept_until TEXT,
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
SEED_EMAILS = {row[0] for row in SEED_USERS}
DUMMY_EMAIL_SUFFIXES = ("@local.test", "@test.local", "@example.com")


def is_dummy_email(email: str) -> bool:
    lower = (email or "").strip().lower()
    if not lower:
        return False
    if lower in SEED_EMAILS or lower.startswith("preview@"):
        return True
    if lower.startswith("loopa-") or lower.startswith("loopb-"):
        return True
    return lower.endswith(DUMMY_EMAIL_SUFFIXES)


def _in_clause(values: list) -> tuple[str, list]:
    return ",".join("?" for _ in values), list(values)


def _delete_views(conn: sqlite3.Connection, view_ids: list[int]) -> None:
    if not view_ids:
        return
    placeholders, values = _in_clause(view_ids)
    tab_ids = [
        row[0]
        for row in conn.execute(
            f"SELECT id FROM layout_tabs WHERE view_id IN ({placeholders})",
            values,
        )
    ]
    if tab_ids:
        tph, tvals = _in_clause(tab_ids)
        for table in (
            "layout_column_filters",
            "layout_columns",
            "layout_tab_groups",
            "layout_tab_sorters",
        ):
            conn.execute(f"DELETE FROM {table} WHERE tab_id IN ({tph})", tvals)
        conn.execute(f"DELETE FROM layout_tabs WHERE id IN ({tph})", tvals)
    for table in ("view_salesmen", "view_statuses", "view_customers"):
        conn.execute(f"DELETE FROM {table} WHERE view_id IN ({placeholders})", values)
    conn.execute(f"DELETE FROM views WHERE id IN ({placeholders})", values)


def _delete_schedules(conn: sqlite3.Connection, schedule_ids: list[int]) -> None:
    if not schedule_ids:
        return
    placeholders, values = _in_clause(schedule_ids)
    for table in (
        "schedule_runs",
        "schedule_weekdays",
        "schedule_monthdays",
        "schedule_recipients",
        "schedule_email_salesmen",
    ):
        conn.execute(f"DELETE FROM {table} WHERE schedule_id IN ({placeholders})", values)
    conn.execute(f"DELETE FROM schedules WHERE id IN ({placeholders})", values)


def purge_dummy_people(conn: sqlite3.Connection) -> int:
    """Remove preview/loop seed People and rows they own. Live company views stay."""
    dummy = [
        row
        for row in conn.execute("SELECT id, email FROM users").fetchall()
        if is_dummy_email(row["email"])
    ]
    removed = 0
    if dummy:
        emails = [row["email"].lower() for row in dummy]
        ids = [int(row["id"]) for row in dummy]
        placeholders, values = _in_clause(emails)
        view_ids = [
            int(row[0])
            for row in conn.execute(
                f"SELECT id FROM views WHERE lower(ifnull(owner_email, '')) IN ({placeholders})",
                values,
            )
        ]
        schedule_ids = [
            int(row[0])
            for row in conn.execute(
                f"SELECT id FROM schedules WHERE lower(ifnull(owner_email, '')) IN ({placeholders})",
                values,
            )
        ]
        _delete_schedules(conn, schedule_ids)
        _delete_views(conn, view_ids)
        conn.execute(f"DELETE FROM jobs WHERE lower(ifnull(owner_email, '')) IN ({placeholders})", values)
        id_ph, id_vals = _in_clause(ids)
        conn.execute(f"DELETE FROM user_sales_groups WHERE user_id IN ({id_ph})", id_vals)
        conn.execute(f"DELETE FROM user_report_access WHERE user_id IN ({id_ph})", id_vals)
        conn.execute(f"DELETE FROM users WHERE id IN ({id_ph})", id_vals)
        removed = len(ids)
    row = conn.execute("SELECT value FROM app_settings WHERE key = 'test_emails'").fetchone()
    if row:
        kept = [
            part.strip()
            for part in (row["value"] or "").split(",")
            if part.strip() and not is_dummy_email(part.strip())
        ]
        conn.execute(
            "UPDATE app_settings SET value = ? WHERE key = 'test_emails'",
            (",".join(kept),),
        )
        if not kept:
            conn.execute(
                "UPDATE app_settings SET value = '0' WHERE key = 'schedule_test_mode'"
            )
    return removed


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
        ensure_column("schedules", "catch_up_pending", "INTEGER NOT NULL DEFAULT 0")
        ensure_column("schedules", "catch_up_for_date", "TEXT")
        ensure_column("users", "theme", "TEXT NOT NULL DEFAULT 'light'")
        ensure_column("schedules", "name", "TEXT NOT NULL DEFAULT ''")
        ensure_column("schedules", "kind", "TEXT NOT NULL DEFAULT 'personal'")
        ensure_column("schedules", "split_by_salesman", "INTEGER NOT NULL DEFAULT 0")
        ensure_column("schedules", "email_to_salesmen", "INTEGER NOT NULL DEFAULT 0")
        ensure_column("schedules", "window_period", "TEXT")
        ensure_column("schedules", "window_start", "TEXT")
        ensure_column("schedules", "window_end", "TEXT")
        ensure_column("jobs", "kept_until", "TEXT")
        ensure_column("schedule_runs", "message", "TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "UPDATE schedules SET is_active = 0 WHERE ifnull(kind, '') = 'company'"
        )
        for name in (
            "saved_reports",
            "company_views",
            "report_defaults",
            "master_schedules",
            "view_workbook_parity",
        ):
            conn.execute(f"DROP TABLE IF EXISTS {name}")
        can_seed = (not PRODUCTION) and conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        if can_seed:
            for row in SEED_USERS:
                conn.execute(
                    """INSERT OR IGNORE INTO users
                       (email, display_name, role, is_active, is_external,
                        sales_group, can_see_company_views, sharepoint_access)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    row,
                )
        from views import migrate_params_json, save_filters_and_layout

        migrate_params_json(conn)
        if can_seed and conn.execute("SELECT COUNT(*) FROM views").fetchone()[0] == 0:
            conn.execute(
                """INSERT INTO views (owner_email, report_key, name, kind, include_period)
                   VALUES ('preview@achimonline.com', 'invoiced', 'Daily Invoiced', 'personal', 1)"""
            )
            invoiced_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            save_filters_and_layout(conn, invoiced_id, {"period": "last_7_days"}, None, 1)
            conn.execute(
                """INSERT INTO views (owner_email, report_key, name, kind, include_period)
                   VALUES (NULL, 'ordered', 'Daily Ordered', 'company', 1)"""
            )
            ordered_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            save_filters_and_layout(conn, ordered_id, {"period": "this_week"}, None, 1)
        for item in REPORTS:
            conn.execute(
                "INSERT OR IGNORE INTO report_visibility (report_key, enabled) VALUES (?, 1)",
                (item["key"],),
            )
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('schedule_test_mode', '0')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            ("test_emails", "preview@achimonline.com" if can_seed else ""),
        )
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('show_company_schedule_setup', '0')"
        )
        if can_seed and conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 0:
            view_id = conn.execute(
                "SELECT id FROM views WHERE name = 'Daily Ordered' AND kind = 'company'"
            ).fetchone()
            if view_id:
                conn.execute(
                    """INSERT INTO schedules (view_id, owner_email, name, kind, freq, run_time, recipients, is_active)
                       VALUES (?, 'preview@achimonline.com', 'Daily Ordered', 'personal', 'daily', '08:00', 'preview@achimonline.com', 1)""",
                    (view_id[0],),
                )
                sid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute(
                    """INSERT INTO schedule_recipients (schedule_id, email, role)
                       VALUES (?, 'preview@achimonline.com', 'to')""",
                    (sid,),
                )
