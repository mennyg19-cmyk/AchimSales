"""Fail-closed checks for the home-site precious.db.

Prod must not migrate or serve a missing, zero-byte, corrupt, or empty-of-users
file. Dev still allows a brand-new sqlite (tests and local first run).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

SENTINEL_KEY = "site_db_role"
SENTINEL_VALUE = "home"

_REQUIRED_AFTER = (
    "users",
    "jobs",
    "app_settings",
    "schema_migrations",
    "schedules",
    "master_schedules",
)


class PreciousIntegrityError(RuntimeError):
    """The serving database is not safe to migrate or boot."""


def assert_before_migrate(path: Path) -> None:
    """Nonzero file, quick_check, at least one user. No schema-level requirement
    so a pre-0016 replica can still migrate forward."""
    conn = _open_ro(path)
    try:
        _quick_check(conn)
        _require_users(conn)
    finally:
        conn.close()


def assert_after_migrate(path: Path) -> None:
    """Same as before-migrate, plus required tables, latest migration, sentinel."""
    from web.data.migrate import precious_migration_stems

    conn = _open_ro(path)
    try:
        _quick_check(conn)
        _require_users(conn)
        missing = [name for name in _REQUIRED_AFTER if not _table_exists(conn, name)]
        if missing:
            raise PreciousIntegrityError(
                "precious db missing required tables after migrate: "
                + ", ".join(missing)
            )
        stems = precious_migration_stems()
        if not stems:
            raise PreciousIntegrityError("no precious migrations found on disk")
        latest = stems[-1]
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        if latest not in applied:
            raise PreciousIntegrityError(
                f"schema {latest} is not applied (refusing a stale serving db)"
            )
    finally:
        conn.close()
    _ensure_sentinel(path)


def _open_ro(path: Path) -> sqlite3.Connection:
    # Do not use connection._connect: that mkdir+connect would create an empty file.
    if not path.is_file():
        raise PreciousIntegrityError("precious db is missing after restore")
    if path.stat().st_size == 0:
        raise PreciousIntegrityError("precious db is zero bytes after restore")
    uri = path.resolve().as_posix()
    try:
        conn = sqlite3.connect(f"file:{uri}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.Error as exc:
        raise PreciousIntegrityError(f"precious db could not be opened: {exc}") from exc
    conn.row_factory = sqlite3.Row
    return conn


def _quick_check(conn: sqlite3.Connection) -> None:
    try:
        row = conn.execute("PRAGMA quick_check").fetchone()
    except sqlite3.Error as exc:
        raise PreciousIntegrityError(f"PRAGMA quick_check failed: {exc}") from exc
    result = str(row[0]) if row else ""
    if result.lower() != "ok":
        raise PreciousIntegrityError(f"PRAGMA quick_check failed: {result or 'no result'}")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _require_users(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "users"):
        raise PreciousIntegrityError(
            "precious db has no users table; refusing to treat it as the site database"
        )
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if n < 1:
        raise PreciousIntegrityError(
            "precious db has no users; refusing to boot an empty site"
        )


def _ensure_sentinel(path: Path) -> None:
    from web.data.connection import _connect

    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key=?",
            (SENTINEL_KEY,),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO app_settings(key, value) VALUES (?, ?)",
                (SENTINEL_KEY, SENTINEL_VALUE),
            )
            conn.commit()
            return
        if str(row[0]) != SENTINEL_VALUE:
            raise PreciousIntegrityError(
                f"{SENTINEL_KEY} is {row[0]!r}, expected {SENTINEL_VALUE!r}"
            )
    finally:
        conn.close()


def file_quick_check_ok(path: Path) -> bool:
    """True when the file exists, is nonempty, and PRAGMA quick_check is ok.

    Used by /readyz. Does not require users (HTTP tests migrate with an empty
    user table). Never creates the file.
    """
    try:
        conn = _open_ro(path)
        try:
            _quick_check(conn)
        finally:
            conn.close()
        return True
    except PreciousIntegrityError:
        return False


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] not in {"before", "after"}:
        print(
            "usage: python -m web.data.precious_integrity before|after PATH",
            file=sys.stderr,
        )
        return 2
    path = Path(args[1])
    try:
        if args[0] == "before":
            assert_before_migrate(path)
        else:
            assert_after_migrate(path)
    except PreciousIntegrityError as exc:
        print(f"precious integrity: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
