"""Optional copy of leftover Azure `app.db` users into v3's `users` table.

Reads that sqlite file directly (read-only). Roles map 1:1. A user's
salesman_key is mapped into `user_salesman_access` when that salesman exists
in v3's `salesmen` table (skipped otherwise — the FK would reject it).

Re-running updates role/flags/display_name. Salesman grants are replaced, not
merged. Explicit env admins (V3_ADMIN_EMAILS) are applied after this and win.
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


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _grant_keys_by_email(conn: sqlite3.Connection) -> dict[str, list[str]]:
    if "user_salesman_access" not in _tables(conn):
        return {}
    cols = _columns(conn, "user_salesman_access")
    if "salesman_key" not in cols:
        return {}
    if "user_email" in cols:
        rows = conn.execute(
            "SELECT user_email, salesman_key FROM user_salesman_access"
        )
    elif "email" in cols:
        rows = conn.execute(
            "SELECT email, salesman_key FROM user_salesman_access"
        )
    else:
        return {}
    out: dict[str, list[str]] = {}
    for r in rows:
        email = (r[0] or "").strip().lower()
        key = (r[1] or "").strip()
        if email and key:
            out.setdefault(email, []).append(key)
    return out


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
        try:
            grants = _grant_keys_by_email(conn)
        except sqlite3.Error:
            grants = {}
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
        keys: list[str] = []
        primary = (d.get("salesman_key") or "").strip()
        if primary:
            keys.append(primary)
        for key in grants.get(email, []):
            if key not in keys:
                keys.append(key)
        out.append({
            "email": email,
            "role": role if role in VALID_ROLES else ROLE_SALESMAN,
            "salesman_key": primary or None,
            "salesman_keys": keys,
            "display_name": (d.get("display_name") or "").strip(),
            "dashboard_enabled": 1 if d.get("dashboard_enabled") else 0,
            "is_external": 1 if d.get("is_external") else 0,
        })
    return out


def copy_live_users(db: Database, users: list[dict]) -> tuple[int, int]:
    """Upsert live users into v3. Returns (users written, grants written)."""
    if not users:
        return 0, 0
    grants_written = 0
    with db.precious() as conn:
        existing_salesmen = {r[0] for r in conn.execute("SELECT key FROM salesmen")}
        for u in users:
            conn.execute(
                "INSERT INTO users(email, display_name, role, is_active,"
                " is_external, dashboard_enabled) VALUES (?, ?, ?, 1, ?, ?)"
                " ON CONFLICT(email) DO UPDATE SET"
                "   display_name=excluded.display_name,"
                "   role=excluded.role,"
                "   is_external=excluded.is_external,"
                "   dashboard_enabled=excluded.dashboard_enabled",
                (u["email"], u["display_name"], u["role"],
                 u["is_external"], u["dashboard_enabled"]),
            )
            uid = conn.execute(
                "SELECT id FROM users WHERE email = ?", (u["email"],)
            ).fetchone()["id"]
            conn.execute("DELETE FROM user_salesman_access WHERE user_id = ?", (uid,))
            seen: set[str] = set()
            raw_keys = u.get("salesman_keys")
            if raw_keys is None and u.get("salesman_key"):
                raw_keys = [u["salesman_key"]]
            for raw in raw_keys or []:
                key = _normalize_salesman_key(raw or "")
                if not key or key not in existing_salesmen or key in seen:
                    continue
                seen.add(key)
                conn.execute(
                    "INSERT OR IGNORE INTO user_salesman_access(user_id, salesman_key)"
                    " VALUES (?, ?)",
                    (uid, key),
                )
                grants_written += 1
    return len(users), grants_written


def seed_users_from_live(db: Database, path: Path | str | None = None) -> int:
    n_users, _n_grants = copy_live_users(db, read_live_users(path))
    return n_users
