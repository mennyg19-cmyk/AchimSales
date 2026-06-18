"""SQLite connection management for the precious + cache databases.

Each call gets a fresh connection with foreign keys on and a journal mode that
defaults to WAL (the right choice on local disk; Litestream replicates the
precious file out-of-process). The journal mode is overridable via
SQLITE_JOURNAL_MODE because WAL is BROKEN on an Azure Files / SMB share -- see
_journal_mode() for the why. There is NO /tmp->/home snapshot or JSON-sidecar
salvage here (forbidden by rule 5).
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_JOURNAL_SWITCH_RETRIES = 20
_VALID_JOURNAL_MODES = {"WAL", "DELETE", "TRUNCATE", "PERSIST", "MEMORY"}


def _journal_mode() -> str:
    """Which SQLite journaling mode to open with (default WAL).

    WAL is fastest and correct on local disk, but it does NOT work on an Azure
    Files / SMB share: WAL coordinates readers and writers through a shared-memory
    index (the -shm file) that SMB can't share across processes, so one process
    can't see another's committed rows. That's how the job queue silently stalls
    -- a web worker enqueues a job the background worker never sees. A rollback
    journal (DELETE/TRUNCATE) uses plain file locks that DO work over SMB, so set
    SQLITE_JOURNAL_MODE=TRUNCATE while the DB lives on /home. The proper fix is to
    move the DB to local disk per rule 5 and drop this override.
    """
    mode = os.environ.get("SQLITE_JOURNAL_MODE", "WAL").strip().upper()
    return mode if mode in _VALID_JOURNAL_MODES else "WAL"


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    # Switching journal mode needs exclusive access and can return "database is
    # locked" IMMEDIATELY (it skips the busy handler) when connections race --
    # e.g. parallel gunicorn workers touching a brand-new DB at boot. Retry with
    # a short backoff instead of failing the caller. (The mode value comes from a
    # fixed allowlist, so it's safe to interpolate into the PRAGMA.)
    mode = _journal_mode()
    for attempt in range(_JOURNAL_SWITCH_RETRIES):
        try:
            conn.execute(f"PRAGMA journal_mode={mode}")
            break
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or attempt == _JOURNAL_SWITCH_RETRIES - 1:
                conn.close()
                raise
            time.sleep(0.05 * (attempt + 1))
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class Database:
    """Holds the two DB paths and hands out connections/transactions."""

    def __init__(self, precious_path: Path, cache_path: Path):
        self.precious_path = precious_path
        self.cache_path = cache_path

    @contextmanager
    def precious(self) -> Iterator[sqlite3.Connection]:
        yield from self._scoped(self.precious_path)

    @contextmanager
    def cache(self) -> Iterator[sqlite3.Connection]:
        yield from self._scoped(self.cache_path)

    @staticmethod
    def _scoped(path: Path) -> Iterator[sqlite3.Connection]:
        conn = _connect(path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def from_config(cfg) -> Database:
    """Build a Database from a web.config.Config."""
    return Database(cfg.precious_db_path, cfg.cache_db_path)
