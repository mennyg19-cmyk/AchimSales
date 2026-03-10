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
    error         TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email    TEXT NOT NULL,
    type          TEXT NOT NULL,
    title         TEXT NOT NULL,
    message       TEXT,
    data          TEXT DEFAULT '{}',
    dismissed     INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL
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
    display_name  TEXT
);

CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_email, timestamp);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_email, dismissed);
CREATE INDEX IF NOT EXISTS idx_settings_user ON user_settings(user_email);
CREATE INDEX IF NOT EXISTS idx_cache_group ON dashboard_cache(sales_group);
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_email ON app_users(email);
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
        conn.executescript(_SCHEMA)
        conn.commit()
        user_count = conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]
        print(f"[db] init_db: app_users table has {user_count} rows after schema init", flush=True)
    finally:
        conn.close()
    migrate_json_history()
    migrate_json_users()


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
    conn = get_db()
    try:
        if user_email:
            conn.execute(
                "UPDATE notifications SET dismissed = 1 WHERE id = ? AND user_email = ?",
                (notification_id, user_email))
        else:
            conn.execute("UPDATE notifications SET dismissed = 1 WHERE id = ?",
                         (notification_id,))
        conn.commit()
    finally:
        conn.close()


def dismiss_notifications_by_type(user_email: str, ntype: str):
    """Dismiss all notifications of a given type for a user."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE notifications SET dismissed = 1 WHERE user_email = ? AND type = ?",
            (user_email, ntype))
        conn.commit()
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


def get_excluded_salesmen(user_email: str) -> list[str]:
    return get_setting(user_email, "excluded_salesmen", [])


def set_excluded_salesmen(user_email: str, keys: list[str]):
    set_setting(user_email, "excluded_salesmen", keys)


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


def get_all_users() -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, email, role, salesman_key, display_name FROM app_users ORDER BY email"
        ).fetchall()
        return [dict(r) for r in rows]
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
            "SELECT id, email, role, salesman_key, display_name FROM app_users WHERE email = ?",
            (email.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def add_user(email: str, role: str, salesman_key: str | None = None,
             display_name: str | None = None) -> bool:
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO app_users (email, role, salesman_key, display_name)
               VALUES (?, ?, ?, ?)""",
            (email.lower().strip(), role, salesman_key or None, display_name or None),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_user(email: str, role: str, salesman_key: str | None = None,
                display_name: str | None = None) -> bool:
    conn = get_db()
    try:
        cur = conn.execute(
            """UPDATE app_users SET role = ?, salesman_key = ?, display_name = ?
               WHERE email = ?""",
            (role, salesman_key or None, display_name or None, email.lower().strip()),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_user(email: str) -> bool:
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM app_users WHERE email = ?",
                           (email.lower().strip(),))
        conn.commit()
        return cur.rowcount > 0
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
