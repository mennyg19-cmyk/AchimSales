"""Notifications repository (precious.db `notifications`).

Per-user alerts (currently `overdue_customer`). Payload is JSON; for overdue
alerts it carries `customer_account` + `customer_name`. Dedup helpers mirror
LIVE: don't re-notify an account that already has an undismissed alert, and
honor a recently-dismissed cooldown window.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from web.data.connection import Database

OVERDUE = "overdue_customer"
REPORT_READY = "report_ready"
DELIVERY_UNKNOWN = "delivery_unknown"


@dataclass(frozen=True)
class Notification:
    id: int
    type: str
    payload: dict
    created_at: str


class NotificationRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, user_id: int, type_: str, payload: dict) -> int:
        with self.db.precious() as conn:
            cur = conn.execute(
                "INSERT INTO notifications(user_id, type, payload_json) VALUES (?, ?, ?)",
                (user_id, type_, json.dumps(payload or {})),
            )
            return cur.lastrowid

    def has_undismissed_account(self, user_id: int, type_: str, account: str) -> bool:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT 1 FROM notifications WHERE user_id=? AND type=? AND dismissed=0"
                " AND json_extract(payload_json, '$.customer_account')=? LIMIT 1",
                (user_id, type_, account),
            ).fetchone()
        return row is not None

    def recently_dismissed_accounts(self, user_id: int, type_: str, days: int = 7) -> set[str]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT json_extract(payload_json, '$.customer_account') AS acct"
                " FROM notifications WHERE user_id=? AND type=? AND dismissed=1"
                f" AND read_at >= datetime('now', '-{int(days)} days')",
                (user_id, type_),
            ).fetchall()
        return {r["acct"] for r in rows if r["acct"]}

    def list_undismissed(self, user_id: int, type_: str | None = None) -> list[Notification]:
        q = ("SELECT id, type, payload_json, created_at FROM notifications"
             " WHERE user_id=? AND dismissed=0")
        args: list = [user_id]
        if type_:
            q += " AND type=?"
            args.append(type_)
        q += " ORDER BY id DESC"
        with self.db.precious() as conn:
            rows = conn.execute(q, args).fetchall()
        return [Notification(r["id"], r["type"], json.loads(r["payload_json"] or "{}"),
                             r["created_at"]) for r in rows]

    def counts(self, user_id: int) -> dict[str, int]:
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT type, COUNT(*) AS n FROM notifications"
                " WHERE user_id=? AND dismissed=0 GROUP BY type", (user_id,),
            ).fetchall()
        return {r["type"]: r["n"] for r in rows}

    def dismiss(self, user_id: int, *, notif_id: int | None = None,
                type_: str | None = None, all_: bool = False) -> int:
        q = "UPDATE notifications SET dismissed=1, read_at=datetime('now') WHERE user_id=? AND dismissed=0"
        args: list = [user_id]
        if all_:
            pass
        elif notif_id is not None:
            q += " AND id=?"
            args.append(notif_id)
        elif type_:
            q += " AND type=?"
            args.append(type_)
        else:
            return 0
        with self.db.precious() as conn:
            cur = conn.execute(q, args)
            return cur.rowcount
