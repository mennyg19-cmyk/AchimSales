"""Database setup and version upgrades."""

# === What's in this file ===
# Schema changes live as plain .sql files in migrations/precious/ and
# migrations/cache/, named like 0001_initial.sql, 0002_*.sql. Each database
# remembers which files it has already run in a schema_migrations table, so
# applying twice is safe -- already-applied files are skipped.
#
# Only one process should set up the database at a time (two at once race and
# corrupt it). lock_for_migration() is the single place that serializes them;
# it's also the seam a Postgres version would re-implement with an advisory lock.
#
# lock_for_migration() -- take an exclusive write lock for the duration of setup
# _migration_files() -- list the .sql files for a database, in order
# _applied_versions() -- read which files a database has already run
# _apply() -- run any not-yet-applied files against a connection
# apply_precious_migrations() -- set up / upgrade the durable database
# ensure_cache_schema() -- set up the throwaway database (used by self-heal)

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .connection import Conn, Database, utc_now_iso

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


@contextmanager
def lock_for_migration(conn: Conn) -> Iterator[None]:
    """Serialize setup so two processes never migrate at the same time.

    Holds SQLite's write lock for the whole migration; a second process waits
    (up to the busy timeout) instead of racing. This is one of the Postgres
    off-ramp seam points -- swap it for a transaction-level advisory lock there.
    """
    with conn.transaction():
        yield


def _migration_files(which: str) -> list[Path]:
    folder = _MIGRATIONS_DIR / which
    if not folder.exists():
        return []
    return sorted(folder.glob("*.sql"))


def _split_statements(sql: str) -> list[str]:
    """Split a trusted in-repo .sql file into individual statements.

    Strips full-line `--` comments, then splits on semicolons. The migration
    files are our own simple DDL (no semicolons inside string literals), so this
    is safe and avoids sqlite's executescript, which would commit our migration
    transaction out from under us.
    """
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return [stmt.strip() for stmt in "\n".join(lines).split(";") if stmt.strip()]


def _ensure_version_table(conn: Conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  version TEXT PRIMARY KEY,"
        "  applied_at TEXT NOT NULL"
        ")"
    )


def _applied_versions(conn: Conn) -> set[str]:
    _ensure_version_table(conn)
    return {row["version"] for row in conn.fetchall("SELECT version FROM schema_migrations")}


def _apply(conn: Conn, which: str) -> list[str]:
    applied = _applied_versions(conn)
    newly: list[str] = []
    for path in _migration_files(which):
        version = path.name
        if version in applied:
            continue
        for statement in _split_statements(path.read_text(encoding="utf-8")):
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, utc_now_iso()),
        )
        newly.append(version)
    return newly


def apply_precious_migrations(db: Database) -> list[str]:
    with db.precious() as conn:
        with lock_for_migration(conn):
            return _apply(conn, "precious")


def ensure_cache_schema(conn: Conn) -> list[str]:
    with conn.transaction():
        return _apply(conn, "cache")
