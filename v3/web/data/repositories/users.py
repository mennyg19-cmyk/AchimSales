"""User repository (precious.db `users` table)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

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

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "User":
        return cls(
            id=r["id"], email=r["email"], display_name=r["display_name"], role=r["role"],
            is_active=bool(r["is_active"]), is_external=bool(r["is_external"]),
            dashboard_enabled=bool(r["dashboard_enabled"]),
            sharepoint_access=bool(r["sharepoint_access"]), test_access=bool(r["test_access"]),
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
        with self.db.precious() as conn:
            conn.execute(
                "INSERT INTO users(email, display_name, role) VALUES (?, ?, ?)"
                " ON CONFLICT(email) DO UPDATE SET"
                "   display_name=excluded.display_name WHERE excluded.display_name <> ''",
                (email, display_name, role),
            )
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            return User.from_row(row)
