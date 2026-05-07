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
    # ---- Salesman map (replaces config/salesman_map.xlsx for the test app) ----
    # Mirrors the live Excel schema 1:1: identity (key/number/names/email),
    # commission %, plus per-report subscription flags and CC/BCC. Editable
    # entirely from the admin Settings page so we never have to redeploy
    # to update commissions or fix a salesman email.
    """
    CREATE TABLE IF NOT EXISTS app_salesmen (
        key            TEXT PRIMARY KEY,           -- normalized lookup key (lowercase, alnum-only)
        number         TEXT NOT NULL DEFAULT '',
        full_name      TEXT NOT NULL DEFAULT '',
        display_name   TEXT NOT NULL DEFAULT '',
        email          TEXT NOT NULL DEFAULT '',
        commission_pct REAL NOT NULL DEFAULT 0,
        cc             TEXT NOT NULL DEFAULT '',   -- semicolon-separated
        bcc            TEXT NOT NULL DEFAULT '',   -- semicolon-separated
        active         INTEGER NOT NULL DEFAULT 1,
        subs_json      TEXT NOT NULL DEFAULT '{}', -- {report_key: bool}
        updated_utc    TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_app_salesmen_active
        ON app_salesmen(active, full_name)
    """,
    # ---- Per-user report-access overrides (mirrors live user_report_access) ----
    """
    CREATE TABLE IF NOT EXISTS user_report_access (
        user_email  TEXT NOT NULL,
        report_key  TEXT NOT NULL,
        allowed     INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (user_email, report_key)
    )
    """,
    # ---- Per-manager assigned-salesmen list (mirrors live user_salesman_access) ----
    """
    CREATE TABLE IF NOT EXISTS user_salesman_access (
        user_email   TEXT NOT NULL,
        salesman_key TEXT NOT NULL,
        PRIMARY KEY (user_email, salesman_key)
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
    # ---- Live-app role/permission parity ----
    # role: admin | developer | manager | salesman (4 roles, same as live).
    # salesman_key: the lookup key into app_salesmen. Required for role=salesman.
    # is_external: signs in via emailed magic link instead of Microsoft.
    # active: shown in dropdowns; toggled off for ex-employees.
    # dashboard_enabled / test_access_enabled: per-user feature flags.
    ("app_users", "role",                "TEXT NOT NULL DEFAULT 'salesman'"),
    ("app_users", "salesman_key",        "TEXT"),
    ("app_users", "is_external",         "INTEGER NOT NULL DEFAULT 0"),
    ("app_users", "active",              "INTEGER NOT NULL DEFAULT 1"),
    ("app_users", "dashboard_enabled",   "INTEGER NOT NULL DEFAULT 1"),
    ("app_users", "test_access_enabled", "INTEGER NOT NULL DEFAULT 1"),
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


def _backfill_user_roles(conn: sqlite3.Connection) -> None:
    """For users created before the role column existed, derive the role
    from the legacy ``is_admin`` flag so admins keep their access.

    Rows whose role is empty (never set explicitly) get either ``admin``
    (if ``is_admin=1``) or ``salesman`` (default).
    """
    try:
        conn.execute(
            "UPDATE app_users SET role = 'admin' "
            " WHERE (role IS NULL OR role = '') AND is_admin = 1"
        )
        conn.execute(
            "UPDATE app_users SET role = 'salesman' "
            " WHERE role IS NULL OR role = ''"
        )
    except Exception:
        log.exception("backfill: app_users.role")


def _seed_salesmen_from_xlsx(conn: sqlite3.Connection) -> None:
    """Idempotent first-boot seed of the app_salesmen table.

    Runs only when the table is empty so an admin can edit rows without
    having them blown away by the next deploy. The xlsx in the live app
    is the canonical source of truth at seed time; after that the test
    app owns its own copy in SQLite.
    """
    row = conn.execute("SELECT COUNT(*) AS n FROM app_salesmen").fetchone()
    if row and row["n"]:
        return

    # The live xlsx loader lives at <repo_root>/config/salesman_excel.py.
    # Python's package resolution may shadow the bare ``config`` name with
    # the test app's own config package, so we load the live module by
    # absolute file path instead of relying on ``import config.*``.
    import importlib.util
    from pathlib import Path as _Path
    repo_root = _Path(__file__).resolve().parents[2]
    live_xlsx = repo_root / "config" / "salesman_excel.py"
    if not live_xlsx.is_file():
        log.warning("salesman_map seed: %s not found, skipping", live_xlsx)
        return

    try:
        spec = importlib.util.spec_from_file_location(
            "_live_salesman_excel", str(live_xlsx),
        )
        if not spec or not spec.loader:
            raise ImportError("no spec")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:
        log.warning("salesman_map seed: could not load live xlsx loader (%s); "
                    "skipping seed (admins can add rows manually).",
                    live_xlsx, exc_info=False)
        return

    load_salesman_map = getattr(mod, "load_salesman_map", None)
    if load_salesman_map is None:
        log.warning("salesman_map seed: load_salesman_map() not found; skipping")
        return

    try:
        recs = load_salesman_map()
    except Exception:
        log.exception("salesman_map seed: load_salesman_map() failed")
        return
    if not recs:
        log.info("salesman_map seed: live xlsx loaded 0 records (probably missing)")
        return
    now = _now_utc()
    for key, rec in recs.items():
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO app_salesmen
                  (key, number, full_name, display_name, email, commission_pct,
                   cc, bcc, active, subs_json, updated_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    key,
                    rec.number or "",
                    rec.full_name or "",
                    rec.display_name or "",
                    rec.email or "",
                    float(rec.commission_pct or 0.0),
                    "; ".join(rec.cc or []),
                    "; ".join(rec.bcc or []),
                    json.dumps(rec.subscriptions or {}),
                    now,
                ),
            )
        except Exception:
            log.exception("salesman_map seed: row %s failed", key)
    log.info("salesman_map seed: inserted %d rows from xlsx", len(recs))


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
        _backfill_user_roles(conn)
        _seed_salesmen_from_xlsx(conn)
        log.info("v2 db initialized at %s", APP_DB_PATH)
    # Ensure offline-fallback mirror tables exist (separate module so
    # the import doesn't add to the top-level circular import surface).
    try:
        from test.webapp.services.mirror import init_mirror_db
        init_mirror_db()
    except Exception:
        log.exception("init_db: mirror init failed (non-fatal)")


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


VALID_ROLES = ("admin", "developer", "manager", "salesman")


def _user_select_cols() -> str:
    return (
        "email, display_name, role, salesman_key, is_admin, sharepoint_access_enabled, "
        "is_external, active, dashboard_enabled, test_access_enabled, "
        "first_login_utc, last_login_utc"
    )


def _user_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["is_admin"]                  = bool(d.get("is_admin"))
    d["sharepoint_access_enabled"] = bool(d.get("sharepoint_access_enabled"))
    d["is_external"]               = bool(d.get("is_external"))
    d["active"]                    = bool(d.get("active", 1))
    d["dashboard_enabled"]         = bool(d.get("dashboard_enabled", 1))
    d["test_access_enabled"]       = bool(d.get("test_access_enabled", 1))
    return d


def list_app_users() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT {_user_select_cols()}
            FROM app_users
            ORDER BY CASE WHEN role IN ('admin','developer') THEN 0
                          WHEN role = 'manager' THEN 1
                          ELSE 2 END,
                     email
            """
        ).fetchall()
    return [_user_row_to_dict(r) for r in rows]


