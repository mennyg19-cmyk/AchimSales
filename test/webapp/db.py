"""SQLite layer for the v2 app.

All paths live under test/app.db -- completely separate from the live app.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
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
    CREATE TABLE IF NOT EXISTS notifications (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email    TEXT NOT NULL,
        type          TEXT NOT NULL,
        title         TEXT NOT NULL,
        message       TEXT NOT NULL DEFAULT '',
        data          TEXT NOT NULL DEFAULT '{}',
        dismissed     INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT NOT NULL,
        dismissed_at  TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_notifications_user
        ON notifications(user_email, dismissed, created_at DESC)
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
    # Trimmed schema: identity (key/number/names/email), commission %, and
    # active flag. CC/BCC and per-report subscriptions live on the email
    # schedules, not here. Every salesman row MUST have an email -- a
    # salesman without an email isn't a real user we can talk to. The
    # boot-time prune in ``_prune_salesmen_without_email`` enforces this.
    """
    CREATE TABLE IF NOT EXISTS app_salesmen (
        key            TEXT PRIMARY KEY,           -- normalized lookup key (lowercase, alnum-only)
        number         TEXT NOT NULL DEFAULT '',
        full_name      TEXT NOT NULL DEFAULT '',
        display_name   TEXT NOT NULL DEFAULT '',
        email          TEXT NOT NULL DEFAULT '',
        commission_pct REAL NOT NULL DEFAULT 0,
        active         INTEGER NOT NULL DEFAULT 1,
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
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_payload_cache (
        cache_key     TEXT PRIMARY KEY,
        kind          TEXT NOT NULL,
        identity      TEXT NOT NULL DEFAULT '',
        user_scope    TEXT NOT NULL DEFAULT '',
        params_hash   TEXT NOT NULL DEFAULT '',
        payload_json  TEXT NOT NULL,
        source_json   TEXT NOT NULL DEFAULT '{}',
        created_utc   TEXT NOT NULL,
        refreshed_utc TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_api_payload_cache_lookup
        ON api_payload_cache(kind, identity, user_scope, refreshed_utc DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS api_async_jobs (
        job_id       TEXT PRIMARY KEY,
        cache_key    TEXT NOT NULL,
        kind         TEXT NOT NULL,
        identity     TEXT NOT NULL DEFAULT '',
        user_scope   TEXT NOT NULL DEFAULT '',
        status       TEXT NOT NULL,
        started_utc  TEXT NOT NULL,
        finished_utc TEXT,
        error        TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_api_async_jobs_cache
        ON api_async_jobs(cache_key, started_utc DESC)
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


def _drop_obsolete_dashboard_caches(conn: sqlite3.Connection) -> None:
    """Dashboard now derives from endpoint mirrors; remove old duplicate caches."""
    conn.execute("DROP TABLE IF EXISTS dashboard_order_cache")
    conn.execute("DROP TABLE IF EXISTS dashboard_cache")


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
        conn.execute(
            "UPDATE app_users SET is_admin = 1 "
            " WHERE role IN ('admin', 'developer')"
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
    inserted = skipped = 0
    for key, rec in recs.items():
        # Salesmen without an email aren't real users for us -- skip
        # them at seed so the merged Users & Permissions list stays
        # clean. Admins can add them manually if needed.
        email = (rec.email or "").strip()
        if not email:
            skipped += 1
            continue
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO app_salesmen
                  (key, number, full_name, display_name, email, commission_pct,
                   active, updated_utc)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    key,
                    rec.number or "",
                    rec.full_name or "",
                    rec.display_name or "",
                    email,
                    float(rec.commission_pct or 0.0),
                    now,
                ),
            )
            inserted += 1
        except Exception:
            log.exception("salesman_map seed: row %s failed", key)
    log.info(
        "salesman_map seed: inserted %d rows from xlsx (skipped %d without email)",
        inserted, skipped,
    )


def _prune_salesmen_without_email(conn: sqlite3.Connection) -> None:
    """Remove any app_salesmen rows that don't have an email.

    Idempotent. Runs on every boot so a stray ``UPDATE`` that blanks the
    email column gets self-healed and we never end up with dropdown
    entries for unreachable phantoms. Anything pruned here also removes
    the corresponding user (since the salesman key was the user's link
    to their identity) and any manager-assignment overrides that
    referenced it.
    """
    try:
        rows = conn.execute(
            "SELECT key FROM app_salesmen WHERE email IS NULL OR email = ''"
        ).fetchall()
    except Exception:
        return
    if not rows:
        return
    for r in rows:
        sk = r["key"]
        try:
            conn.execute("DELETE FROM app_salesmen WHERE key = ?", (sk,))
            # Remove the linked user -- a salesman without an email
            # cannot have signed in / received a magic link.
            conn.execute(
                "DELETE FROM app_users WHERE role = 'salesman' AND salesman_key = ?",
                (sk,),
            )
            conn.execute(
                "DELETE FROM user_salesman_access WHERE salesman_key = ?",
                (sk,),
            )
        except Exception:
            log.exception("prune salesmen: failed for key=%s", sk)
    log.info("prune salesmen: removed %d rows without email", len(rows))


def _sync_salesman_users(conn: sqlite3.Connection) -> None:
    """For every salesman row, make sure an app_users row exists with
    role=salesman and salesman_key=<key>. Idempotent.

    We use email as the user primary key, so:
      * if a user with that email already exists, update its role to
        salesman and link it to the salesman row;
      * if not, create a fresh row.

    Manual admin/developer/manager users keep their roles; we only
    promote to salesman when the existing role would otherwise be
    'salesman' anyway, or when it's empty (no role assigned yet).
    """
    try:
        rows = conn.execute(
            "SELECT key, full_name, display_name, email FROM app_salesmen "
            "WHERE email IS NOT NULL AND email != ''"
        ).fetchall()
    except Exception:
        return
    created = linked = 0
    for r in rows:
        email = (r["email"] or "").strip().lower()
        if not email:
            continue
        existing = conn.execute(
            "SELECT email, role, salesman_key FROM app_users WHERE email = ?",
            (email,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO app_users
                  (email, display_name, role, salesman_key, is_admin, is_external,
                   active, dashboard_enabled, test_access_enabled)
                VALUES (?, ?, 'salesman', ?, 0, 0, 1, 1, 1)
                """,
                (email, r["display_name"] or r["full_name"] or None, r["key"]),
            )
            created += 1
        else:
            # Only auto-link when the user has no salesman_key yet OR
            # already points at a (possibly stale) salesman. We never
            # overwrite an admin/developer/manager account that just
            # happens to share an email with a salesman row.
            cur_role = (existing["role"] or "").strip().lower()
            cur_key  = (existing["salesman_key"] or "").strip()
            if cur_role in ("", "salesman") and cur_key != r["key"]:
                conn.execute(
                    "UPDATE app_users SET role = 'salesman', salesman_key = ? "
                    "WHERE email = ?",
                    (r["key"], email),
                )
                linked += 1
    if created or linked:
        log.info(
            "salesman/user sync: created %d new user rows, linked %d existing",
            created, linked,
        )


# Connect-time setup that only needs to run once per process. On
# Azure App Service the DB lives on the SMB-mounted /home/, where
# every open()/close() carries real network latency; a dashboard
# render that did ~13 fresh connects added up to 20+ seconds just
# in connection setup. Once the schema is up the only thing we need
# per connection is the PRAGMAs that aren't persisted in the DB
# header.
_connect_setup_done = False


def _apply_pragmas(conn: sqlite3.Connection, *, first_time: bool) -> None:
    """Best-effort PRAGMA tuning.

    Every PRAGMA is wrapped individually so one failure (e.g. a
    read-only mount that won't let us write the WAL sidecar files)
    can't kill the connection. The defaults SQLite picks if any of
    these fail are still functional, just slower.
    """
    pragmas: list[str] = [
        "PRAGMA foreign_keys = ON",
        "PRAGMA busy_timeout = 30000",
        # WAL + synchronous=NORMAL is the standard "fast on slow disk"
        # combo: readers/writers run concurrently and we skip fsync
        # after every commit. Durability across power loss is still
        # preserved within WAL semantics (checkpoint syncs).
        "PRAGMA synchronous = NORMAL",
        "PRAGMA temp_store = MEMORY",
        # 64 MB per-connection page cache. Keeps the dashboard's
        # GROUP BY over 85k salesline rows in memory after the first
        # hit.
        "PRAGMA cache_size = -65536",
    ]
    if first_time:
        # journal_mode persists in the DB header; only set it once.
        pragmas.append("PRAGMA journal_mode = WAL")
    for stmt in pragmas:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            log.warning("pragma failed (continuing): %s", stmt, exc_info=True)


def _connect() -> sqlite3.Connection:
    global _connect_setup_done
    if not _connect_setup_done:
        APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(APP_DB_PATH), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn, first_time=not _connect_setup_done)
    _connect_setup_done = True
    return conn


# Per-request connection cache. A single dashboard render fires
# ~13 helper calls that each opened their own SQLite handle; sharing
# one handle across the request collapses that to 1 open + 1 close.
# Falls back to a fresh connect outside a request context (worker
# threads, the mirror refresh, the scheduler, etc.) so we never
# accidentally share a connection across threads.
@contextlib.contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    try:
        from flask import g, has_request_context
    except Exception:
        has_request_context = lambda: False  # noqa: E731
        g = None  # type: ignore[assignment]

    if has_request_context():
        cached = getattr(g, "_v2_sqlite_conn", None)
        if cached is None:
            cached = _connect()
            g._v2_sqlite_conn = cached
        try:
            yield cached
            # Each `with connect()` block is still its own atomic unit;
            # we just don't tear down the underlying socket between
            # them. sqlite3's implicit-BEGIN model means the next call
            # that issues an INSERT/UPDATE just opens a fresh
            # transaction.
            cached.commit()
        except Exception:
            cached.rollback()
            raise
        # Deliberately do NOT close on the inner exit -- the Flask
        # teardown hook closes the shared connection once the whole
        # request finishes.
        return

    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def teardown_request_connection(exc: BaseException | None = None) -> None:
    """Flask teardown hook: close the per-request SQLite connection.

    Registered from ``create_app`` so the request-scoped connection
    opened above is reliably released no matter how the request
    exits (success, exception, or aborted response).
    """
    try:
        from flask import g
    except Exception:
        return
    conn = getattr(g, "_v2_sqlite_conn", None)
    if conn is None:
        return
    try:
        if exc is not None:
            conn.rollback()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass
    try:
        delattr(g, "_v2_sqlite_conn")
    except Exception:
        pass


def init_db() -> None:
    """Create tables if they don't exist. Idempotent; safe on every boot."""
    with _lock, connect() as conn:
        for stmt in SCHEMA_STATEMENTS:
            conn.execute(stmt)
        _ensure_columns(conn)
        _drop_obsolete_dashboard_caches(conn)
        _seed_feature_flags(conn)
        _backfill_user_roles(conn)
        _seed_salesmen_from_xlsx(conn)
        _prune_salesmen_without_email(conn)
        _sync_salesman_users(conn)
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


def normalize_key(value: str | None) -> str:
    """Normalize a salesman key / sales group for comparison."""
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def get_app_setting(key: str) -> str | None:
    key = (key or "").strip()
    if not key:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else None


def get_app_settings_batch(keys: list[str]) -> dict[str, str | None]:
    """Read multiple ``app_settings`` rows in one connection.

    Returns ``{key: value_or_None}`` for every requested key. The
    dashboard refresh-status panel reads ~7 settings per page render;
    batching them collapses 7 connections + 7 SELECTs into one of
    each. On OneDrive-hosted SQLite that's the difference between a
    snappy page and a noticeably slow one.
    """
    cleaned = [(k or "").strip() for k in keys]
    cleaned = [k for k in cleaned if k]
    if not cleaned:
        return {}
    placeholders = ",".join("?" for _ in cleaned)
    out: dict[str, str | None] = {k: None for k in cleaned}
    with connect() as conn:
        rows = conn.execute(
            f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})",
            cleaned,
        ).fetchall()
    for r in rows:
        out[r["key"]] = r["value"]
    return out


def set_app_setting(key: str, value: str) -> None:
    key = (key or "").strip()
    if not key:
        return
    val = value if value is not None else ""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, val),
        )


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


# -- Notifications ----------------------------------------------------------

def add_notification(
    user_email: str,
    ntype: str,
    title: str,
    message: str = "",
    data: dict | None = None,
) -> int | None:
    """Insert a notification and return its id."""
    email = _norm_email(user_email)
    ntype = (ntype or "").strip()
    title = (title or "").strip()
    if not email or not ntype or not title:
        return None
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO notifications (user_email, type, title, message, data, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (email, ntype, title, message or "", json.dumps(data or {}), _now_utc()),
        )
        return int(cur.lastrowid)


def get_notifications(user_email: str, dismissed: bool = False) -> list[dict]:
    """Return notifications for a user, newest first."""
    email = _norm_email(user_email)
    if not email:
        return []
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, type, title, message, data, dismissed, created_at
            FROM notifications
            WHERE user_email = ? AND dismissed = ?
            ORDER BY created_at DESC
            """,
            (email, 1 if dismissed else 0),
        ).fetchall()
    out: list[dict] = []
    for row in rows:
        item = dict(row)
        try:
            item["data"] = json.loads(item.get("data") or "{}")
        except json.JSONDecodeError:
            item["data"] = {}
        out.append(item)
    return out


def get_notification_counts(user_email: str) -> dict[str, int]:
    """Return unread notification counts by type plus total."""
    email = _norm_email(user_email)
    if not email:
        return {"total": 0}
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT type, COUNT(*) AS cnt
            FROM notifications
            WHERE user_email = ? AND dismissed = 0
            GROUP BY type
            """,
            (email,),
        ).fetchall()
    counts = {str(r["type"]): int(r["cnt"] or 0) for r in rows}
    counts["total"] = sum(counts.values())
    return counts


def dismiss_notification(notification_id: int, user_email: str | None = None) -> None:
    """Mark one notification as dismissed, optionally scoped to its owner."""
    email = _norm_email(user_email or "")
    now = _now_utc()
    with connect() as conn:
        if email:
            conn.execute(
                """
                UPDATE notifications
                SET dismissed = 1, dismissed_at = ?
                WHERE id = ? AND user_email = ?
                """,
                (now, notification_id, email),
            )
        else:
            conn.execute(
                "UPDATE notifications SET dismissed = 1, dismissed_at = ? WHERE id = ?",
                (now, notification_id),
            )


def dismiss_notifications_by_type(user_email: str, ntype: str) -> None:
    """Dismiss all unread notifications of a given type for the user."""
    email = _norm_email(user_email)
    ntype = (ntype or "").strip()
    if not email or not ntype:
        return
    with connect() as conn:
        conn.execute(
            """
            UPDATE notifications
            SET dismissed = 1, dismissed_at = ?
            WHERE user_email = ? AND type = ? AND dismissed = 0
            """,
            (_now_utc(), email, ntype),
        )


def dismiss_all_notifications(user_email: str) -> None:
    """Dismiss all unread notifications for the user."""
    email = _norm_email(user_email)
    if not email:
        return
    with connect() as conn:
        conn.execute(
            """
            UPDATE notifications
            SET dismissed = 1, dismissed_at = ?
            WHERE user_email = ? AND dismissed = 0
            """,
            (_now_utc(), email),
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
    role = (d.get("role") or "").strip().lower()
    d["is_admin"]                  = bool(d.get("is_admin")) or role in ("admin", "developer")
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
    """Create a new app_users row.

    Returns False if the email already exists. Raises ``ValueError`` for
    invalid input.

    Salesman users are 1:1 with ``app_salesmen`` rows; the recommended
    way to add one is ``upsert_salesman_record`` (which creates both
    rows). When this function is called with ``role='salesman'`` it
    requires an existing salesman_key and silently aligns the email
    with that salesman's email.
    """
    email = _norm_email(email)
    if not email:
        raise ValueError("email is required")
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of {VALID_ROLES}")
    with connect() as conn:
        if role == "salesman":
            if not salesman_key:
                raise ValueError(
                    "Add a salesman via the Salesman flow -- it creates the "
                    "user automatically."
                )
            sm = conn.execute(
                "SELECT email FROM app_salesmen WHERE key = ?", (salesman_key,),
            ).fetchone()
            if not sm or not sm["email"]:
                raise ValueError(f"Unknown salesman key: {salesman_key}")
            sm_email = sm["email"].strip().lower()
            if sm_email and sm_email != email:
                # Trust the salesman row as the source of truth for
                # email so we don't end up with two users for one
                # salesman.
                email = sm_email
        if is_external and role != "salesman":
            raise ValueError("External (magic-link) login is only for salesmen")
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

        # Mirror identity-style edits back to the linked salesman row,
        # but ONLY when the caller was acting on a salesman user. We
        # use the post-update salesman_key so a fresh role assignment
        # picks up the link too.
        target_email = new_email if (new_email and new_email != email) else email
        post = conn.execute(
            "SELECT role, salesman_key, display_name, active "
            "FROM app_users WHERE email = ?", (target_email,),
        ).fetchone()
        if post and (post["role"] or "").lower() == "salesman" and post["salesman_key"]:
            sk = post["salesman_key"]
            sm_sets, sm_params = [], []
            if new_email and new_email != email:
                sm_sets.append("email = ?"); sm_params.append(target_email)
            if "display_name" in kwargs and post["display_name"]:
                sm_sets.append("display_name = ?")
                sm_params.append(post["display_name"])
            if "active" in kwargs:
                sm_sets.append("active = ?"); sm_params.append(int(post["active"] or 0))
            if sm_sets:
                sm_params.append(sk)
                try:
                    conn.execute(
                        f"UPDATE app_salesmen SET {', '.join(sm_sets)}, "
                        f"updated_utc = '{_now_utc()}' WHERE key = ?",
                        sm_params,
                    )
                except sqlite3.OperationalError:
                    log.exception("update_app_user: salesman mirror failed")


def delete_app_user(email: str) -> None:
    """Delete a user. If the user is a salesman, also delete the
    paired ``app_salesmen`` row (the relationship is 1:1 in this app).
    """
    email = _norm_email(email)
    if not email:
        return
    with connect() as conn:
        row = conn.execute(
            "SELECT role, salesman_key FROM app_users WHERE email = ?", (email,),
        ).fetchone()
        conn.execute("DELETE FROM app_users WHERE email = ?", (email,))
        if row and (row["role"] or "").lower() == "salesman" and row["salesman_key"]:
            sk = row["salesman_key"]
            conn.execute("DELETE FROM app_salesmen WHERE key = ?", (sk,))
            conn.execute(
                "DELETE FROM user_salesman_access WHERE salesman_key = ?", (sk,),
            )


def has_sharepoint_access(email: str) -> bool:
    """Admins always pass. Otherwise check per-user flag."""
    u = get_app_user(email)
    if not u:
        return False
    if is_admin_email(email):
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


def _salesman_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["active"] = bool(d.get("active", 1))
    try:
        d["commission_pct"] = float(d.get("commission_pct") or 0.0)
    except Exception:
        d["commission_pct"] = 0.0
    return d


def list_salesman_map(*, active_only: bool = False) -> list[dict]:
    """Salesmen, ordered by name. Empty-email rows are filtered out
    defensively even though the prune in init_db should have removed
    them already.
    """
    sql = "SELECT * FROM app_salesmen WHERE email IS NOT NULL AND email != ''"
    if active_only:
        sql += " AND active = 1"
    sql += " ORDER BY full_name COLLATE NOCASE, key"
    with connect() as conn:
        rows = conn.execute(sql).fetchall()
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
    """Insert or update a salesman row + keep the linked user in sync.

    Email is REQUIRED -- we do not allow phantom salesmen anymore.
    Side effects:

      * Creates/updates a matching ``app_users`` row keyed by the
        salesman's email (role=salesman, salesman_key=<key>).
      * If the salesman's email changed, the user's email is renamed
        and any per-user data keyed by the old email cascades.

    Returns the normalized salesman key.
    Raises ``ValueError`` on missing key/email/full_name.
    """
    raw_key = data.get("key") or ""
    k = _norm_salesman_key(raw_key)
    if not k:
        raise ValueError("salesman key is required")

    number       = str(data.get("number") or "").strip()
    full_name    = str(data.get("full_name") or "").strip()
    display_name = str(data.get("display_name") or "").strip() or full_name
    email        = str(data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("salesman email is required and must be a valid address")
    if not full_name:
        raise ValueError("salesman full_name is required")
    try:
        commission_pct = float(data.get("commission_pct") or 0.0)
    except (TypeError, ValueError):
        commission_pct = 0.0
    active = 1 if (data.get("active", True) in (True, 1, "1", "true", "True")) else 0

    now = _now_utc()
    with connect() as conn:
        # Capture the previous email (if any) so we can rename the
        # linked user atomically.
        prev = conn.execute(
            "SELECT email FROM app_salesmen WHERE key = ?", (k,),
        ).fetchone()
        prev_email = (prev["email"].strip().lower() if prev and prev["email"] else "")

        # Refuse to attach to an email that's already used by a non-salesman
        # account (admin/developer/manager). The admin would have to demote
        # that account first; silently overwriting their role would be
        # surprising.
        clash = conn.execute(
            "SELECT email, role, salesman_key FROM app_users "
            " WHERE email = ? AND role NOT IN ('salesman','')",
            (email,),
        ).fetchone()
        if clash and (prev_email != email):
            raise ValueError(
                f"{email} is already a non-salesman user (role={clash['role']}). "
                "Demote that user first or pick a different email."
            )

        conn.execute(
            """
            INSERT INTO app_salesmen
              (key, number, full_name, display_name, email, commission_pct,
               active, updated_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              number         = excluded.number,
              full_name      = excluded.full_name,
              display_name   = excluded.display_name,
              email          = excluded.email,
              commission_pct = excluded.commission_pct,
              active         = excluded.active,
              updated_utc    = excluded.updated_utc
            """,
            (k, number, full_name, display_name, email, commission_pct, active, now),
        )

        # ----- keep the linked app_users row in sync -----
        if prev_email and prev_email != email:
            # Rename: cascade the old email to the new one across every
            # per-user table. We can't call update_app_user() here -- it
            # would open a second SQLite connection and (under WAL with
            # an open writer) deadlock. Inline the work instead.
            existing_old = conn.execute(
                "SELECT email FROM app_users WHERE email = ?", (prev_email,),
            ).fetchone()
            if existing_old:
                # Remove any pre-existing row at the new email so the
                # rename UPDATE doesn't violate the PK.
                conn.execute(
                    "DELETE FROM app_users WHERE email = ? AND email != ?",
                    (email, prev_email),
                )
                conn.execute(
                    "UPDATE app_users "
                    "   SET email = ?, role = 'salesman', salesman_key = ?, "
                    "       display_name = COALESCE(?, display_name), active = ? "
                    " WHERE email = ?",
                    (email, k, display_name or None, active, prev_email),
                )
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
                            (email, prev_email),
                        )
                    except sqlite3.OperationalError:
                        pass
            else:
                # No old user row -- create the new one.
                conn.execute(
                    """
                    INSERT INTO app_users
                      (email, display_name, role, salesman_key, is_admin,
                       is_external, active, dashboard_enabled, test_access_enabled)
                    VALUES (?, ?, 'salesman', ?, 0, 0, ?, 1, 1)
                    """,
                    (email, display_name or None, k, active),
                )
        else:
            existing = conn.execute(
                "SELECT email, role FROM app_users WHERE email = ?", (email,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO app_users
                      (email, display_name, role, salesman_key, is_admin,
                       is_external, active, dashboard_enabled, test_access_enabled)
                    VALUES (?, ?, 'salesman', ?, 0, 0, ?, 1, 1)
                    """,
                    (email, display_name or None, k, active),
                )
            else:
                # Only auto-assign salesman role if the user doesn't
                # already hold a stronger role.
                if (existing["role"] or "").lower() in ("", "salesman"):
                    conn.execute(
                        "UPDATE app_users SET role = 'salesman', salesman_key = ?, "
                        "display_name = COALESCE(display_name, ?), active = ? "
                        "WHERE email = ?",
                        (k, display_name or None, active, email),
                    )
                else:
                    # User has an admin/developer/manager role: just link
                    # the salesman key without changing anything else.
                    conn.execute(
                        "UPDATE app_users SET salesman_key = ? WHERE email = ?",
                        (k, email),
                    )
    return k


def delete_salesman_record(key: str) -> bool:
    """Delete a salesman row. Cascades to the linked user.

    The salesman <-> user relationship is one-to-one, so removing the
    salesman also removes their user (you can't have a salesman role
    user with no salesman to point at). Manager assignments that
    reference this key are pruned too.
    """
    k = _norm_salesman_key(key)
    if not k:
        return False
    with connect() as conn:
        sm_row = conn.execute(
            "SELECT email FROM app_salesmen WHERE key = ?", (k,),
        ).fetchone()
        cur = conn.execute("DELETE FROM app_salesmen WHERE key = ?", (k,))
        if sm_row and sm_row["email"]:
            email = sm_row["email"].strip().lower()
            conn.execute(
                "DELETE FROM app_users WHERE email = ? AND role = 'salesman'",
                (email,),
            )
        conn.execute(
            "DELETE FROM user_salesman_access WHERE salesman_key = ?", (k,),
        )
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
            "SELECT key, number, full_name, display_name, commission_pct, email "
            "FROM app_salesmen"
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
        d["sm_number"]      = sm["number"] if sm else None
        d["sm_name"]        = sm["full_name"] if sm else None
        d["commission_pct"] = float(sm["commission_pct"] or 0.0) if sm else None
        enriched.append(d)
    return enriched
