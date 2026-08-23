"""Reading and writing which salesman(s) a person is allowed to see."""

# === What's in this file ===
# The admin-managed map of "this login -> these salesman number(s)". The authz
# module reads it to decide what slice of a report a non-privileged person gets.
# Emails are kept lower-cased so a login always matches its mapping.
#
# UserScopeRepository.salesmen_for() -- the salesman numbers assigned to one email
# UserScopeRepository.emails_for_salesman() -- the logins mapped to one salesman number
# UserScopeRepository.set_salesmen() -- replace a person's whole assignment
# UserScopeRepository.all_assignments() -- {email: [numbers]} for the admin screen

from __future__ import annotations

from ..connection import Database, normalize_email, utc_now_iso


def _norm_number(number: str) -> str:
    return (number or "").strip()


class UserScopeRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def salesmen_for(self, email: str) -> list[str]:
        with self._db.precious() as conn:
            rows = conn.fetchall(
                "SELECT salesman_number FROM user_salesmen WHERE user_email = ? "
                "ORDER BY salesman_number",
                (normalize_email(email),),
            )
            return [row["salesman_number"] for row in rows]

    def emails_for_salesman(self, number: str) -> list[str]:
        with self._db.precious() as conn:
            rows = conn.fetchall(
                "SELECT user_email FROM user_salesmen WHERE salesman_number = ? "
                "ORDER BY user_email",
                (_norm_number(number),),
            )
            return [row["user_email"] for row in rows]

    def set_salesmen(self, email: str, numbers: list[str]) -> None:
        email = normalize_email(email)
        cleaned = sorted({n for n in (_norm_number(raw) for raw in numbers) if n})
        now = utc_now_iso()
        with self._db.precious() as conn:
            with conn.transaction():
                conn.execute("DELETE FROM user_salesmen WHERE user_email = ?", (email,))
                for number in cleaned:
                    conn.execute(
                        "INSERT INTO user_salesmen (user_email, salesman_number, created_at) "
                        "VALUES (?, ?, ?)",
                        (email, number, now),
                    )

    def all_assignments(self) -> dict[str, list[str]]:
        with self._db.precious() as conn:
            rows = conn.fetchall(
                "SELECT user_email, salesman_number FROM user_salesmen "
                "ORDER BY user_email, salesman_number"
            )
        assignments_by_email: dict[str, list[str]] = {}
        for row in rows:
            assignments_by_email.setdefault(row["user_email"], []).append(row["salesman_number"])
        return assignments_by_email