def get_app_user(email: str) -> dict | None:
    email = _norm_email(email)
    if not email:
        return None
    with connect() as conn:
        row = conn.execute(
            f"SELECT {_user_select_cols()} FROM app_users WHERE email = ?",
            (email,),
        ).fetchone()
    return _user_row_to_dict(row) if row else None


def add_app_user(
    email: str, *,
    role: str = "salesman", salesman_key: str | None = None,
    display_name: str | None = None, is_external: bool = False,
) -> bool:
    """Create a new app_users row. Returns False if the email already exists."""
    email = _norm_email(email)
    if not email or role not in VALID_ROLES:
        return False
    with connect() as conn:
        existing = conn.execute(
            "SELECT 1 FROM app_users WHERE email = ?", (email,),
        ).fetchone()
        if existing:
            return False
        conn.execute(
            """
            INSERT INTO app_users
              (email, role, salesman_key, display_name, is_admin, is_external,
               active, dashboard_enabled, test_access_enabled)
            VALUES (?, ?, ?, ?, ?, ?, 1, 1, 1)
            """,
            (
                email,
                role,
                (salesman_key or None),
                display_name,
                1 if role in ("admin", "developer") else 0,
                1 if is_external else 0,
            ),
        )
    return True


def update_app_user(email: str, **kwargs: Any) -> None:
    """Generic update. Accepts any combination of:

    display_name, role, salesman_key, is_admin, sharepoint_access_enabled,
    is_external, active, dashboard_enabled, test_access_enabled, new_email.
    """
    email = _norm_email(email)
    if not email:
        return

    int_fields = (
        "is_admin", "sharepoint_access_enabled", "is_external",
        "active", "dashboard_enabled", "test_access_enabled",
    )
    str_fields = ("display_name", "role", "salesman_key")

    if "role" in kwargs:
        new_role = kwargs["role"]
        if new_role not in VALID_ROLES:
            raise ValueError(f"Invalid role: {new_role}")
        # Keep is_admin in sync with role so legacy callers still work.
        kwargs.setdefault("is_admin", new_role in ("admin", "developer"))

    sets, params = [], []
    for f in str_fields:
        if f in kwargs:
            v = kwargs[f]
            sets.append(f"{f} = ?"); params.append(v if v else None)
    for f in int_fields:
        if f in kwargs:
            sets.append(f"{f} = ?"); params.append(1 if kwargs[f] else 0)

    new_email = kwargs.get("new_email")
    if new_email is not None:
        new_email = _norm_email(str(new_email))
        if not new_email or "@" not in new_email:
            raise ValueError("new_email must be a valid email")
        if new_email != email:
            sets.append("email = ?"); params.append(new_email)

    if not sets:
        return
    params.append(email)
    with connect() as conn:
        existing = conn.execute(
            "SELECT 1 FROM app_users WHERE email = ?", (email,),
        ).fetchone()
        if not existing:
            conn.execute("INSERT INTO app_users (email) VALUES (?)", (email,))
        conn.execute(
            f"UPDATE app_users SET {', '.join(sets)} WHERE email = ?", params,
        )
        if new_email and new_email != email:
            # Cascade rename to all rows keyed by user_email.
            for tbl, col in (
                ("user_preferences",   "user_email"),
                ("user_exclusions",    "user_email"),
                ("saved_reports",      "user_email"),
                ("schedules",          "user_email"),
                ("report_run_log",     "user_email"),
                ("outbox",             "user_email"),
                ("user_report_access", "user_email"),
                ("user_salesman_access","user_email"),
            ):
                try:
                    conn.execute(
                        f"UPDATE {tbl} SET {col} = ? WHERE {col} = ?",
                        (new_email, email),
                    )
                except sqlite3.OperationalError:
                    pass


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
    if not u:
        return False
    if u.get("role") in ("admin", "developer"):
        return True
    return bool(u.get("is_admin"))


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


