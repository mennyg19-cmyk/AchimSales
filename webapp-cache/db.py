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
    dashboard_enabled INTEGER DEFAULT 1
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

CREATE TABLE IF NOT EXISTS draft_orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email          TEXT NOT NULL,
    customer_account    TEXT,
    customer_name       TEXT,
    ship_date           TEXT,
    delivery_address_id INTEGER,
    delivery_address_text TEXT,
    ship_method         TEXT,
    po_number           TEXT,
    status              TEXT NOT NULL DEFAULT 'draft',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS draft_order_lines (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_order_id      INTEGER NOT NULL REFERENCES draft_orders(id) ON DELETE CASCADE,
    item_number         TEXT NOT NULL,
    item_name           TEXT,
    upc                 TEXT,
    qty                 INTEGER NOT NULL DEFAULT 0,
    case_pack           INTEGER NOT NULL DEFAULT 1,
    unit_price          REAL NOT NULL DEFAULT 0,
    custom_price        REAL,
    update_customer_price INTEGER DEFAULT 0,
    book_price          REAL,
    extended_price      REAL NOT NULL DEFAULT 0,
    is_matrix_entry     INTEGER DEFAULT 0,
    variant_color       TEXT,
    variant_size        TEXT,
    sort_order          INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS customer_addresses (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_account    TEXT NOT NULL,
    address_id          TEXT,
    label               TEXT,
    address_text        TEXT NOT NULL,
    street              TEXT,
    city                TEXT,
    state               TEXT,
    zip_code            TEXT,
    country             TEXT,
    is_default          INTEGER DEFAULT 0,
    source              TEXT DEFAULT 'manual',
    UNIQUE(customer_account, label)
);

CREATE TABLE IF NOT EXISTS product_cache (
    item_number         TEXT PRIMARY KEY,
    product_name        TEXT,
    description         TEXT,
    sales_price         REAL DEFAULT 0,
    product_group       TEXT,
    last_refreshed      TEXT
);

CREATE TABLE IF NOT EXISTS price_cache (
    customer_account    TEXT NOT NULL,
    item_number         TEXT NOT NULL,
    price               REAL NOT NULL DEFAULT 0,
    currency            TEXT,
    min_qty             REAL DEFAULT 0,
    last_refreshed      TEXT,
    PRIMARY KEY (customer_account, item_number, min_qty)
);

CREATE TABLE IF NOT EXISTS order_headers_cache (
    sales_order_number   TEXT NOT NULL,
    customer_account     TEXT NOT NULL,
    order_date           TEXT,
    order_status         TEXT,
    processing_status    TEXT,
    customer_requisition TEXT,
    sales_order_name     TEXT,
    salesman             TEXT,
    customer_name        TEXT,
    last_refreshed       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_lines_cache (
    sales_order_number   TEXT NOT NULL,
    line_number          INTEGER,
    item_number          TEXT,
    line_description     TEXT,
    qty_ordered          REAL,
    sales_price          REAL,
    line_total           REAL,
    line_status          TEXT,
    last_refreshed       TEXT NOT NULL
);

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

CREATE INDEX IF NOT EXISTS idx_runbook_history_ts ON runbook_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_runbook_history_report ON runbook_history(report_name);

CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_email, timestamp);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_email, dismissed);
CREATE INDEX IF NOT EXISTS idx_settings_user ON user_settings(user_email);
CREATE INDEX IF NOT EXISTS idx_cache_group ON dashboard_cache(sales_group);
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_email ON app_users(email);
CREATE INDEX IF NOT EXISTS idx_report_runs_started ON report_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_user_report_access ON user_report_access(user_email);
CREATE INDEX IF NOT EXISTS idx_draft_orders_user ON draft_orders(user_email, status);
CREATE INDEX IF NOT EXISTS idx_order_headers_customer ON order_headers_cache(customer_account);
CREATE INDEX IF NOT EXISTS idx_order_headers_order ON order_headers_cache(sales_order_number);
CREATE INDEX IF NOT EXISTS idx_order_lines_order ON order_lines_cache(sales_order_number);
CREATE INDEX IF NOT EXISTS idx_draft_order_lines_order ON draft_order_lines(draft_order_id);
CREATE INDEX IF NOT EXISTS idx_customer_addresses_account ON customer_addresses(customer_account);
CREATE INDEX IF NOT EXISTS idx_price_cache_customer ON price_cache(customer_account);
CREATE INDEX IF NOT EXISTS idx_price_cache_item ON price_cache(item_number);
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
        # Add dashboard_enabled column if missing (upgrade from older schema)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(app_users)").fetchall()]
        if "dashboard_enabled" not in cols:
            conn.execute("ALTER TABLE app_users ADD COLUMN dashboard_enabled INTEGER DEFAULT 1")
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
        # Migrate customer_addresses: add structured address columns
        addr_cols = [r[1] for r in conn.execute("PRAGMA table_info(customer_addresses)").fetchall()]
        for col, typedef in [("address_id", "TEXT"), ("street", "TEXT"), ("city", "TEXT"),
                             ("state", "TEXT"), ("zip_code", "TEXT"), ("country", "TEXT"),
                             ("source", "TEXT DEFAULT 'manual'")]:
            if col not in addr_cols:
                conn.execute(f"ALTER TABLE customer_addresses ADD COLUMN {col} {typedef}")
        conn.commit()
        # Migrate product_cache: add description column
        prod_cols = [r[1] for r in conn.execute("PRAGMA table_info(product_cache)").fetchall()]
        if prod_cols and "description" not in prod_cols:
            conn.execute("ALTER TABLE product_cache ADD COLUMN description TEXT")
            conn.commit()
        # Migrate history: add azure_job_id for Azure Automation dispatch
        hist_cols = [r[1] for r in conn.execute("PRAGMA table_info(history)").fetchall()]
        if "azure_job_id" not in hist_cols:
            conn.execute("ALTER TABLE history ADD COLUMN azure_job_id TEXT")
            conn.commit()
        # Ensure unique constraint on customer_addresses for idempotent seeding
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_custaddr_uniq "
                "ON customer_addresses(customer_account, label)"
            )
            conn.commit()
        except Exception:
            pass  # index already exists or table has duplicates
        user_count = conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]
        print(f"[db] init_db: app_users table has {user_count} rows after schema init", flush=True)
    finally:
        conn.close()
    migrate_json_history()
    migrate_json_users()
    seed_salesmen()
    seed_report_config()
    seed_feature_flags()
    sync_salesmen_to_users()
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
    """Seed report_config from REPORTS_CONFIG so every report key has a row."""
    from webapp.user_map import REPORTS_CONFIG
    conn = get_db()
    try:
        for rkey in REPORTS_CONFIG:
            conn.execute(
                "INSERT OR IGNORE INTO report_config (report_key, enabled) VALUES (?, 1)",
                (rkey,),
            )
        conn.commit()
    except Exception:
        log.exception("Report config seed failed")
    finally:
        conn.close()


