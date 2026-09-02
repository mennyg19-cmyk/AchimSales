"""User repository (precious.db `users` table)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from report_engine.lib import salesman_key
from web.auth.principal import ROLE_DEVELOPER
from web.data.connection import Database


@dataclass(frozen=True)
class User:
    id: int
    email: str
    display_name: str
    role: str
    is_active: bool
    is_external: bool
    dashboard_enabled: bool
    sharepoint_access: bool
    test_access: bool
    can_see_company_views: bool
    sales_group: str = ""

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "User":
        keys = set(r.keys())
        views = bool(r["can_see_company_views"]) if "can_see_company_views" in keys else False
        sales_group = r["sales_group"] if "sales_group" in keys else ""
        return cls(
            id=r["id"], email=r["email"], display_name=r["display_name"], role=r["role"],
            is_active=bool(r["is_active"]), is_external=bool(r["is_external"]),
            dashboard_enabled=bool(r["dashboard_enabled"]),
            sharepoint_access=bool(r["sharepoint_access"]), test_access=bool(r["test_access"]),
            can_see_company_views=views, sales_group=sales_group or "",
        )


class UserRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
            ).fetchone()
            return User.from_row(row) if row else None

    def upsert(self, email: str, *, display_name: str = "", role: str = "salesman") -> User:
        email = email.lower().strip()
        views_flag = 1 if role == ROLE_DEVELOPER else 0
        with self.db.precious() as conn:
            conn.execute(
                "INSERT INTO users(email, display_name, role, can_see_company_views)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(email) DO UPDATE SET"
                "   display_name=excluded.display_name WHERE excluded.display_name <> ''",
                (email, display_name, role, views_flag),
            )
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            return User.from_row(row)

    # --- admin operations ---------------------------------------------------

    _FLAGS = (
        "is_active", "is_external", "dashboard_enabled", "sharepoint_access",
        "test_access", "can_see_company_views",
    )

    def list_all(self) -> list[User]:
        with self.db.precious() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY email").fetchall()
        return [User.from_row(r) for r in rows]

    def all_users(self, *, include_inactive: bool = False) -> list[User]:
        """All users, optionally including inactive (for impersonation picker)."""
        with self.db.precious() as conn:
            if include_inactive:
                rows = conn.execute("SELECT * FROM users ORDER BY role, email").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM users WHERE is_active = 1 ORDER BY role, email"
                ).fetchall()
        return [User.from_row(r) for r in rows]

    def get_by_id(self, user_id: int) -> User | None:
        with self.db.precious() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return User.from_row(row) if row else None

    def create(self, email: str, *, role: str, display_name: str = "",
               is_external: bool = False, sales_group: str = "") -> User:
        email = email.lower().strip()
        views_flag = 1 if role == ROLE_DEVELOPER else 0
        sales_group = (sales_group or "").strip()
        with self.db.precious() as conn:
            conn.execute(
                "INSERT INTO users(email, display_name, role, is_external,"
                " can_see_company_views, sales_group)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(email) DO UPDATE SET role=excluded.role,"
                "   display_name=excluded.display_name, is_external=excluded.is_external,"
                "   sales_group=excluded.sales_group",
                (email, display_name, role, 1 if is_external else 0, views_flag, sales_group),
            )
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return User.from_row(row)

    def update(self, user_id: int, *, role: str | None = None,
               sales_group: str | None = None, **flags: bool) -> None:
        """Update role, SalesGroup, and/or any boolean flags. Unknown flag names are ignored."""
        sets: list[str] = []
        vals: list[object] = []
        if role is not None:
            sets.append("role = ?")
            vals.append(role)
        if sales_group is not None:
            sets.append("sales_group = ?")
            vals.append(sales_group.strip())
        for name, value in flags.items():
            if name in self._FLAGS and value is not None:
                sets.append(f"{name} = ?")
                vals.append(1 if value else 0)
        if not sets:
            return
        vals.append(user_id)
        with self.db.precious() as conn:
            conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", vals)

    def delete(self, user_id: int) -> None:
        """Delete a user; FK ON DELETE CASCADE removes access/prefs/saved rows."""
        with self.db.precious() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def get_salesman_access(self, user_id: int) -> set[str]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT salesman_key FROM user_salesman_access WHERE user_id = ?", (user_id,)
            ).fetchall()
        return {r["salesman_key"] for r in rows}

    def set_salesman_access(self, user_id: int, keys: list[str]) -> None:
        """Replace-all the user's per-salesman grants in one transaction.

        Keys are stored normalized (`salesman_key`) so `can_view_customer` can
        membership-test the customer SalesGroup against this set.
        """
        clean = sorted({salesman_key(k) for k in keys if k and str(k).strip()})
        clean = [k for k in clean if k]
        with self.db.precious() as conn:
            conn.execute("DELETE FROM user_salesman_access WHERE user_id = ?", (user_id,))
            conn.executemany(
                "INSERT OR IGNORE INTO user_salesman_access(user_id, salesman_key) VALUES (?, ?)",
                [(user_id, k) for k in clean],
            )

    def get_report_access(self, user_id: int) -> dict[str, bool]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT report_key, allowed FROM user_report_access WHERE user_id = ?", (user_id,)
            ).fetchall()
        return {r["report_key"]: bool(r["allowed"]) for r in rows}

    def set_report_access(self, user_id: int, report_key: str, allowed: bool) -> None:
        with self.db.precious() as conn:
            conn.execute(
                "INSERT INTO user_report_access(user_id, report_key, allowed) VALUES (?, ?, ?)"
                " ON CONFLICT(user_id, report_key) DO UPDATE SET allowed=excluded.allowed",
                (user_id, report_key, 1 if allowed else 0),
            )

    def clear_report_access(self, user_id: int, report_key: str) -> None:
        """Remove an explicit override so the report reverts to 'inherit' (the
        role default). Idempotent: a no-op when no override exists."""
        with self.db.precious() as conn:
            conn.execute(
                "DELETE FROM user_report_access WHERE user_id = ? AND report_key = ?",
                (user_id, report_key),
            )
