"""Database access for the rebuilt reports app."""

# === What's in this file ===
# Two SQLite databases live on local disk:
#   precious.db -- the data we can't lose (users, jobs, schedules, config, audit).
#                  Litestream backs it up to Azure Blob.
#   cache.db    -- throwaway report results. If it vanishes we just rebuild it.
#
# Everything talks to the database through a small wrapper called Conn instead
# of the raw sqlite3 library. That wrapper is the single seam that lets us swap
# to Postgres later without touching every query: services only ever see
# execute / fetchone / fetchall / commit, never a sqlite-specific object.
#
# === Postgres off-ramp seam points (the 5 things a swap would re-implement) ===
#   1. Conn -- the duck-typed connection wrapper (execute/fetchone/fetchall/commit).
#   2. utc_now_iso() -- timestamps come from Python, never SQL's datetime('now'),
#      so date logic doesn't depend on the database engine.
#   3. JSON is stored as TEXT and encoded/decoded at the repository edge, never
#      with SQLite-only json_extract() in service queries.
#   4. JobRepository.claim_next() -- the one place that atomically grabs a job;
#      a Postgres version would use SELECT ... FOR UPDATE SKIP LOCKED here.
#   5. migrate.lock_for_migration() -- the one place that serializes migrations.
#
# utc_now_iso() -- current UTC time as an ISO string (single source for timestamps)
# Conn -- thin wrapper over a sqlite3 connection exposing the portable protocol
# Database -- opens precious()/cache() connections; cache self-heals if deleted

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, Protocol, Sequence

from ..config import Config


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_email(email: str | None) -> str:
    """One spelling of an email for storage and lookups: trimmed, lowercased.
    Used everywhere an email is a key so the same person always matches."""
    return (email or "").strip().lower()


class Connection(Protocol):
    """What services are allowed to assume about a database connection.

    Anything implementing this (SQLite today, Postgres tomorrow) is a drop-in.
    """

    def execute(self, sql: str, params: Sequence[Any] = ...) -> Any: ...
    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> Any: ...
    def fetchone(self, sql: str, params: Sequence[Any] = ...) -> Any: ...
    def fetchall(self, sql: str, params: Sequence[Any] = ...) -> list[Any]: ...
    def commit(self) -> None: ...


class Conn:
    """Wraps a sqlite3 connection so callers use one small, portable surface.

    Connections run in autocommit mode (each statement lands immediately). When
    several writes must succeed or fail together, wrap them in `transaction()`.

    Return types are deliberately loose (Any / mapping-like rows) so the sqlite
    specifics stay private to this layer and a Postgres wrapper can be a drop-in.
    """

    def __init__(self, raw: sqlite3.Connection) -> None:
        self._raw = raw

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        return self._raw.execute(sql, params)

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> Any:
        return self._raw.executemany(sql, rows)

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[Mapping[str, Any]]:
        return self._raw.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[Mapping[str, Any]]:
        return self._raw.execute(sql, params).fetchall()

    def commit(self) -> None:
        self._raw.commit()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Run several writes as one all-or-nothing unit.

        BEGIN IMMEDIATE takes the write lock up front so concurrent writers wait
        instead of racing; on any error everything rolls back.
        """
        self._raw.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._raw.execute("COMMIT")
        except Exception:
            self._raw.execute("ROLLBACK")
            raise


_BUSY_TIMEOUT_MS = 5000


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(path), timeout=_BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA busy_timeout=%d" % _BUSY_TIMEOUT_MS)
    raw.execute("PRAGMA foreign_keys=ON")
    return raw


class Database:
    def __init__(self, config: Config) -> None:
        self._config = config

    @contextmanager
    def precious(self) -> Iterator[Conn]:
        raw = _open(self._config.precious_db_path)
        try:
            yield Conn(raw)
        finally:
            raw.close()

    @contextmanager
    def cache(self) -> Iterator[Conn]:
        """Open the throwaway database, rebuilding its schema if it went missing.

        Every open cheaply checks the schema is actually there. If cache.db was
        deleted OR its tables were dropped after an earlier heal, this re-creates
        the schema instead of crashing with "no such table". Checking each time
        (rather than remembering "already healed") keeps it correct across
        threads and across a database that gets wiped underneath us.
        """
        raw = _open(self._config.cache_db_path)
        try:
            from .migrate import cache_schema_present, ensure_cache_schema

            conn = Conn(raw)
            if not cache_schema_present(conn):
                ensure_cache_schema(conn)
            yield conn
        finally:
            raw.close()