def seed_feature_flags():
    """Seed default feature flags."""
    defaults = [
        ("dashboard_enabled", 1, "Show the Dashboard tab for all users"),
        ("order_entry_enabled", 0, "Show the Order Entry tab for sales reps"),
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


def sync_salesmen_to_users():
    """Ensure every salesman in the salesmen table has a corresponding app_users row.

    Creates placeholder rows (email = key, role = salesman) so they appear
    in the unified user/permissions grid even before a real email is assigned.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        salesmen = conn.execute("SELECT key, full_name FROM salesmen WHERE number != '?unassigned'").fetchall()
        created = 0
        for sm in salesmen:
            existing = conn.execute(
                "SELECT 1 FROM app_users WHERE salesman_key = ?", (sm["key"],)
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT OR IGNORE INTO app_users (email, role, salesman_key, display_name, dashboard_enabled)
                       VALUES (?, 'salesman', ?, ?, 1)""",
                    (sm["key"], sm["key"], sm["full_name"]),
                )
                created += 1
        if created:
            conn.commit()
            print(f"[db] sync_salesmen_to_users: created {created} placeholder user rows", flush=True)
    except Exception:
        log.exception("sync_salesmen_to_users failed")
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
                sm_number, sm_name, active, reports: {report_key: bool}}
    """
    conn = get_db()
    try:
        users = conn.execute(
            """SELECT u.id, u.email, u.role, u.salesman_key, u.display_name,
                      u.dashboard_enabled,
                      s.number AS sm_number, s.full_name AS sm_name, s.active
               FROM app_users u
               LEFT JOIN salesmen s ON u.salesman_key = s.key
               ORDER BY CASE WHEN u.role IN ('admin','developer') THEN 0 ELSE 1 END,
                        s.full_name, u.email"""
        ).fetchall()

        overrides = conn.execute(
            "SELECT user_email, report_key, allowed FROM user_report_access"
        ).fetchall()
        ovr_map: dict[str, dict[str, bool]] = {}
        for o in overrides:
            ovr_map.setdefault(o["user_email"], {})[o["report_key"]] = bool(o["allowed"])

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
            reports = {}
            for rk in report_keys:
                cfg = REPORTS_CONFIG[rk]
                if rk in user_ovr:
                    reports[rk] = user_ovr[rk]
                elif is_adm:
                    reports[rk] = global_cfg.get(rk, True)
                elif cfg.get("salesman_filter"):
                    reports[rk] = global_cfg.get(rk, True)
                else:
                    reports[rk] = False
            d["reports"] = reports
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


# -- Order headers / lines cache -------------------------------------------

def upsert_order_headers_cache(rows: list[dict]):
    """Replace all cached order headers with fresh data."""
    if not rows:
        return
    conn = get_db()
    try:
        conn.execute("DELETE FROM order_headers_cache")
        conn.executemany(
            """INSERT INTO order_headers_cache
               (sales_order_number, customer_account, order_date, order_status,
                processing_status, customer_requisition, sales_order_name,
                salesman, customer_name, last_refreshed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(r["sales_order_number"], r["customer_account"], r.get("order_date"),
              r.get("order_status"), r.get("processing_status"),
              r.get("customer_requisition"), r.get("sales_order_name"),
              r.get("salesman"), r.get("customer_name"), r["last_refreshed"])
             for r in rows],
        )
        conn.commit()
        log.info("order_headers_cache: upserted %d rows", len(rows))
    finally:
        conn.close()


