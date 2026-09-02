"""Versioned migration runner (plan section 6: no ad-hoc ALTER TABLE at boot).

Each database has its own ordered set of `NNNN_name.sql` files. Applied versions
are tracked in a `schema_migrations` table; pending files are applied in order,
each in its own transaction. Re-running is a no-op (idempotent).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from web.data.connection import Database, _connect

_MIGRATIONS_ROOT = Path(__file__).resolve().parent / "migrations"


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )


def _applied(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def apply_migrations(path: Path, migrations_dir: Path) -> list[str]:
    """Apply pending migrations in `migrations_dir` to the DB at `path`.

    Each migration's DDL AND its `schema_migrations` row are applied in a SINGLE
    transaction, so a failure can never leave the schema changed but the version
    untracked (atomicity). Returns the list of versions newly applied.
    """
    conn = _connect(path)
    newly: list[str] = []
    try:
        _ensure_table(conn)
        done = _applied(conn)
        files = sorted(migrations_dir.glob("*.sql")) if migrations_dir.exists() else []
        for f in files:
            version = f.stem
            if version in done:
                continue
            ts = datetime.now(timezone.utc).isoformat()
            # version + ts embedded as literals so the version insert lives inside
            # the same BEGIN/COMMIT as the migration body (one atomic unit).
            # IMMEDIATE takes the write lock up front: a worker that loses the
            # boot race waits (busy_timeout) instead of deadlocking on a
            # read->write lock upgrade halfway through the script.
            script = (
                "BEGIN IMMEDIATE;\n"
                + f.read_text(encoding="utf-8")
                + "\nINSERT INTO schema_migrations(version, applied_at) VALUES "
                + f"({_sql_literal(version)}, {_sql_literal(ts)});\n"
                + "COMMIT;"
            )
            try:
                conn.executescript(script)
            except Exception as exc:
                conn.rollback()  # discard the partial, uncommitted migration
                # Gunicorn workers boot in parallel and can race to apply the
                # same pending migration. The loser fails (duplicate version row
                # or "table already exists"); if the version is now recorded as
                # applied, the winner did our work - skip it, don't crash boot.
                if version in _applied(conn):
                    continue
                # ALTER TABLE ADD COLUMN is not always transactional. If the
                # column landed but schema_migrations did not, the next boot
                # would raise duplicate-column and never start the scheduler.
                if "duplicate column name" in str(exc).lower():
                    conn.execute(
                        "INSERT OR IGNORE INTO schema_migrations(version, applied_at)"
                        " VALUES (?, ?)",
                        (version, ts),
                    )
                    conn.commit()
                    newly.append(version)
                    continue
                raise
            newly.append(version)
        return newly
    finally:
        conn.close()


def migrate(db: Database) -> dict[str, list[str]]:
    """Apply both databases' migrations. Returns {db_name: [applied versions]}."""
    precious = apply_migrations(db.precious_path, _MIGRATIONS_ROOT / "precious")
    _ensure_users_company_views_column(db.precious_path)
    _ensure_users_sales_group_column(db.precious_path)
    from web.scheduling.personal_views import convert_personal_schedules

    convert_personal_schedules(db)
    return {
        "precious": precious,
        "cache": migrate_cache_only(db),
    }


def _ensure_users_company_views_column(path: Path) -> None:
    """Add can_see_company_views if 0016 was skipped or the column was lost."""
    conn = _connect(path)
    try:
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "users" not in tables:
            return
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        if "can_see_company_views" in cols:
            return
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN can_see_company_views INTEGER NOT NULL DEFAULT 0"
            )
            conn.execute(
                "UPDATE users SET can_see_company_views = 1 WHERE role = 'developer'"
            )
            conn.commit()
        except sqlite3.OperationalError as exc:
            conn.rollback()
            # Parallel gunicorn workers can both see a missing column and ALTER.
            if "duplicate column name" not in str(exc).lower():
                raise
    finally:
        conn.close()


def _ensure_users_sales_group_column(path: Path) -> None:
    """Add sales_group if 0017 was skipped or the column was lost."""
    conn = _connect(path)
    try:
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "users" not in tables:
            return
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        if "sales_group" in cols:
            return
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN sales_group TEXT NOT NULL DEFAULT ''"
            )
            conn.commit()
        except sqlite3.OperationalError as exc:
            conn.rollback()
            if "duplicate column name" not in str(exc).lower():
                raise
    finally:
        conn.close()


def migrate_cache_only(db: Database) -> list[str]:
    """Re-create the disposable cache schema. cache.db can vanish between boots
    (it's deletable by design), so the report cache uses this to self-heal when
    it finds the file fresh and table-less mid-flight."""
    return apply_migrations(db.cache_path, _MIGRATIONS_ROOT / "cache")
