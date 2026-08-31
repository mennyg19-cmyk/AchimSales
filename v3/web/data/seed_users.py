"""Copy the user directory from the live app into v3's `users` table.

The live app (webapp/) is the authoritative user directory: it stores every
authorized account in its SQLite DB (`app_users`: email, role, salesman_key,
display_name, dashboard_enabled, is_external). v3 mirrors that list on boot so
the same people - with the same roles - can sign in to /test without being
re-entered by hand.

This reads the live DB *file* directly (read-only); it never imports live code,
so v3 stays decoupled. Roles map 1:1 (admin|developer|manager|salesman). A
user's salesman_key is mapped into v3's `user_salesman_access` when that salesman
exists in v3's `salesmen` table (skipped otherwise - the FK would reject it).

Mirror semantics: re-running updates role/flags/display_name to match live, so
live remains the source of truth for who can sign in. Explicit env admins
(V3_ADMIN_EMAILS) are applied *after* this and always win.
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


def copy_live_users(db: Database, users: list[dict]) -> int:
    """Upsert live users into v3. Returns the number of users written."""
    if not users:
        return 0
    with db.precious() as conn:
        existing_salesmen = {r[0] for r in conn.execute("SELECT key FROM salesmen")}
        for u in users:
            views_flag = 1 if u["role"] == "developer" else 0
            conn.execute(
                "INSERT INTO users(email, display_name, role, is_active,"
                " is_external, dashboard_enabled, can_see_company_views)"
                " VALUES (?, ?, ?, 1, ?, ?, ?)"
                " ON CONFLICT(email) DO UPDATE SET"
                "   display_name=excluded.display_name,"
                "   role=excluded.role,"
                "   is_external=excluded.is_external,"
                "   dashboard_enabled=excluded.dashboard_enabled",
                (u["email"], u["display_name"], u["role"],
                 u["is_external"], u["dashboard_enabled"], views_flag),
            )
            key = _normalize_salesman_key(u["salesman_key"] or "")
            if key and key in existing_salesmen:
                uid = conn.execute(
                    "SELECT id FROM users WHERE email = ?", (u["email"],)
                ).fetchone()["id"]
                conn.execute(
                    "INSERT OR IGNORE INTO user_salesman_access(user_id, salesman_key)"
                    " VALUES (?, ?)",
                    (uid, key),
                )
    return len(users)


def seed_users_from_live(db: Database, path: Path | str | None = None) -> int:
    return copy_live_users(db, read_live_users(path))
