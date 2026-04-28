"""
SQLite database layer for the Sales Reports web app.

Single file database at webapp/app.db.  Uses Python's built-in sqlite3
module -- zero extra dependencies.
"""

import json
import logging
import os
import re as _re
import sqlite3
import glob as _glob
import shutil
import uuid

log = logging.getLogger(__name__)


def normalize_key(value: str) -> str:
    """Normalize a salesman key / sales group for comparison.

    Strips all non-alphanumeric chars and lowercases the result so that
    'M.Kolko', 'mkolko', and 'M Kolko' all match.
    """
    return _re.sub(r"[^a-z0-9]+", "", value.lower()) if value else ""


WEBAPP_DIR = os.path.dirname(os.path.abspath(__file__))

# On Azure, /home is persistent storage that survives redeploys.
# Locally, fall back to the webapp directory.
_AZURE_HOME = os.environ.get("HOME", "")
_ON_AZURE = bool(os.environ.get("WEBSITE_SITE_NAME"))

if _ON_AZURE:
    _DB_DIR = "/home/data"
    os.makedirs(_DB_DIR, exist_ok=True)
    DB_PATH = os.path.join(_DB_DIR, "app.db")
elif _AZURE_HOME and os.path.isdir(_AZURE_HOME) and _AZURE_HOME.startswith("/home"):
    _DB_DIR = os.path.join(_AZURE_HOME, "data")
    os.makedirs(_DB_DIR, exist_ok=True)
    DB_PATH = os.path.join(_DB_DIR, "app.db")
else:
    DB_PATH = os.path.join(WEBAPP_DIR, "app.db")

print(f"[db] DB_PATH resolved to: {DB_PATH} (AZURE={_ON_AZURE}, HOME={_AZURE_HOME!r}, WEBSITE_SITE_NAME={os.environ.get('WEBSITE_SITE_NAME')!r})",
      flush=True)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id     TEXT UNIQUE NOT NULL,
    user_email    TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    report_key    TEXT NOT NULL,
    report_name   TEXT NOT NULL,
    params        TEXT DEFAULT '{}',
    status        TEXT DEFAULT 'running',
    filepath      TEXT,
    filename      TEXT,
    summary       TEXT DEFAULT '{}',
    error         TEXT,
    extra_files   TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS notifications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email    TEXT NOT NULL,
    type          TEXT NOT NULL,
    title         TEXT NOT NULL,
    message       TEXT,
    data          TEXT DEFAULT '{}',
    dismissed     INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    dismissed_at  TEXT
);

CREATE TABLE IF NOT EXISTS user_settings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email    TEXT NOT NULL,
    setting_key   TEXT NOT NULL,
    setting_value TEXT NOT NULL,
    UNIQUE(user_email, setting_key)
);

CREATE TABLE IF NOT EXISTS dashboard_cache (
    customer_account  TEXT NOT NULL,
    customer_name     TEXT,
    sales_group       TEXT,
    last_order_date   TEXT,
    order_dates       TEXT,
    avg_gap_days      REAL,
    gap_stdev         REAL,
    overdue_threshold REAL,
    days_since_last   INTEGER,
    status            TEXT,
    last_refreshed    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email    TEXT NOT NULL,
    name          TEXT NOT NULL,
    report_key    TEXT NOT NULL,
    report_name   TEXT NOT NULL,
    params        TEXT DEFAULT '{}',
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_saved_reports_user ON saved_reports(user_email);

CREATE TABLE IF NOT EXISTS app_users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    role          TEXT NOT NULL DEFAULT 'salesman',
    salesman_key  TEXT,
    display_name  TEXT,
    dashboard_enabled INTEGER DEFAULT 1,
    test_access_enabled INTEGER DEFAULT 0,
    is_external   INTEGER DEFAULT 0
);

-- One-time login tokens for external (magic-link) sign-in. We store a
-- random opaque token (URL-safe), the user's email, expiry, and a flag
-- so we can mark it consumed after the first successful click. Unused
-- tokens auto-expire after 15 minutes.
CREATE TABLE IF NOT EXISTS magic_link_tokens (
    token         TEXT PRIMARY KEY,
    email         TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    consumed_at   TEXT
);

CREATE TABLE IF NOT EXISTS report_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id     TEXT NOT NULL,
    user_email    TEXT NOT NULL,
    report_key    TEXT NOT NULL,
    report_name   TEXT NOT NULL,
    params        TEXT DEFAULT '{}',
    started_at    TEXT NOT NULL,
    ended_at      TEXT,
    duration_sec  REAL,
    status        TEXT DEFAULT 'running',
    error         TEXT
);

