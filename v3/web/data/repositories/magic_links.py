"""One-time sign-in tokens in precious.db."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from web.data.connection import Database

_WINDOW_MIN = 15
_MAX_PER_EMAIL = 5
_MAX_PER_IP = 40


class MagicLinkRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_token(self, email: str, ttl_minutes: int = 15,
                     request_ip: str | None = None) -> str | None:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(minutes=_WINDOW_MIN)).isoformat()
        expires = now + timedelta(minutes=ttl_minutes)
        email_norm = email.lower().strip()
        ip = (request_ip or "").strip()
        now_s = now.isoformat()

        with self.db.precious() as conn:
            n_email = conn.execute(
                "SELECT COUNT(*) FROM magic_link_tokens WHERE email = ? AND created_at >= ?",
                (email_norm, cutoff),
            ).fetchone()[0]
            if n_email >= _MAX_PER_EMAIL:
                return None
            conn.execute(
                "UPDATE magic_link_tokens SET consumed_at = ? "
                "WHERE email = ? AND consumed_at IS NULL",
                (now_s, email_norm),
            )
            conn.execute(
                """INSERT INTO magic_link_tokens
                   (token, email, created_at, expires_at, request_ip)
                   VALUES (?, ?, ?, ?, ?)""",
                (token, email_norm, now_s, expires.isoformat(), ip or None),
            )
        return token

    def consume_token(self, token: str) -> str | None:
        if not token or len(token) < 16:
            return None
        now = datetime.now(timezone.utc).isoformat()
        with self.db.precious() as conn:
            cur = conn.execute(
                """UPDATE magic_link_tokens
                   SET consumed_at = ?
                   WHERE token = ? AND consumed_at IS NULL AND expires_at >= ?""",
                (now, token, now),
            )
            if cur.rowcount != 1:
                return None
            row = conn.execute(
                "SELECT email FROM magic_link_tokens WHERE token = ?",
                (token,),
            ).fetchone()
            return row["email"] if row else None

    def record_attempt(self, email: str, request_ip: str) -> None:
        with self.db.precious() as conn:
            conn.execute(
                "INSERT INTO magic_link_attempts (email, ip, created_at) VALUES (?, ?, ?)",
                (email.lower().strip(), (request_ip or "").strip(),
                 datetime.now(timezone.utc).isoformat()),
            )

    def ip_rate_limited(self, request_ip: str) -> bool:
        ip = (request_ip or "").strip()
        if not ip:
            return False
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=_WINDOW_MIN)).isoformat()
        with self.db.precious() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM magic_link_attempts WHERE ip = ? AND created_at >= ?",
                (ip, cutoff),
            ).fetchone()[0]
        return n >= _MAX_PER_IP
