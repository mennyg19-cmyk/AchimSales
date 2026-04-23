"""SQLite layer for the v2 app.

Kept intentionally small. Right now we only track app_users (populated on
sign-in). Other tables (saved layouts, schedules) will be added when their
features are rebuilt.

All paths live under test/app.db -- completely separate from the live app.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
from typing import Iterator

from test.config.settings import APP_DB_PATH

log = logging.getLogger(__name__)

_lock = threading.Lock()


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS app_users (
        email           TEXT PRIMARY KEY,
        display_name    TEXT,
        is_admin        INTEGER NOT NULL DEFAULT 0,
        first_login_utc TEXT,
        last_login_utc  TEXT
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
        created_utc  TEXT    NOT NULL,
        UNIQUE(user_email, name)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_saved_reports_user
        ON saved_reports(user_email, created_utc DESC)
    """,
]


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
        log.info("v2 db initialized at %s", APP_DB_PATH)
