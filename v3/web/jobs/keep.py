"""Shared rules for a report run's Keep expiry."""

from __future__ import annotations

from datetime import datetime, timezone


def _kept_still_valid(kept_until: str | None, now: datetime) -> bool:
    if not kept_until:
        return False
    try:
        expires_at = datetime.fromisoformat(kept_until)
    except ValueError:
        return False
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    return expires_at > now
