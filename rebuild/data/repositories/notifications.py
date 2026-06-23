"""Reading and writing a person's in-app messages (their little inbox)."""

# === What's in this file ===
# The only code that touches the notifications table. Today it holds one kind of
# message: "a private schedule of yours failed to run." The base page shows a
# person their unread messages; a message can offer a "run it now" button and is
# dismissed once they act on it (or click dismiss).
#
# NotificationsRepository.create() -- add one message for a person
# NotificationsRepository.list_unread() -- a person's unread messages (newest first)
# NotificationsRepository.get() -- one message by id
# NotificationsRepository.dismiss() -- hide one message
# NotificationsRepository.dismiss_for_schedule() -- hide a person's messages about one schedule

from __future__ import annotations

import uuid
from typing import Optional

from ..connection import Database, utc_now_iso

KIND_SCHEDULE_FAILED = "schedule_failed"

_STATUS_UNREAD = "unread"
_STATUS_DISMISSED = "dismissed"


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


class NotificationsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self,
        *,
        user_email: str,
        kind: str,
        title: str,
        body: str = "",
        schedule_id: Optional[str] = None,
    ) -> str:
        note_id = uuid.uuid4().hex
        with self._db.precious() as conn:
            conn.execute(
                "INSERT INTO notifications (id, user_email, kind, title, body, schedule_id, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (note_id, _norm_email(user_email), kind, title, body, schedule_id, _STATUS_UNREAD, utc_now_iso()),
            )
        return note_id

    def list_unread(self, user_email: str) -> list[dict]:
        with self._db.precious() as conn:
            rows = conn.fetchall(
                "SELECT * FROM notifications WHERE user_email = ? AND status = ? ORDER BY created_at DESC",
                (_norm_email(user_email), _STATUS_UNREAD),
            )
            return [dict(r) for r in rows]

    def get(self, note_id: str) -> Optional[dict]:
        with self._db.precious() as conn:
            row = conn.fetchone("SELECT * FROM notifications WHERE id = ?", (note_id,))
            return dict(row) if row else None

    def dismiss(self, note_id: str) -> None:
        with self._db.precious() as conn:
            conn.execute(
                "UPDATE notifications SET status = ? WHERE id = ?", (_STATUS_DISMISSED, note_id)
            )

    def dismiss_for_schedule(self, user_email: str, schedule_id: str) -> None:
        with self._db.precious() as conn:
            conn.execute(
                "UPDATE notifications SET status = ? WHERE user_email = ? AND schedule_id = ? AND status = ?",
                (_STATUS_DISMISSED, _norm_email(user_email), schedule_id, _STATUS_UNREAD),
            )
