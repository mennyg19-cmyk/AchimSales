"""SQLite connection management for the precious + cache databases.

Each call gets a fresh connection with WAL + foreign keys on (cheap on local
disk, safe under gunicorn gthread workers - no shared connection across threads).
This is local-disk SQLite only; Litestream replicates the precious file
out-of-process. There is NO /tmp->/home snapshot or JSON-sidecar salvage here
(forbidden by rule 5).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
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
