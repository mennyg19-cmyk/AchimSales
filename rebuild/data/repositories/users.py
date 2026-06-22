"""Reading and writing the users table."""

# === What's in this file ===
# The app's record of who has signed in. record_login() upserts a person each
# time they log in (first_seen stays, last_seen and role refresh). It's the
# directory mirror the admin screens read later.
#
# UsersRepository.record_login() -- upsert a user on sign-in
# UsersRepository.get() -- fetch one user by email

from __future__ import annotations

from typing import Optional

from ...auth.principal import Principal
from ..connection import Database, utc_now_iso


class UsersRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def record_login(self, principal: Principal) -> None:
        now = utc_now_iso()
        with self._db.precious() as conn:
            conn.execute(
                "INSERT INTO users (email, name, role, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(email) DO UPDATE SET "
                "  name=excluded.name, role=excluded.role, last_seen=excluded.last_seen",
                (principal.email, principal.name, principal.role, now, now),
            )

    def get(self, email: str) -> Optional[dict]:
        with self._db.precious() as conn:
            row = conn.fetchone(
                "SELECT email, name, role, first_seen, last_seen FROM users WHERE email = ?",
                (email.strip().lower(),),
            )
            return dict(row) if row else None
