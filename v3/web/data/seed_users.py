"""Copy the user directory from the live app into v3's `users` table.

Live (webapp/) is the list of who may sign in. Home (v3) is the source of
truth for an existing person's role, flags, and extra salesman grants.
Boot inserts people who are not on home yet, and adds Live salesman grants
that home is missing. It does not overwrite a role saved on Users & access.
V3_ADMIN_EMAILS / V3_DEVELOPER_EMAILS still win after this.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from report_engine.lib import salesman_key as _normalize_salesman_key
from web.auth.principal import ROLE_SALESMAN, VALID_ROLES
from web.data.connection import Database


def live_db_path() -> Path:
    """Where the live app keeps app.db. Env-overridable; matches webapp/db.py."""
    return Path(os.environ.get("LIVE_DB_PATH") or "/home/data/app.db")


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def read_live_users(path: Path | str | None = None) -> list[dict]:
    """Read app_users from the live DB. Returns [] if the file/table is absent."""
    path = Path(path) if path is not None else live_db_path()
    if not path.is_file():
        return []
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cols = _columns(conn, "app_users")
        if "email" not in cols:
            return []
        wanted = [c for c in ("email", "role", "salesman_key", "display_name",
                              "dashboard_enabled", "is_external") if c in cols]
        rows = conn.execute(f"SELECT {', '.join(wanted)} FROM app_users").fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    out: list[dict] = []
    for r in rows:
        d = {k: r[k] for k in r.keys()}
        email = (d.get("email") or "").strip().lower()
        if not email or "@" not in email:
            continue
        role = (d.get("role") or "").strip().lower()
        out.append({
            "email": email,
            "role": role if role in VALID_ROLES else ROLE_SALESMAN,
            "salesman_key": (d.get("salesman_key") or "").strip() or None,
            "display_name": (d.get("display_name") or "").strip(),
            "dashboard_enabled": 1 if d.get("dashboard_enabled") else 0,
            "is_external": 1 if d.get("is_external") else 0,
        })
    return out


def read_live_salesman_access(path: Path | str | None = None) -> list[tuple[str, str]]:
    """Live manager (and salesman) grants: (email, salesman_key). Missing table → []."""
    path = Path(path) if path is not None else live_db_path()
    if not path.is_file():
        return []
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT user_email, salesman_key FROM user_salesman_access"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    out: list[tuple[str, str]] = []
    for r in rows:
        email = (r["user_email"] or "").strip().lower()
        key = (r["salesman_key"] or "").strip()
        if email and "@" in email and key:
            out.append((email, key))
    return out


def copy_live_users(
    db: Database,
    users: list[dict],
    access_rows: list[tuple[str, str]] | None = None,
) -> int:
    """Insert new Live users; add missing salesman grants. Does not change existing roles."""
    access_rows = access_rows or []
    if not users and not access_rows:
        return 0
    with db.precious() as conn:
        existing_salesmen = {r[0] for r in conn.execute("SELECT key FROM salesmen")}
        for u in users:
            conn.execute(
                "INSERT INTO users(email, display_name, role, is_active,"
                " is_external, dashboard_enabled) VALUES (?, ?, ?, 1, ?, ?)"
                " ON CONFLICT(email) DO NOTHING",
                (u["email"], u["display_name"], u["role"],
                 u["is_external"], u["dashboard_enabled"]),
            )
        by_email: dict[str, set[str]] = {}

        def _grant(email: str, raw_key: str) -> None:
            e = (email or "").strip().lower()
            k = _normalize_salesman_key(raw_key or "")
            if e and k and k in existing_salesmen:
                by_email.setdefault(e, set()).add(k)

        for u in users:
            if u.get("salesman_key"):
                _grant(u["email"], u["salesman_key"])
        for email, key in access_rows:
            _grant(email, key)
        for email, keys in by_email.items():
            row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if row is None:
                continue
            uid = row["id"]
            conn.executemany(
                "INSERT OR IGNORE INTO user_salesman_access(user_id, salesman_key)"
                " VALUES (?, ?)",
                [(uid, k) for k in keys],
            )
    return len(users)


def seed_users_from_live(db: Database, path: Path | str | None = None) -> int:
    path = Path(path) if path is not None else live_db_path()
    return copy_live_users(db, read_live_users(path), read_live_salesman_access(path))