# ---------------------------------------------------------------------------
# Salesman map (DB-backed; admins edit via Settings page)
# ---------------------------------------------------------------------------

import re as _re


def _norm_salesman_key(s: str) -> str:
    """Mirror the live ``_norm_key`` (lowercase, alphanumeric only)."""
    return _re.sub(r"[^a-z0-9]+", "", str(s or "").strip().lower())


def _split_email_list(s: str | None) -> list[str]:
    if not s:
        return []
    return [e.strip() for e in str(s).replace(",", ";").split(";") if e.strip()]


def _salesman_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    try:
        d["subscriptions"] = json.loads(d.get("subs_json") or "{}")
    except Exception:
        d["subscriptions"] = {}
    d["cc_list"]  = _split_email_list(d.get("cc"))
    d["bcc_list"] = _split_email_list(d.get("bcc"))
    d["active"]   = bool(d.get("active", 1))
    try:
        d["commission_pct"] = float(d.get("commission_pct") or 0.0)
    except Exception:
        d["commission_pct"] = 0.0
    return d


def list_salesman_map(*, active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM app_salesmen"
    params: list[Any] = []
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY full_name COLLATE NOCASE, key"
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_salesman_row_to_dict(r) for r in rows]


def get_salesman_record(key: str) -> dict | None:
    k = _norm_salesman_key(key)
    if not k:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM app_salesmen WHERE key = ?", (k,),
        ).fetchone()
    return _salesman_row_to_dict(row) if row else None


def upsert_salesman_record(data: dict) -> str:
    """Insert or update a salesman row. Returns the normalized key."""
    raw_key = data.get("key") or ""
    k = _norm_salesman_key(raw_key)
    if not k:
        raise ValueError("key is required")

    number       = str(data.get("number") or "").strip()
    full_name    = str(data.get("full_name") or "").strip()
    display_name = str(data.get("display_name") or "").strip() or full_name
    email        = str(data.get("email") or "").strip()
    try:
        commission_pct = float(data.get("commission_pct") or 0.0)
    except (TypeError, ValueError):
        commission_pct = 0.0
    cc  = "; ".join(_split_email_list(data.get("cc")))
    bcc = "; ".join(_split_email_list(data.get("bcc")))
    active = 1 if (data.get("active", True) in (True, 1, "1", "true", "True")) else 0

    subs = data.get("subscriptions") or {}
    if not isinstance(subs, dict):
        subs = {}
    subs = {str(k2): bool(v) for k2, v in subs.items()}
    subs_json = json.dumps(subs)

    now = _now_utc()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO app_salesmen
              (key, number, full_name, display_name, email, commission_pct,
               cc, bcc, active, subs_json, updated_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              number         = excluded.number,
              full_name      = excluded.full_name,
              display_name   = excluded.display_name,
              email          = excluded.email,
              commission_pct = excluded.commission_pct,
              cc             = excluded.cc,
              bcc            = excluded.bcc,
              active         = excluded.active,
              subs_json      = excluded.subs_json,
              updated_utc    = excluded.updated_utc
            """,
            (k, number, full_name, display_name, email, commission_pct,
             cc, bcc, active, subs_json, now),
        )
    return k


def delete_salesman_record(key: str) -> bool:
    k = _norm_salesman_key(key)
    if not k:
        return False
    with connect() as conn:
        cur = conn.execute("DELETE FROM app_salesmen WHERE key = ?", (k,))
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Per-user report-access overrides + per-manager assigned-salesmen list
# ---------------------------------------------------------------------------

def get_user_report_overrides(email: str) -> dict[str, bool]:
    """Returns ``{report_key: allowed}`` overrides for a user."""
    e = _norm_email(email)
    if not e:
        return {}
    with connect() as conn:
        rows = conn.execute(
            "SELECT report_key, allowed FROM user_report_access WHERE user_email = ?",
            (e,),
        ).fetchall()
    return {r["report_key"]: bool(r["allowed"]) for r in rows}


def set_user_report_override(email: str, report_key: str, allowed: bool) -> None:
    e = _norm_email(email)
    rk = (report_key or "").strip()
    if not e or not rk:
        return
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO user_report_access (user_email, report_key, allowed)
            VALUES (?, ?, ?)
            ON CONFLICT(user_email, report_key)
              DO UPDATE SET allowed = excluded.allowed
            """,
            (e, rk, 1 if allowed else 0),
        )


