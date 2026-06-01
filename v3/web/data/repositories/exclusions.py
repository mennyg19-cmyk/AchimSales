"""Per-user customer exclusions (precious.db `user_exclusions`).

A user can hide customers from their own dashboard tiles/table and overdue
notifications. Owner-scoped: every method is keyed by user_id so one user can
never read or change another's exclusions.
"""

from __future__ import annotations

from web.data.connection import Database


class ExclusionRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, user_id: int) -> set[str]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT customer_account FROM user_exclusions WHERE user_id = ?", (user_id,)
            ).fetchall()
        return {r["customer_account"] for r in rows}

    def is_excluded(self, user_id: int, customer_account: str) -> bool:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT 1 FROM user_exclusions WHERE user_id = ? AND customer_account = ?",
                (user_id, customer_account),
            ).fetchone()
        return row is not None

    def set(self, user_id: int, customer_account: str, excluded: bool) -> None:
        with self.db.precious() as conn:
            if excluded:
                conn.execute(
                    "INSERT OR IGNORE INTO user_exclusions(user_id, customer_account)"
                    " VALUES (?, ?)", (user_id, customer_account))
            else:
                conn.execute(
                    "DELETE FROM user_exclusions WHERE user_id = ? AND customer_account = ?",
                    (user_id, customer_account))

    def replace_all(self, user_id: int, accounts: list[str]) -> None:
        clean = sorted({a.strip() for a in accounts if a and a.strip()})
        with self.db.precious() as conn:
            conn.execute("DELETE FROM user_exclusions WHERE user_id = ?", (user_id,))
            conn.executemany(
                "INSERT OR IGNORE INTO user_exclusions(user_id, customer_account) VALUES (?, ?)",
                [(user_id, a) for a in clean])
