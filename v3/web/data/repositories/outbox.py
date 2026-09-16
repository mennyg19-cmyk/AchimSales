"""Outbox repository (precious.db `outbox` table).

Every email / SharePoint delivery is logged here as an auditable record of what
was sent, to whom, and whether it succeeded. The email service writes a row per
delivery attempt; the diagnostics/admin UI reads it back.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from web.data.connection import Database


@dataclass(frozen=True)
class OutboxMessage:
    id: int
    subject: str
    recipients: str
    attachment_meta: dict
    sharepoint_meta: dict
    status: str
    created_at: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "OutboxMessage":
        return cls(
            id=r["id"], subject=r["subject"], recipients=r["recipients"],
            attachment_meta=json.loads(r["attachment_meta"] or "{}"),
            sharepoint_meta=json.loads(r["sharepoint_meta"] or "{}"),
            status=r["status"], created_at=r["created_at"],
        )


class OutboxRepository:
    def __init__(self, db: Database):
        self.db = db

    def enqueue(self, *, subject: str, recipients: str,
                attachment_meta: dict | None = None,
                sharepoint_meta: dict | None = None, status: str = "queued") -> int:
        with self.db.precious() as conn:
            cur = conn.execute(
                "INSERT INTO outbox(subject, recipients, attachment_meta, sharepoint_meta, status)"
                " VALUES (?, ?, ?, ?, ?)",
                (subject, recipients, json.dumps(attachment_meta or {}),
                 json.dumps(sharepoint_meta or {}), status),
            )
            return cur.lastrowid

    def mark(self, message_id: int, status: str) -> None:
        with self.db.precious() as conn:
            conn.execute("UPDATE outbox SET status=? WHERE id=?", (status, message_id))

    def get(self, message_id: int) -> OutboxMessage | None:
        with self.db.precious() as conn:
            row = conn.execute("SELECT * FROM outbox WHERE id=?", (message_id,)).fetchone()
            return OutboxMessage.from_row(row) if row else None

    def list_recent(self, limit: int = 100) -> list[OutboxMessage]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT * FROM outbox ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [OutboxMessage.from_row(r) for r in rows]
