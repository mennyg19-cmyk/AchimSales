"""Outside-company email addresses that must be approved before send."""

from __future__ import annotations

from datetime import datetime, timezone

from web.data.connection import Database
from web.data.repositories.app_settings import AppSettingsRepository
from web.delivery.email import is_company_address

APPROVAL_NEEDED = "Those addresses need admin or developer approval."


class ExternalRecipientRepository:
    def __init__(self, db: Database):
        self.db = db

    def note_addresses(self, addresses: list[str],
                       requested_by_user_id: int | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.precious() as conn:
            for raw in addresses:
                email = raw.strip().lower()
                if not email or is_company_address(email):
                    continue
                conn.execute(
                    "INSERT INTO external_recipients"
                    "(email, status, requested_by_user_id, created_at)"
                    " VALUES (?, 'pending', ?, ?)"
                    " ON CONFLICT(email) DO NOTHING",
                    (email, requested_by_user_id, now),
                )

    def sendable(self, addresses: list[str]) -> list[str]:
        test = {e.lower() for e in AppSettingsRepository(self.db).test_emails()}
        approved = self._approved()
        out: list[str] = []
        for raw in addresses:
            email = raw.strip()
            if not email:
                continue
            low = email.lower()
            if is_company_address(low) or low in approved or low in test:
                out.append(email)
        return out

    def list_pending(self) -> list[dict]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT email, created_at, requested_by_user_id"
                " FROM external_recipients WHERE status='pending'"
                " ORDER BY created_at ASC",
            ).fetchall()
        return [dict(r) for r in rows]

    def decide(self, email: str, status: str, decided_by_user_id: int | None) -> bool:
        if status not in ("approved", "rejected"):
            raise ValueError(f"status must be approved or rejected, got {status!r}")
        email = (email or "").strip().lower()
        if not email:
            return False
        now = datetime.now(timezone.utc).isoformat()
        with self.db.precious() as conn:
            cur = conn.execute(
                "UPDATE external_recipients"
                " SET status=?, decided_by_user_id=?, decided_at=?"
                " WHERE email=?",
                (status, decided_by_user_id, now, email),
            )
            return cur.rowcount == 1

    def _approved(self) -> set[str]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT email FROM external_recipients WHERE status='approved'",
            ).fetchall()
        return {r["email"].lower() for r in rows}