def upsert_order_lines_cache(rows: list[dict]):
    """Replace all cached order lines with fresh data."""
    if not rows:
        return
    conn = get_db()
    try:
        conn.execute("DELETE FROM order_lines_cache")
        conn.executemany(
            """INSERT INTO order_lines_cache
               (sales_order_number, line_number, item_number, line_description,
                qty_ordered, sales_price, line_total, line_status, last_refreshed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(r["sales_order_number"], r.get("line_number"), r.get("item_number"),
              r.get("line_description"), r.get("qty_ordered"), r.get("sales_price"),
              r.get("line_total"), r.get("line_status"), r["last_refreshed"])
             for r in rows],
        )
        conn.commit()
        log.info("order_lines_cache: upserted %d rows", len(rows))
    finally:
        conn.close()


def get_cached_orders(customer_account: str, start_date: str | None = None,
                      end_date: str | None = None, last_n: int | None = None) -> list[dict]:
    """Return cached order headers for a customer, optionally filtered by date."""
    conn = get_db()
    try:
        sql = "SELECT * FROM order_headers_cache WHERE customer_account = ?"
        params: list = [customer_account]
        if start_date:
            sql += " AND order_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND order_date <= ?"
            params.append(end_date)
        sql += " ORDER BY order_date DESC"
        if last_n:
            sql += " LIMIT ?"
            params.append(last_n)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_cached_order_detail(order_number: str) -> tuple[dict | None, list[dict]]:
    """Return (header_dict, lines_list) from cache for a single order."""
    conn = get_db()
    try:
        hdr = conn.execute(
            "SELECT * FROM order_headers_cache WHERE sales_order_number = ?",
            (order_number,),
        ).fetchone()
        header = dict(hdr) if hdr else None
        lines = [dict(r) for r in conn.execute(
            "SELECT * FROM order_lines_cache WHERE sales_order_number = ? ORDER BY line_number",
            (order_number,),
        ).fetchall()]
        return header, lines
    finally:
        conn.close()


def get_order_headers_count() -> int:
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM order_headers_cache").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


def get_order_lines_count() -> int:
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM order_lines_cache").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


def update_record_job_id(user_email: str, record_id: str, azure_job_id: str):
    """Store the Azure Automation job ID on a history record."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE history SET azure_job_id = ? WHERE record_id = ? AND user_email = ?",
            (azure_job_id, record_id, user_email),
        )
        conn.commit()
    finally:
        conn.close()


def get_record_job_id(record_id: str) -> str | None:
    """Retrieve the Azure Automation job ID for a history record."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT azure_job_id FROM history WHERE record_id = ?", (record_id,)
        ).fetchone()
        return row["azure_job_id"] if row and row["azure_job_id"] else None
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
                    "SELECT id FROM runbook_history WHERE job_id = ?", (job_id,)
                ).fetchone()
                if existing:
                    conn.execute(
                        """UPDATE runbook_history
                           SET status = ?, duration_sec = ?, end_time = ?,
                               error = ?, rows_output = ?, files_uploaded = ?
                           WHERE job_id = ?""",
                        (r.get("status"), r.get("duration_sec"), r.get("end_time"),
                         r.get("error"), r.get("rows_output"), r.get("files_uploaded"),
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