CREATE TABLE IF NOT EXISTS salesmen (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    key           TEXT UNIQUE NOT NULL,
    number        TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    active        INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS report_config (
    report_key    TEXT PRIMARY KEY,
    enabled       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS user_report_access (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email    TEXT NOT NULL,
    report_key    TEXT NOT NULL,
    allowed       INTEGER DEFAULT 1,
    UNIQUE(user_email, report_key)
);

CREATE TABLE IF NOT EXISTS feature_flags (
    flag_key      TEXT PRIMARY KEY,
    enabled       INTEGER DEFAULT 1,
    description   TEXT
);

CREATE TABLE IF NOT EXISTS schedules (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    name                  TEXT UNIQUE NOT NULL,
    report_key            TEXT NOT NULL,
    extra_args            TEXT DEFAULT '',
    frequency             TEXT NOT NULL DEFAULT 'Day',
    interval_val          INTEGER DEFAULT 1,
    start_time            TEXT NOT NULL,
    time_zone             TEXT DEFAULT 'America/New_York',
    days_of_week          TEXT DEFAULT '',
    month_days            TEXT DEFAULT '',
    enabled               INTEGER DEFAULT 1,
    description           TEXT DEFAULT '',
    azure_schedule_name   TEXT,
    azure_job_schedule_id TEXT,
    last_synced_at        TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

-- The order-entry feature is currently disabled. Its supporting
-- tables (draft_orders, draft_order_lines, customer_addresses,
-- product_cache, price_cache) used to live here but were removed and
-- are dropped by a one-shot migration in init_db(). If the feature is
-- ever revived, recreate them here AND remove the DROP statements.

CREATE TABLE IF NOT EXISTS runbook_history (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id           TEXT UNIQUE,
    timestamp        TEXT NOT NULL,
    report_name      TEXT,
    status           TEXT,
    duration_sec     REAL,
    rows_output      INTEGER,
    files_uploaded   INTEGER,
    args             TEXT,
    error            TEXT,
    runbook_name     TEXT,
    start_time       TEXT,
    end_time         TEXT,
    source           TEXT DEFAULT 'run_log'
);

CREATE TABLE IF NOT EXISTS user_salesman_access (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email    TEXT NOT NULL,
    salesman_key  TEXT NOT NULL,
    UNIQUE(user_email, salesman_key)
);

CREATE TABLE IF NOT EXISTS email_distributions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT UNIQUE NOT NULL,
    recipients       TEXT NOT NULL DEFAULT '[]',
    cc               TEXT NOT NULL DEFAULT '[]',
    subject_template TEXT NOT NULL DEFAULT 'Daily Reports - {date}',
    body_template    TEXT NOT NULL DEFAULT '',
    enabled          INTEGER NOT NULL DEFAULT 1,
    trigger_mode     TEXT NOT NULL DEFAULT 'after_reports',
    frequency        TEXT NOT NULL DEFAULT 'daily',
    days_of_week     TEXT NOT NULL DEFAULT '',
    month_days       TEXT NOT NULL DEFAULT '',
    send_time        TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS email_distribution_reports (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    distribution_id    INTEGER NOT NULL REFERENCES email_distributions(id) ON DELETE CASCADE,
    report_key         TEXT NOT NULL,
    extra_args_match   TEXT DEFAULT '',
    file_path_template TEXT DEFAULT '',
    UNIQUE(distribution_id, report_key)
);

CREATE TABLE IF NOT EXISTS email_distribution_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    distribution_id  INTEGER NOT NULL REFERENCES email_distributions(id) ON DELETE CASCADE,
    sent_date        TEXT NOT NULL,
    sent_at          TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'sent',
    error            TEXT,
    reports_included TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_email_dist_log_date ON email_distribution_log(distribution_id, sent_date);
CREATE INDEX IF NOT EXISTS idx_runbook_history_ts ON runbook_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_runbook_history_report ON runbook_history(report_name);

CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_email, timestamp);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_email, dismissed);
CREATE INDEX IF NOT EXISTS idx_settings_user ON user_settings(user_email);
CREATE INDEX IF NOT EXISTS idx_cache_group ON dashboard_cache(sales_group);
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_email ON app_users(email);
CREATE INDEX IF NOT EXISTS idx_report_runs_started ON report_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_user_report_access ON user_report_access(user_email);
CREATE INDEX IF NOT EXISTS idx_user_salesman_access_email ON user_salesman_access(user_email);
"""


def get_db() -> sqlite3.Connection:
    """Return a connection with Row factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist and run one-time migrations."""
    print(f"[db] init_db: using database at {DB_PATH} (exists={os.path.isfile(DB_PATH)})", flush=True)
    conn = get_db()
    try:
        # One-shot cleanup of the order-entry tables. The feature is
        # disabled and these tables were taking up schema space and
        # confusing the DB explorer. ``DROP TABLE IF EXISTS`` is safe
        # to run repeatedly -- on a fresh DB the tables never existed
        # and nothing happens. Run BEFORE executescript so any
        # foreign-key references (draft_order_lines -> draft_orders)
        # don't block the drops.
        for tbl in ("draft_order_lines", "draft_orders",
                    "customer_addresses", "price_cache", "product_cache"):
            conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        conn.commit()

        conn.executescript(_SCHEMA)
        conn.commit()
        # Add dashboard_enabled column if missing (upgrade from older schema)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(app_users)").fetchall()]
        if "dashboard_enabled" not in cols:
            conn.execute("ALTER TABLE app_users ADD COLUMN dashboard_enabled INTEGER DEFAULT 1")
            conn.commit()
        if "test_access_enabled" not in cols:
            conn.execute("ALTER TABLE app_users ADD COLUMN test_access_enabled INTEGER DEFAULT 0")
            conn.commit()
        if "is_external" not in cols:
            conn.execute("ALTER TABLE app_users ADD COLUMN is_external INTEGER DEFAULT 0")
            conn.commit()
        notif_cols = [r[1] for r in conn.execute("PRAGMA table_info(notifications)").fetchall()]
        if notif_cols and "dismissed_at" not in notif_cols:
            conn.execute("ALTER TABLE notifications ADD COLUMN dismissed_at TEXT")
            conn.commit()
        # Add month_days column to schedules if missing
        sched_cols = [r[1] for r in conn.execute("PRAGMA table_info(schedules)").fetchall()]
        if sched_cols and "month_days" not in sched_cols:
            conn.execute("ALTER TABLE schedules ADD COLUMN month_days TEXT DEFAULT ''")
            conn.commit()
        # Migrate email_distributions: add scheduling columns
        ed_cols = [r[1] for r in conn.execute("PRAGMA table_info(email_distributions)").fetchall()]
        for col, typedef in [("trigger_mode", "TEXT NOT NULL DEFAULT 'after_reports'"),
                             ("frequency", "TEXT NOT NULL DEFAULT 'daily'"),
                             ("days_of_week", "TEXT NOT NULL DEFAULT ''"),
                             ("month_days", "TEXT NOT NULL DEFAULT ''"),
                             ("send_time", "TEXT NOT NULL DEFAULT ''")]:
            if col not in ed_cols:
                conn.execute(f"ALTER TABLE email_distributions ADD COLUMN {col} {typedef}")
        conn.commit()
        # Migrate email_distribution_reports: add file_path_template
        edr_cols = [r[1] for r in conn.execute("PRAGMA table_info(email_distribution_reports)").fetchall()]
        if "file_path_template" not in edr_cols:
            conn.execute("ALTER TABLE email_distribution_reports ADD COLUMN file_path_template TEXT DEFAULT ''")
            conn.commit()
        # Migrate history: add extra_files JSON array for multi-file reports (Number 4, Salesman, etc.)
        hist_cols = [r[1] for r in conn.execute("PRAGMA table_info(history)").fetchall()]
        if hist_cols and "extra_files" not in hist_cols:
            conn.execute("ALTER TABLE history ADD COLUMN extra_files TEXT DEFAULT '[]'")
            conn.commit()
        user_count = conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]
        print(f"[db] init_db: app_users table has {user_count} rows after schema init", flush=True)
    finally:
        conn.close()
    migrate_json_history()
    migrate_json_users()
    seed_salesmen()
    seed_report_config()
    seed_feature_flags()
    seed_demo_order_data()


def migrate_json_history():
    """One-time migration: import existing _history/*.json into SQLite."""
    history_dir = os.path.join(WEBAPP_DIR, "_history")
    backup_dir = os.path.join(WEBAPP_DIR, "_history_backup")

    if not os.path.isdir(history_dir):
        return

    json_files = _glob.glob(os.path.join(history_dir, "*.json"))
    if not json_files:
        return

    conn = get_db()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        if existing > 0:
            log.info("History table already has data -- skipping JSON migration")
            return

        migrated = 0
        for fpath in json_files:
            fname = os.path.basename(fpath)
            email_part = fname.replace(".json", "")
            email = email_part.replace("_", "-").replace("-", "@", 1)
            if "@" not in email:
                email = email_part

            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    records = json.load(f)
            except Exception:
                log.exception("Failed to read %s for migration", fpath)
                continue

            for rec in records:
                record_id = rec.get("record_id", uuid.uuid4().hex[:12])
                conn.execute(
                    """INSERT OR IGNORE INTO history
                       (record_id, user_email, timestamp, report_key, report_name,
                        params, status, filepath, filename, summary, error)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record_id,
                        email,
                        rec.get("timestamp", ""),
                        rec.get("report_key", ""),
                        rec.get("report_name", ""),
                        json.dumps(rec.get("params", {})),
                        rec.get("status", "completed"),
                        rec.get("filepath"),
                        rec.get("filename"),
                        json.dumps(rec.get("summary", {})),
                        rec.get("error"),
                    ),
                )
                migrated += 1

        conn.commit()
        log.info("Migrated %d history records from JSON to SQLite", migrated)

        os.makedirs(backup_dir, exist_ok=True)
        for fpath in json_files:
            shutil.move(fpath, os.path.join(backup_dir, os.path.basename(fpath)))
        log.info("Moved JSON history files to %s", backup_dir)

    except Exception:
        log.exception("JSON history migration failed")
    finally:
        conn.close()


# -- Notification helpers --------------------------------------------------

def add_notification(user_email: str, ntype: str, title: str,
                     message: str = "", data: dict | None = None) -> int:
    """Insert a notification and return its id."""
    from datetime import datetime
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO notifications (user_email, type, title, message, data, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_email, ntype, title, message,
             json.dumps(data or {}),
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_notifications(user_email: str, dismissed: bool = False) -> list[dict]:
    """Return notifications for a user, newest first."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, type, title, message, data, dismissed, created_at
               FROM notifications
               WHERE user_email = ? AND dismissed = ?
               ORDER BY created_at DESC""",
            (user_email, int(dismissed)),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["data"] = json.loads(d["data"]) if d["data"] else {}
            result.append(d)
        return result
    finally:
        conn.close()


def get_notification_counts(user_email: str) -> dict:
    """Return counts of unread notifications by type."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT type, COUNT(*) as cnt
               FROM notifications
               WHERE user_email = ? AND dismissed = 0
               GROUP BY type""",
            (user_email,),
        ).fetchall()
        counts = {r["type"]: r["cnt"] for r in rows}
        counts["total"] = sum(counts.values())
        return counts
    finally:
        conn.close()


def dismiss_notification(notification_id: int, user_email: str | None = None):
    """Mark a single notification as dismissed (only if owned by user_email)."""
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_db()
    try:
        if user_email:
            conn.execute(
                "UPDATE notifications SET dismissed = 1, dismissed_at = ? WHERE id = ? AND user_email = ?",
                (now, notification_id, user_email))
        else:
            conn.execute("UPDATE notifications SET dismissed = 1, dismissed_at = ? WHERE id = ?",
                         (now, notification_id))
        conn.commit()
    finally:
        conn.close()


def dismiss_notifications_by_type(user_email: str, ntype: str):
    """Dismiss all notifications of a given type for a user."""
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_db()
    try:
        conn.execute(
            "UPDATE notifications SET dismissed = 1, dismissed_at = ? WHERE user_email = ? AND type = ?",
            (now, user_email, ntype))
        conn.commit()
    finally:
        conn.close()


def dismiss_all_notifications(user_email: str):
    """Dismiss every active notification for a user."""
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_db()
    try:
        conn.execute(
            "UPDATE notifications SET dismissed = 1, dismissed_at = ? WHERE user_email = ? AND dismissed = 0",
            (now, user_email,))
        conn.commit()
    finally:
        conn.close()


def get_recently_dismissed_accounts(user_email: str, days: int = 7) -> set:
    """Return customer accounts dismissed within the last N days (cooldown)."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT data FROM notifications
               WHERE user_email = ? AND type = 'overdue_customer'
                 AND dismissed = 1 AND dismissed_at >= ?""",
            (user_email, cutoff),
        ).fetchall()
        accts = set()
        for r in rows:
            d = json.loads(r["data"]) if r["data"] else {}
            acct = d.get("customer_account")
            if acct:
                accts.add(acct)
        return accts
    finally:
        conn.close()


# -- User settings helpers -------------------------------------------------

def get_setting(user_email: str, key: str, default=None):
    """Get a user setting value (JSON-decoded)."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT setting_value FROM user_settings WHERE user_email = ? AND setting_key = ?",
            (user_email, key)).fetchone()
        if row:
            return json.loads(row["setting_value"])
        return default
    finally:
        conn.close()


def set_setting(user_email: str, key: str, value):
    """Set a user setting value (JSON-encoded)."""
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO user_settings (user_email, setting_key, setting_value)
               VALUES (?, ?, ?)
               ON CONFLICT(user_email, setting_key)
               DO UPDATE SET setting_value = excluded.setting_value""",
            (user_email, key, json.dumps(value)))
        conn.commit()
    finally:
        conn.close()


def get_excluded_customers(user_email: str) -> list[str]:
    return get_setting(user_email, "excluded_customers", [])


def set_excluded_customers(user_email: str, accounts: list[str]):
    set_setting(user_email, "excluded_customers", accounts)


def get_cached_customer_list(salesman_key: str | None = None) -> list[dict]:
    """Fast query: return minimal customer info from the dashboard cache.

    Used by the settings page so it doesn't have to wait for a full refresh.
    """
    conn = get_db()
    try:
        if salesman_key:
            rows = conn.execute(
                "SELECT customer_account, customer_name, last_order_date, sales_group "
                "FROM dashboard_cache ORDER BY customer_name"
            ).fetchall()
            norm = normalize_key(salesman_key)
            rows = [r for r in rows if normalize_key(r["sales_group"] or "") == norm]
        else:
            rows = conn.execute(
                """SELECT customer_account, customer_name, last_order_date
                   FROM dashboard_cache ORDER BY customer_name"""
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# -- User management -------------------------------------------------------

def migrate_json_users():
    """One-time migration: import user_map.json into the app_users table."""
    user_map_path = os.path.join(WEBAPP_DIR, "user_map.json")
    if not os.path.isfile(user_map_path):
        return

    conn = get_db()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]
        if existing > 0:
            return

        with open(user_map_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        users = data.get("users", {})
        migrated = 0
        for email, info in users.items():
            conn.execute(
                """INSERT OR IGNORE INTO app_users (email, role, salesman_key, display_name)
                   VALUES (?, ?, ?, ?)""",
                (email.lower().strip(),
                 info.get("role", "salesman"),
                 info.get("salesman_key"),
                 info.get("display_name")),
            )
            migrated += 1

        conn.commit()
        print(f"[db] Seeded {migrated} users from user_map.json into app_users", flush=True)
    except Exception:
        log.exception("User map migration failed")
    finally:
        conn.close()


def seed_salesmen():
    """One-time seed: populate salesmen table from config/salesman_map.py."""
    conn = get_db()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM salesmen").fetchone()[0]
        if existing > 0:
            return
        try:
            from config.salesman_map import SALESMAN_MAP
        except ImportError:
            log.warning("config.salesman_map not found -- skipping salesmen seed")
            return
        count = 0
        for key, (number, full_name, display_name) in SALESMAN_MAP.items():
            conn.execute(
                """INSERT OR IGNORE INTO salesmen (key, number, full_name, display_name, active)
                   VALUES (?, ?, ?, ?, 1)""",
                (key, number, full_name, display_name),
            )
            count += 1
        conn.commit()
        print(f"[db] Seeded {count} salesmen from salesman_map.py", flush=True)
    except Exception:
        log.exception("Salesmen seed failed")
    finally:
        conn.close()


def seed_report_config():
    """Seed report_config from REPORTS_CONFIG so every report key has a row.

    Most reports default to globally enabled. Reports listed in
    ``_REPORTS_DISABLED_BY_DEFAULT`` start globally disabled instead, so
    they're hidden from everyone (including future new users) until an admin
    explicitly turns them on per-user via the user_report_access override.
    """
    from webapp.user_map import REPORTS_CONFIG

    conn = get_db()
    try:
        for rkey in REPORTS_CONFIG:
            default_enabled = 0 if rkey in _REPORTS_DISABLED_BY_DEFAULT else 1
            conn.execute(
                "INSERT OR IGNORE INTO report_config (report_key, enabled) VALUES (?, ?)",
                (rkey, default_enabled),
            )
        conn.commit()
    except Exception:
        log.exception("Report config seed failed")
    finally:
        conn.close()


# Reports that ship globally disabled. Admins flip them on for individual
# users via the user_report_access override (Settings -> Permissions grid).
_REPORTS_DISABLED_BY_DEFAULT = {
    "customer_last_order",
}


def seed_feature_flags():
    """Seed default feature flags."""
    defaults = [
        ("dashboard_enabled", 1, "Show the Dashboard tab for all users"),
        ("order_entry_enabled", 0, "Show the Order Entry tab for sales reps"),
        ("test_site_enabled", 0, "Show 'Go to Test' link for users with test access"),
    ]
    conn = get_db()
    try:
        for key, enabled, desc in defaults:
            conn.execute(
                "INSERT OR IGNORE INTO feature_flags (flag_key, enabled, description) VALUES (?, ?, ?)",
                (key, enabled, desc),
            )
        conn.commit()
    except Exception:
        log.exception("Feature flags seed failed")
    finally:
        conn.close()


def seed_demo_order_data():
    """No-op. Demo data has been removed; addresses come from D365."""
    pass


# -- Salesmen CRUD ---------------------------------------------------------

def get_all_salesmen_db() -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, key, number, full_name, display_name, active FROM salesmen ORDER BY full_name"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()



def update_salesman_db(key: str, **fields) -> bool:
    allowed = {"number", "full_name", "display_name", "active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [key]
    conn = get_db()
    try:
        cur = conn.execute(f"UPDATE salesmen SET {set_clause} WHERE key = ?", values)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def add_salesman_db(key: str, number: str, full_name: str, display_name: str) -> bool:
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO salesmen (key, number, full_name, display_name, active) VALUES (?, ?, ?, ?, 1)",
            (key, number, full_name, display_name),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_salesman_db(key: str) -> bool:
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM salesmen WHERE key = ?", (key,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# -- Report config CRUD ---------------------------------------------------

def get_report_config_all() -> dict[str, bool]:
    """Return {report_key: enabled} for all reports."""
    conn = get_db()
    try:
        rows = conn.execute("SELECT report_key, enabled FROM report_config").fetchall()
        return {r["report_key"]: bool(r["enabled"]) for r in rows}
    finally:
        conn.close()


def set_report_enabled(report_key: str, enabled: bool):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO report_config (report_key, enabled) VALUES (?, ?) "
            "ON CONFLICT(report_key) DO UPDATE SET enabled = excluded.enabled",
            (report_key, int(enabled)),
        )
        conn.commit()
    finally:
        conn.close()


# -- Per-user report access overrides --------------------------------------

def get_user_report_overrides(user_email: str) -> dict[str, bool]:
    """Return {report_key: allowed} overrides for a specific user."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT report_key, allowed FROM user_report_access WHERE user_email = ?",
            (user_email.lower().strip(),),
        ).fetchall()
        return {r["report_key"]: bool(r["allowed"]) for r in rows}
    finally:
        conn.close()


def set_user_report_override(user_email: str, report_key: str, allowed: bool):
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO user_report_access (user_email, report_key, allowed)
               VALUES (?, ?, ?)
               ON CONFLICT(user_email, report_key) DO UPDATE SET allowed = excluded.allowed""",
            (user_email.lower().strip(), report_key, int(allowed)),
        )
        conn.commit()
    finally:
        conn.close()


def delete_user_report_override(user_email: str, report_key: str):
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM user_report_access WHERE user_email = ? AND report_key = ?",
            (user_email.lower().strip(), report_key),
        )
        conn.commit()
    finally:
        conn.close()


# -- Per-user salesman access (for managers) -------------------------------

def get_user_salesman_access(user_email: str) -> list[str]:
    """Return the list of salesman keys a user (typically a manager) is allowed to access."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT salesman_key FROM user_salesman_access WHERE user_email = ?",
            (user_email.lower().strip(),),
        ).fetchall()
        return [r["salesman_key"] for r in rows]
    finally:
        conn.close()


def set_user_salesman_access(user_email: str, keys: list[str]):
    """Replace all salesman-access entries for *user_email* with *keys*."""
    email = user_email.lower().strip()
    conn = get_db()
    try:
        conn.execute("DELETE FROM user_salesman_access WHERE user_email = ?", (email,))
        for k in keys:
            k = k.strip()
            if k:
                conn.execute(
                    "INSERT OR IGNORE INTO user_salesman_access (user_email, salesman_key) VALUES (?, ?)",
                    (email, k),
                )
        conn.commit()
    finally:
        conn.close()


# -- Feature flags ---------------------------------------------------------

def get_feature_flag(flag_key: str, default: bool = True) -> bool:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT enabled FROM feature_flags WHERE flag_key = ?", (flag_key,)
        ).fetchone()
        return bool(row["enabled"]) if row else default
    finally:
        conn.close()


def get_all_feature_flags() -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT flag_key, enabled, description FROM feature_flags ORDER BY flag_key"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_feature_flag(flag_key: str, enabled: bool):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO feature_flags (flag_key, enabled) VALUES (?, ?) "
            "ON CONFLICT(flag_key) DO UPDATE SET enabled = excluded.enabled",
            (flag_key, int(enabled)),
        )
        conn.commit()
    finally:
        conn.close()


# -- User management -------------------------------------------------------

def get_all_users() -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, email, role, salesman_key, display_name, dashboard_enabled FROM app_users ORDER BY email"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_users_permission_grid() -> list[dict]:
    """Return every app_user with their salesman info and per-report access map.

    Each item: {email, role, salesman_key, display_name, dashboard_enabled,
                test_access_enabled, sm_number, sm_name, active, reports: {report_key: bool},
                allowed_salesmen: [str]}
    """
    conn = get_db()
    try:
        users = conn.execute(
            """SELECT u.id, u.email, u.role, u.salesman_key, u.display_name,
                      u.dashboard_enabled, u.test_access_enabled, u.is_external,
                      s.number AS sm_number, s.full_name AS sm_name, s.active
               FROM app_users u
               LEFT JOIN salesmen s ON u.salesman_key = s.key
               ORDER BY CASE WHEN u.role IN ('admin','developer') THEN 0
                             WHEN u.role = 'manager' THEN 1
                             ELSE 2 END,
                        s.full_name, u.email"""
        ).fetchall()

        overrides = conn.execute(
            "SELECT user_email, report_key, allowed FROM user_report_access"
        ).fetchall()
        ovr_map: dict[str, dict[str, bool]] = {}
        for o in overrides:
            ovr_map.setdefault(o["user_email"], {})[o["report_key"]] = bool(o["allowed"])

        sm_access_rows = conn.execute(
            "SELECT user_email, salesman_key FROM user_salesman_access"
        ).fetchall()
        sm_access_map: dict[str, list[str]] = {}
        for row in sm_access_rows:
            sm_access_map.setdefault(row["user_email"], []).append(row["salesman_key"])

        from webapp.user_map import REPORTS_CONFIG
        report_keys = list(REPORTS_CONFIG.keys())

        global_cfg = {}
        for row in conn.execute("SELECT report_key, enabled FROM report_config").fetchall():
            global_cfg[row["report_key"]] = bool(row["enabled"])

        result = []
        for u in users:
            d = dict(u)
            user_ovr = ovr_map.get(d["email"], {})
            is_adm = d["role"] in ("admin", "developer")
            is_mgr = d["role"] == "manager"
            reports = {}
            for rk in report_keys:
                cfg = REPORTS_CONFIG[rk]
                if rk in user_ovr:
                    reports[rk] = user_ovr[rk]
                elif is_adm or is_mgr:
                    reports[rk] = global_cfg.get(rk, True)
                elif cfg.get("salesman_filter"):
                    reports[rk] = global_cfg.get(rk, True)
                else:
                    reports[rk] = False
            d["reports"] = reports
            d["allowed_salesmen"] = sm_access_map.get(d["email"], [])
            result.append(d)
        return result
    finally:
        conn.close()


def set_user_dashboard(email: str, enabled: bool):
    conn = get_db()
    try:
        conn.execute("UPDATE app_users SET dashboard_enabled = ? WHERE email = ?",
                     (int(enabled), email.lower().strip()))
        conn.commit()
    finally:
        conn.close()


def set_user_test_access(email: str, enabled: bool):
    conn = get_db()
    try:
        conn.execute("UPDATE app_users SET test_access_enabled = ? WHERE email = ?",
                     (int(enabled), email.lower().strip()))
        conn.commit()
    finally:
        conn.close()


def get_users_by_salesman_key(salesman_key: str) -> list[dict]:
    """Return all app_users rows that match a salesman_key (case-insensitive)."""
    norm = normalize_key(salesman_key)
    if not norm:
        return []
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, email, role, salesman_key, display_name FROM app_users"
        ).fetchall()
        return [dict(r) for r in rows if normalize_key(r["salesman_key"] or "") == norm]
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT id, email, role, salesman_key, display_name, is_external
               FROM app_users WHERE email = ?""",
            (email.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def add_user(email: str, role: str, salesman_key: str | None = None,
             display_name: str | None = None,
             is_external: bool = False) -> bool:
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO app_users (email, role, salesman_key, display_name, is_external)
               VALUES (?, ?, ?, ?, ?)""",
            (email.lower().strip(), role, salesman_key or None,
             display_name or None, 1 if is_external else 0),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_user(email: str, role: str, salesman_key: str | None = None,
                display_name: str | None = None,
                is_external: bool | None = None,
                new_email: str | None = None) -> bool:
    """Update a user. ``is_external=None`` leaves the existing value alone.

    If *new_email* is provided AND differs from *email*, the email
    change cascades to every other table that stores user_email, in a
    single transaction. We use string columns for user_email throughout
    (no FK constraints), so this manual cascade is the only way to keep
    notifications, settings, saved reports, etc. attached to the same
    person after a rename.
    """
    old = email.lower().strip()
    new = (new_email or "").lower().strip() or old

    conn = get_db()
    try:
        if new != old:
            existing = conn.execute(
                "SELECT 1 FROM app_users WHERE email = ?", (new,)
            ).fetchone()
            if existing:
                raise sqlite3.IntegrityError(
                    f"Cannot rename: an account with email {new} already exists.")

        if is_external is None:
            cur = conn.execute(
                """UPDATE app_users SET email = ?, role = ?, salesman_key = ?,
                       display_name = ?
                   WHERE email = ?""",
                (new, role, salesman_key or None, display_name or None, old),
            )
        else:
            cur = conn.execute(
                """UPDATE app_users SET email = ?, role = ?, salesman_key = ?,
                       display_name = ?, is_external = ?
                   WHERE email = ?""",
                (new, role, salesman_key or None, display_name or None,
                 1 if is_external else 0, old),
            )

        if cur.rowcount > 0 and new != old:
            for table, col in _USER_EMAIL_REFS:
                conn.execute(
                    f"UPDATE {table} SET {col} = ? WHERE {col} = ?",
                    (new, old),
                )

        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# Tables that store a user identity by *email string* rather than by
# foreign key. Anything that references a user belongs in this list so
# delete_user can purge it and update_user can rename it. Adding a new
# user-keyed table? Add it here too -- there's no schema-level cascade.
_USER_EMAIL_REFS: list[tuple[str, str]] = [
    ("notifications", "user_email"),
    ("user_settings", "user_email"),
    ("saved_reports", "user_email"),
    ("user_report_access", "user_email"),
    ("user_salesman_access", "user_email"),
    ("history", "user_email"),
    ("report_runs", "user_email"),
    ("magic_link_tokens", "email"),
]


def create_magic_link_token(email: str, ttl_minutes: int = 15) -> str:
    """Generate a fresh one-time login token for *email*. Returns the token.

    The token is URL-safe and 32 random bytes (~43 chars base64), opaque to
    the user. We also clean out any expired tokens for the same email so
    the table doesn't grow forever.
    """
    import secrets
    from datetime import datetime, timedelta, timezone

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=ttl_minutes)
    email_norm = email.lower().strip()

    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM magic_link_tokens WHERE email = ? AND (expires_at < ? OR consumed_at IS NOT NULL)",
            (email_norm, now.isoformat()),
        )
        conn.execute(
            """INSERT INTO magic_link_tokens (token, email, created_at, expires_at)
               VALUES (?, ?, ?, ?)""",
            (token, email_norm, now.isoformat(), expires.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def consume_magic_link_token(token: str) -> str | None:
    """Validate a token and mark it consumed. Returns the email if valid,
    None if the token is unknown, expired, or already used.
    """
    from datetime import datetime, timezone

    if not token or len(token) < 16:
        return None

    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT email, expires_at, consumed_at FROM magic_link_tokens
               WHERE token = ?""",
            (token,),
        ).fetchone()
        if not row:
            return None
        if row["consumed_at"]:
            return None
        if row["expires_at"] < now:
            return None
        conn.execute(
            "UPDATE magic_link_tokens SET consumed_at = ? WHERE token = ?",
            (now, token),
        )
        conn.commit()
        return row["email"]
    finally:
        conn.close()


def delete_user(email: str) -> dict:
    """Delete a user and every row keyed to their email across the DB.

    There are no foreign-key cascades (user_email is denormalized as a
    plain string in 8 tables), so the cleanup is manual but exhaustive
    -- see ``_USER_EMAIL_REFS``. Returns a small audit dict so the
    caller / admin UI can confirm what was wiped.
    """
    norm = email.lower().strip()
    conn = get_db()
    try:
        deleted: dict[str, int] = {}
        for table, col in _USER_EMAIL_REFS:
            cur = conn.execute(
                f"DELETE FROM {table} WHERE {col} = ?", (norm,)
            )
            if cur.rowcount:
                deleted[table] = cur.rowcount

        cur = conn.execute("DELETE FROM app_users WHERE email = ?", (norm,))
        existed = cur.rowcount > 0
        if existed:
            deleted["app_users"] = 1
        conn.commit()
        return {"existed": existed, "deleted_rows": deleted}
    finally:
        conn.close()


def purge_orphan_user_data(dry_run: bool = True) -> dict:
    """Find rows in user-keyed tables whose email no longer exists in
    ``app_users`` and (optionally) delete them.

    Useful when historical bugs or pre-cascade renames left dangling
    rows -- e.g. notifications keyed to an old email after the user was
    renamed. Returns a per-table breakdown of what was found, plus the
    list of orphan emails so the caller can show them in the UI.
    """
    conn = get_db()
    try:
        per_table: dict[str, dict] = {}
        all_orphans: set[str] = set()
        for table, col in _USER_EMAIL_REFS:
            rows = conn.execute(
                f"""SELECT {col} AS email, COUNT(*) AS n FROM {table}
                    WHERE {col} NOT IN (SELECT email FROM app_users)
                    GROUP BY {col}"""
            ).fetchall()
            if not rows:
                continue
            entries = [{"email": r["email"], "rows": r["n"]} for r in rows]
            per_table[table] = {
                "column": col,
                "total": sum(e["rows"] for e in entries),
                "by_email": entries,
            }
            for e in entries:
                if e["email"]:
                    all_orphans.add(e["email"])

        deleted: dict[str, int] = {}
        if not dry_run and per_table:
            for table, col in _USER_EMAIL_REFS:
                if table not in per_table:
                    continue
                cur = conn.execute(
                    f"""DELETE FROM {table}
                        WHERE {col} NOT IN (SELECT email FROM app_users)"""
                )
                if cur.rowcount:
                    deleted[table] = cur.rowcount
            conn.commit()

        return {
            "dry_run": dry_run,
            "orphan_emails": sorted(all_orphans),
            "per_table": per_table,
            "deleted_rows": deleted,
        }
    finally:
        conn.close()


# -- Saved reports (presets) -----------------------------------------------

def get_saved_reports(user_email: str) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, name, report_key, report_name, params, created_at
               FROM saved_reports WHERE user_email = ?
               ORDER BY name""",
            (user_email,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["params"] = json.loads(d["params"]) if d["params"] else {}
            result.append(d)
        return result
    finally:
        conn.close()


def add_saved_report(user_email: str, name: str, report_key: str,
                     report_name: str, params: dict) -> int:
    from datetime import datetime
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO saved_reports
               (user_email, name, report_key, report_name, params, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_email, name, report_key, report_name,
             json.dumps(params),
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def delete_saved_report(preset_id: int, user_email: str) -> bool:
    conn = get_db()
    try:
        cur = conn.execute(
            "DELETE FROM saved_reports WHERE id = ? AND user_email = ?",
            (preset_id, user_email))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# -- Report audit log ------------------------------------------------------

def cleanup_stale_running_reports():
    """Mark any 'running' records as 'failed' -- they are orphans from a
    previous server session whose background threads no longer exist."""
    from datetime import datetime
    conn = get_db()
    try:
        now = datetime.now().isoformat(timespec="seconds")
        c1 = conn.execute(
            "UPDATE history SET status = 'failed', error = 'Server restarted while report was running' "
            "WHERE status = 'running'"
        )
        c2 = conn.execute(
            "UPDATE report_runs SET ended_at = ?, status = 'failed', "
            "error = 'Server restarted while report was running' "
            "WHERE status = 'running' AND ended_at IS NULL",
            (now,),
        )
        conn.commit()
        total = (c1.rowcount or 0) + (c2.rowcount or 0)
        if total:
            log.info("Cleaned up %d stale 'running' report records on startup", total)
    finally:
        conn.close()


def log_report_start(record_id: str, user_email: str, report_key: str,
                     report_name: str, params: dict) -> int:
    """Insert a row when a report run begins. Returns the row id."""
    from datetime import datetime
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO report_runs
               (record_id, user_email, report_key, report_name, params, started_at, status)
               VALUES (?, ?, ?, ?, ?, ?, 'running')""",
            (record_id, user_email, report_key, report_name,
             json.dumps(params),
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def log_report_end(record_id: str, status: str, error: str | None = None):
    """Update the audit row when a report run finishes."""
    from datetime import datetime
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT started_at FROM report_runs WHERE record_id = ? ORDER BY id DESC LIMIT 1",
            (record_id,),
        ).fetchone()
        duration = None
        if row:
            started = datetime.fromisoformat(row["started_at"])
            duration = round((datetime.now() - started).total_seconds(), 1)
        conn.execute(
            """UPDATE report_runs
               SET ended_at = ?, duration_sec = ?, status = ?, error = ?
               WHERE record_id = ? AND ended_at IS NULL""",
            (datetime.now().isoformat(timespec="seconds"),
             duration, status, error, record_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_report_runs(limit: int = 200) -> list[dict]:
    """Return the most recent report runs across all users."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT record_id, user_email, report_key, report_name, params,
                      started_at, ended_at, duration_sec, status, error
               FROM report_runs ORDER BY started_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["params"] = json.loads(d["params"]) if d["params"] else {}
            result.append(d)
        return result
    except Exception:
        log.warning("report_runs table may not exist yet", exc_info=True)
        return []
    finally:
        conn.close()


# -- Schedules CRUD -------------------------------------------------------

def get_all_schedules() -> list[dict]:
    """Return all schedule rows, ordered by name."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, name, report_key, extra_args, frequency, interval_val,
                      start_time, time_zone, days_of_week, month_days,
                      enabled, description,
                      azure_schedule_name, azure_job_schedule_id,
                      last_synced_at, created_at, updated_at
               FROM schedules ORDER BY name"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_schedule_by_name(name: str) -> dict | None:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM schedules WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_schedule_by_id(schedule_id: int) -> dict | None:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM schedules WHERE id = ?", (schedule_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_schedule(name: str, report_key: str, extra_args: str = "",
                    frequency: str = "Day", interval_val: int = 1,
                    start_time: str = "", time_zone: str = "America/New_York",
                    days_of_week: str = "", month_days: str = "",
                    enabled: bool = True, description: str = "",
                    azure_schedule_name: str | None = None,
                    azure_job_schedule_id: str | None = None) -> int:
    """Insert or update a schedule row. Returns the row id."""
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO schedules
               (name, report_key, extra_args, frequency, interval_val,
                start_time, time_zone, days_of_week, month_days,
                enabled, description,
                azure_schedule_name, azure_job_schedule_id,
                last_synced_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 report_key = excluded.report_key,
                 extra_args = excluded.extra_args,
                 frequency = excluded.frequency,
                 interval_val = excluded.interval_val,
                 start_time = excluded.start_time,
                 time_zone = excluded.time_zone,
                 days_of_week = excluded.days_of_week,
                 month_days = excluded.month_days,
                 enabled = excluded.enabled,
                 description = excluded.description,
                 azure_schedule_name = excluded.azure_schedule_name,
                 azure_job_schedule_id = excluded.azure_job_schedule_id,
                 last_synced_at = excluded.last_synced_at,
                 updated_at = excluded.updated_at""",
            (name, report_key, extra_args, frequency, interval_val,
             start_time, time_zone, days_of_week, month_days,
             int(enabled), description,
             azure_schedule_name, azure_job_schedule_id,
             now, now, now),
        )
        conn.commit()
        return cur.lastrowid or conn.execute(
            "SELECT id FROM schedules WHERE name = ?", (name,)
        ).fetchone()[0]
    finally:
        conn.close()


def update_schedule_fields(schedule_id: int, **fields) -> bool:
    """Update specific fields on a schedule row."""
    from datetime import datetime
    allowed = {
        "name", "report_key", "extra_args", "frequency", "interval_val",
        "start_time", "time_zone", "days_of_week", "month_days",
        "enabled", "description",
        "azure_schedule_name", "azure_job_schedule_id", "last_synced_at",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = datetime.now().isoformat(timespec="seconds")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [schedule_id]
    conn = get_db()
    try:
        cur = conn.execute(
            f"UPDATE schedules SET {set_clause} WHERE id = ?", values
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_schedule_db(schedule_id: int) -> bool:
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_all_schedules_db():
    """Remove all schedule rows (used during full re-sync)."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM schedules")
        conn.commit()
    finally:
        conn.close()


# -- Draft orders CRUD ----------------------------------------------------

def create_draft_order(user_email: str, **fields) -> int:
    """Create a new draft order and return its id."""
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO draft_orders
               (user_email, customer_account, customer_name, ship_date,
                delivery_address_id, delivery_address_text, ship_method,
                po_number, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
            (user_email,
             fields.get("customer_account"),
             fields.get("customer_name"),
             fields.get("ship_date"),
             fields.get("delivery_address_id"),
             fields.get("delivery_address_text"),
             fields.get("ship_method"),
             fields.get("po_number"),
             now, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_draft_orders(user_email: str, status: str | None = None) -> list[dict]:
    """Return draft orders for a user, newest first."""
    conn = get_db()
    try:
        if status:
            rows = conn.execute(
                """SELECT * FROM draft_orders
                   WHERE user_email = ? AND status = ?
                   ORDER BY updated_at DESC""",
                (user_email, status),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM draft_orders
                   WHERE user_email = ?
                   ORDER BY updated_at DESC""",
                (user_email,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_draft_order(order_id: int, user_email: str | None = None) -> dict | None:
    """Return a single draft order, optionally scoped to user."""
    conn = get_db()
    try:
        if user_email:
            row = conn.execute(
                "SELECT * FROM draft_orders WHERE id = ? AND user_email = ?",
                (order_id, user_email),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM draft_orders WHERE id = ?", (order_id,)
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_draft_order(order_id: int, user_email: str, **fields) -> bool:
    """Update header fields on a draft order."""
    from datetime import datetime
    allowed = {
        "customer_account", "customer_name", "ship_date",
        "delivery_address_id", "delivery_address_text",
        "ship_method", "po_number", "status",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = datetime.now().isoformat(timespec="seconds")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [order_id, user_email]
    conn = get_db()
    try:
        cur = conn.execute(
            f"UPDATE draft_orders SET {set_clause} WHERE id = ? AND user_email = ?",
            values,
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_draft_order(order_id: int, user_email: str) -> bool:
    conn = get_db()
    try:
        cur = conn.execute(
            "DELETE FROM draft_orders WHERE id = ? AND user_email = ?",
            (order_id, user_email),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# -- Draft order lines CRUD -----------------------------------------------

def get_draft_order_lines(order_id: int) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM draft_order_lines WHERE draft_order_id = ? ORDER BY sort_order, id",
            (order_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_draft_order_line(order_id: int, **fields) -> int:
    """Add a line to a draft order. Returns the new line id."""
    qty = fields.get("qty", 0)
    price = fields.get("custom_price") or fields.get("unit_price", 0)
    extended = qty * price
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO draft_order_lines
               (draft_order_id, item_number, item_name, upc, qty, case_pack,
                unit_price, custom_price, update_customer_price, book_price,
                extended_price, is_matrix_entry, variant_color, variant_size, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_id,
             fields.get("item_number", ""),
             fields.get("item_name"),
             fields.get("upc"),
             qty,
             fields.get("case_pack", 1),
             fields.get("unit_price", 0),
             fields.get("custom_price"),
             int(fields.get("update_customer_price", False)),
             fields.get("book_price"),
             extended,
             int(fields.get("is_matrix_entry", False)),
             fields.get("variant_color"),
             fields.get("variant_size"),
             fields.get("sort_order", 0)),
        )
        conn.commit()
        _touch_draft_order(order_id, conn)
        return cur.lastrowid
    finally:
        conn.close()


def update_draft_order_line(line_id: int, order_id: int, **fields) -> bool:
    allowed = {
        "item_number", "item_name", "upc", "qty", "case_pack",
        "unit_price", "custom_price", "update_customer_price",
        "book_price", "is_matrix_entry", "variant_color", "variant_size",
        "sort_order",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if "qty" in updates or "custom_price" in updates or "unit_price" in updates:
        qty = updates.get("qty")
        price = updates.get("custom_price") or updates.get("unit_price")
        if qty is not None and price is not None:
            updates["extended_price"] = qty * price
    if "update_customer_price" in updates:
        updates["update_customer_price"] = int(updates["update_customer_price"])
    if "is_matrix_entry" in updates:
        updates["is_matrix_entry"] = int(updates["is_matrix_entry"])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [line_id, order_id]
    conn = get_db()
    try:
        cur = conn.execute(
            f"UPDATE draft_order_lines SET {set_clause} WHERE id = ? AND draft_order_id = ?",
            values,
        )
        conn.commit()
        if cur.rowcount > 0:
            _touch_draft_order(order_id, conn)
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_draft_order_line(line_id: int, order_id: int) -> bool:
    conn = get_db()
    try:
        cur = conn.execute(
            "DELETE FROM draft_order_lines WHERE id = ? AND draft_order_id = ?",
            (line_id, order_id),
        )
        conn.commit()
        if cur.rowcount > 0:
            _touch_draft_order(order_id, conn)
        return cur.rowcount > 0
    finally:
        conn.close()


def _touch_draft_order(order_id: int, conn: sqlite3.Connection | None = None):
    """Bump updated_at on a draft order."""
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    close = False
    if conn is None:
        conn = get_db()
        close = True
    try:
        conn.execute(
            "UPDATE draft_orders SET updated_at = ? WHERE id = ?", (now, order_id)
        )
        conn.commit()
    finally:
        if close:
            conn.close()


# -- Customer addresses CRUD -----------------------------------------------

def get_customer_addresses(customer_account: str) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM customer_addresses WHERE customer_account = ? ORDER BY is_default DESC, label",
            (customer_account,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_customer_address(customer_account: str, label: str, address_text: str,
                         is_default: bool = False, street: str = "",
                         city: str = "", state: str = "", zip_code: str = "",
                         country: str = "", source: str = "manual",
                         address_id: str = "") -> int:
    conn = get_db()
    try:
        if is_default:
            conn.execute(
                "UPDATE customer_addresses SET is_default = 0 WHERE customer_account = ?",
                (customer_account,),
            )
        cur = conn.execute(
            """INSERT INTO customer_addresses
               (customer_account, address_id, label, address_text, is_default,
                street, city, state, zip_code, country, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (customer_account, address_id[:5] if address_id else "",
             label, address_text, int(is_default),
             street, city, state, zip_code, country, source),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def upsert_d365_addresses(addresses: list[dict]):
    """Bulk upsert addresses from D365. Only touches source='d365' rows."""
    conn = get_db()
    try:
        for a in addresses:
            parts = [a.get("Street", ""), a.get("City", ""),
                     a.get("State", ""), a.get("ZipCode", ""),
                     a.get("Country", "")]
            addr_text = ", ".join(p for p in parts if p)
            label = a.get("Label", "") or addr_text[:60]
            conn.execute(
                """INSERT INTO customer_addresses
                   (customer_account, label, address_text, is_default,
                    street, city, state, zip_code, country, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'd365')
                   ON CONFLICT(customer_account, label) DO UPDATE SET
                    address_text=excluded.address_text,
                    street=excluded.street, city=excluded.city,
                    state=excluded.state, zip_code=excluded.zip_code,
                    country=excluded.country, source='d365'""",
                (a.get("CustomerAccount", ""), label, addr_text,
                 1 if str(a.get("IsPrimary", "")).lower() in ("yes", "true", "1") else 0,
                 a.get("Street", ""), a.get("City", ""),
                 a.get("State", ""), a.get("ZipCode", ""),
                 a.get("Country", "")),
            )
        conn.commit()
    finally:
        conn.close()


# -- Product cache CRUD ---------------------------------------------------

def get_cached_products(search_term: str = "") -> list[dict]:
    """Search the product_cache table. Returns list of product dicts."""
    conn = get_db()
    try:
        if search_term:
            q = f"%{search_term}%"
            rows = conn.execute(
                """SELECT * FROM product_cache
                   WHERE item_number LIKE ? OR product_name LIKE ?
                         OR description LIKE ?
                   ORDER BY item_number LIMIT 200""",
                (q, q, q),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM product_cache ORDER BY item_number LIMIT 200"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def upsert_product_cache(products: list[dict]):
    """Bulk upsert products into product_cache."""
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_db()
    try:
        conn.execute("DELETE FROM product_cache")
        conn.executemany(
            """INSERT INTO product_cache
               (item_number, product_name, description, sales_price, product_group, last_refreshed)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(p.get("ItemNumber", ""), p.get("ProductName", ""),
              p.get("Description", ""),
              float(p.get("BookPrice", 0) or 0),
              p.get("ProductGroup", ""), now)
             for p in products],
        )
        conn.commit()
    finally:
        conn.close()


def get_product_count() -> int:
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM product_cache").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


# -- Price cache CRUD -----------------------------------------------------

def get_cached_price(customer_account: str, item_number: str,
                     qty: float = 1.0) -> float | None:
    """Look up customer-specific price from price_cache.

    Returns the price for the highest min_qty that is <= qty,
    or None if no trade agreement exists.
    """
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT price FROM price_cache
               WHERE customer_account = ? AND item_number = ? AND min_qty <= ?
               ORDER BY min_qty DESC LIMIT 1""",
            (customer_account, item_number, qty),
        ).fetchone()
        return row["price"] if row else None
    finally:
        conn.close()


def upsert_price_cache(prices: list[dict]):
    """Bulk upsert trade agreement prices into price_cache."""
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_db()
    try:
        conn.execute("DELETE FROM price_cache")
        conn.executemany(
            """INSERT INTO price_cache
               (customer_account, item_number, price, currency, min_qty, last_refreshed)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(p.get("CustomerAccount", ""), p.get("ItemNumber", ""),
              float(p.get("Price", 0) or 0), p.get("Currency", ""),
              float(p.get("MinQty", 0) or 0), now)
             for p in prices],
        )
        conn.commit()
    finally:
        conn.close()


def get_price_count() -> int:
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM price_cache").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


# -- Runbook history -------------------------------------------------------

def upsert_runbook_history(rows: list[dict]):
    """Insert or update runbook history rows.

    Each row should have at minimum 'timestamp' and 'report_name'.
    Rows with a 'job_id' use it as unique key; others use timestamp+report_name+status.
    """
    if not rows:
        return
    conn = get_db()
    try:
        for r in rows:
            job_id = r.get("job_id") or None
            if job_id:
                existing = conn.execute(
                    "SELECT id, report_name, args, error FROM runbook_history WHERE job_id = ?", (job_id,)
                ).fetchone()
                if existing:
                    conn.execute(
                        """UPDATE runbook_history
                           SET status = ?, duration_sec = ?, end_time = ?,
                               report_name = COALESCE(NULLIF(?, ''), report_name),
                               args = COALESCE(NULLIF(?, ''), args),
                               error = COALESCE(NULLIF(?, ''), error),
                               rows_output = COALESCE(?, rows_output),
                               files_uploaded = COALESCE(?, files_uploaded)
                           WHERE job_id = ?""",
                        (r.get("status"), r.get("duration_sec"), r.get("end_time"),
                         r.get("report_name", ""), r.get("args", ""),
                         r.get("error", ""), r.get("rows_output"), r.get("files_uploaded"),
                         job_id),
                    )
                    continue

            if not job_id:
                dup = conn.execute(
                    """SELECT id FROM runbook_history
                       WHERE job_id IS NULL AND timestamp = ? AND report_name = ? AND status = ?""",
                    (r.get("timestamp", ""), r.get("report_name", ""), r.get("status", "")),
                ).fetchone()
                if dup:
                    continue

            conn.execute(
                """INSERT OR IGNORE INTO runbook_history
                   (job_id, timestamp, report_name, status, duration_sec,
                    rows_output, files_uploaded, args, error,
                    runbook_name, start_time, end_time, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job_id, r.get("timestamp", ""), r.get("report_name", ""),
                 r.get("status", ""), r.get("duration_sec"),
                 r.get("rows_output"), r.get("files_uploaded"),
                 r.get("args", ""), r.get("error", ""),
                 r.get("runbook_name", ""), r.get("start_time"),
                 r.get("end_time"), r.get("source", "run_log")),
            )
        conn.commit()
        log.info("Upserted %d runbook history rows", len(rows))
    finally:
        conn.close()


def get_runbook_history(limit: int = 500) -> list[dict]:
    """Return the most recent runbook history entries."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM runbook_history
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_runbook_history_count() -> int:
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM runbook_history").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


# -- Email Distribution CRUD -----------------------------------------------

def get_all_distributions() -> list[dict]:
    """Return all email distributions with their associated report keys."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM email_distributions ORDER BY name"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["recipients"] = json.loads(d["recipients"]) if d["recipients"] else []
            d["cc"] = json.loads(d["cc"]) if d["cc"] else []
            reps = conn.execute(
                "SELECT report_key, extra_args_match, file_path_template FROM email_distribution_reports WHERE distribution_id = ?",
                (d["id"],),
            ).fetchall()
            d["report_keys"] = [dict(rep) for rep in reps]
            last = conn.execute(
                """SELECT sent_date, sent_at, status, error FROM email_distribution_log
                   WHERE distribution_id = ? ORDER BY sent_at DESC LIMIT 1""",
                (d["id"],),
            ).fetchone()
            d["last_send"] = dict(last) if last else None
            result.append(d)
        return result
    finally:
        conn.close()


def get_distribution_by_id(dist_id: int) -> dict | None:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM email_distributions WHERE id = ?", (dist_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["recipients"] = json.loads(d["recipients"]) if d["recipients"] else []
        d["cc"] = json.loads(d["cc"]) if d["cc"] else []
        reps = conn.execute(
            "SELECT report_key, extra_args_match, file_path_template FROM email_distribution_reports WHERE distribution_id = ?",
            (d["id"],),
        ).fetchall()
        d["report_keys"] = [dict(rep) for rep in reps]
        return d
    finally:
        conn.close()


def upsert_distribution(
    name: str,
    recipients: list[str],
    report_keys: list[dict],
    cc: list[str] | None = None,
    subject_template: str = "Daily Reports - {date}",
    body_template: str = "",
    enabled: bool = True,
    trigger_mode: str = "after_reports",
    frequency: str = "daily",
    days_of_week: str = "",
    month_days: str = "",
    send_time: str = "",
    dist_id: int | None = None,
) -> int:
    """Create or update an email distribution. Returns the row id."""
    from datetime import datetime
    conn = get_db()
    try:
        if dist_id:
            conn.execute(
                """UPDATE email_distributions
                   SET name = ?, recipients = ?, cc = ?, subject_template = ?,
                       body_template = ?, enabled = ?,
                       trigger_mode = ?, frequency = ?, days_of_week = ?,
                       month_days = ?, send_time = ?
                   WHERE id = ?""",
                (name, json.dumps(recipients), json.dumps(cc or []),
                 subject_template, body_template, int(enabled),
                 trigger_mode, frequency, days_of_week, month_days, send_time,
                 dist_id),
            )
            conn.execute("DELETE FROM email_distribution_reports WHERE distribution_id = ?", (dist_id,))
            row_id = dist_id
        else:
            cur = conn.execute(
                """INSERT INTO email_distributions
                   (name, recipients, cc, subject_template, body_template, enabled,
                    trigger_mode, frequency, days_of_week, month_days, send_time, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, json.dumps(recipients), json.dumps(cc or []),
                 subject_template, body_template, int(enabled),
                 trigger_mode, frequency, days_of_week, month_days, send_time,
                 datetime.now().isoformat(timespec="seconds")),
            )
            row_id = cur.lastrowid
        for rk in report_keys:
            conn.execute(
                """INSERT INTO email_distribution_reports
                   (distribution_id, report_key, extra_args_match, file_path_template)
                   VALUES (?, ?, ?, ?)""",
                (row_id, rk["report_key"], rk.get("extra_args_match", ""),
                 rk.get("file_path_template", "")),
            )
        conn.commit()
        return row_id
    finally:
        conn.close()


def delete_distribution(dist_id: int) -> bool:
    conn = get_db()
    try:
        conn.execute("DELETE FROM email_distribution_reports WHERE distribution_id = ?", (dist_id,))
        conn.execute("DELETE FROM email_distribution_log WHERE distribution_id = ?", (dist_id,))
        cur = conn.execute("DELETE FROM email_distributions WHERE id = ?", (dist_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def toggle_distribution_enabled(dist_id: int) -> bool | None:
    """Toggle the enabled flag. Returns the new value, or None if not found."""
    conn = get_db()
    try:
        row = conn.execute("SELECT enabled FROM email_distributions WHERE id = ?", (dist_id,)).fetchone()
        if not row:
            return None
        new_val = 0 if row["enabled"] else 1
        conn.execute("UPDATE email_distributions SET enabled = ? WHERE id = ?", (new_val, dist_id))
        conn.commit()
        return bool(new_val)
    finally:
        conn.close()


def was_distribution_sent_today(dist_id: int, today_str: str) -> bool:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM email_distribution_log WHERE distribution_id = ? AND sent_date = ? AND status = 'sent'",
            (dist_id, today_str),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def log_distribution_send(dist_id: int, sent_date: str, status: str,
                          reports_included: list[str], error: str | None = None) -> int:
    from datetime import datetime
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO email_distribution_log
               (distribution_id, sent_date, sent_at, status, error, reports_included)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (dist_id, sent_date, datetime.now().isoformat(timespec="seconds"),
             status, error, json.dumps(reports_included)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_distribution_log(dist_id: int | None = None, limit: int = 100) -> list[dict]:
    conn = get_db()
    try:
        if dist_id:
            rows = conn.execute(
                """SELECT l.*, d.name as distribution_name
                   FROM email_distribution_log l
                   JOIN email_distributions d ON d.id = l.distribution_id
                   WHERE l.distribution_id = ?
                   ORDER BY l.sent_at DESC LIMIT ?""",
                (dist_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT l.*, d.name as distribution_name
                   FROM email_distribution_log l
                   JOIN email_distributions d ON d.id = l.distribution_id
                   ORDER BY l.sent_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["reports_included"] = json.loads(d["reports_included"]) if d["reports_included"] else []
            result.append(d)
        return result
    finally:
        conn.close()