def clear_user_report_override(email: str, report_key: str) -> None:
    e = _norm_email(email)
    rk = (report_key or "").strip()
    if not e or not rk:
        return
    with connect() as conn:
        conn.execute(
            "DELETE FROM user_report_access WHERE user_email = ? AND report_key = ?",
            (e, rk),
        )


def get_user_salesman_access(email: str) -> list[str]:
    """Salesman keys a manager is allowed to run reports for."""
    e = _norm_email(email)
    if not e:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT salesman_key FROM user_salesman_access WHERE user_email = ?",
            (e,),
        ).fetchall()
    return [r["salesman_key"] for r in rows]


def set_user_salesman_access(email: str, keys: list[str]) -> None:
    """Replace the salesman-access set for a user with *keys*."""
    e = _norm_email(email)
    if not e:
        return
    cleaned = sorted({_norm_salesman_key(k) for k in (keys or []) if _norm_salesman_key(k)})
    with connect() as conn:
        conn.execute(
            "DELETE FROM user_salesman_access WHERE user_email = ?", (e,),
        )
        if cleaned:
            conn.executemany(
                "INSERT OR IGNORE INTO user_salesman_access (user_email, salesman_key) VALUES (?, ?)",
                [(e, k) for k in cleaned],
            )


def get_users_permission_grid(report_keys: list[str]) -> list[dict]:
    """Return every app_user with role/salesman info, per-report effective
    permissions, and (for managers) the assigned-salesmen list.

    *report_keys* is the canonical ordered list of report keys the UI
    cares about. Effective permissions:

      * admin/developer/manager → all reports allowed by default
      * salesman               → only reports that don't require admin
                                 (currently we treat all listed reports
                                 as available to salesmen unless an
                                 override says otherwise)
      * any per-user override wins
    """
    rk_list = list(report_keys or [])
    users = list_app_users()
    if not users:
        return []

    overrides_by_user: dict[str, dict[str, bool]] = {}
    sm_access_by_user: dict[str, list[str]] = {}
    salesmen_by_key: dict[str, dict] = {}
    with connect() as conn:
        for r in conn.execute(
            "SELECT user_email, report_key, allowed FROM user_report_access"
        ).fetchall():
            overrides_by_user.setdefault(r["user_email"], {})[r["report_key"]] = bool(r["allowed"])
        for r in conn.execute(
            "SELECT user_email, salesman_key FROM user_salesman_access"
        ).fetchall():
            sm_access_by_user.setdefault(r["user_email"], []).append(r["salesman_key"])
        for r in conn.execute(
            "SELECT key, number, full_name FROM app_salesmen"
        ).fetchall():
            salesmen_by_key[r["key"]] = dict(r)

    enriched = []
    for u in users:
        d = dict(u)
        ovr = overrides_by_user.get(d["email"], {})
        is_priv = d.get("role") in ("admin", "developer", "manager")

        reports: dict[str, bool] = {}
        for rk in rk_list:
            if rk in ovr:
                reports[rk] = ovr[rk]
            else:
                reports[rk] = True if is_priv else True
        d["reports"] = reports
        d["allowed_salesmen"] = sm_access_by_user.get(d["email"], [])

        sm = salesmen_by_key.get(d.get("salesman_key") or "")
        d["sm_number"] = sm["number"] if sm else None
        d["sm_name"]   = sm["full_name"] if sm else None
        enriched.append(d)
    return enriched
