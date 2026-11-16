"""Eastern display helpers for warehouse dashboard timestamps.

Record fields like createdDateTime / modifiedDateTime are already Eastern wall
clocks (even when a source labels them GMT). Refresh stamps UpdatedUtc,
LastSeenUtc, and LastImportedUTC are true GMT/UTC and must convert to ET for
the "Data as of" line. Production shape example:
'Thu, 05 Nov 2026 09:34:36 GMT' (RFC 822).
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

_REFRESH_STAMP_KEYS = frozenset({
    "UpdatedUtc", "LastSeenUtc", "LastImportedUTC",
})


def parse_utc_timestamp(value) -> datetime | None:
    """Parse a true-UTC/GMT stamp into an aware datetime. Returns None if unusable."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    # Production Reporting API often returns RFC 822: 'Thu, 05 Nov 2026 09:34:36 GMT'
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass

    cleaned = text
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    if " " in cleaned and "T" not in cleaned[:19] and "," not in cleaned:
        cleaned = cleaned.replace(" ", "T", 1)

    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(cleaned[:26], fmt)
                break
            except ValueError:
                dt = None
        if dt is None:
            return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_to_eastern_display(value, *, seconds: bool = False) -> str | None:
    """Format a true-UTC stamp as America/New_York wall time, labeled ET."""
    dt = parse_utc_timestamp(value)
    if dt is None:
        return None
    local = dt.astimezone(ET)
    if seconds:
        return local.strftime("%Y-%m-%d %H:%M:%S") + " ET"
    return local.strftime("%Y-%m-%d %H:%M") + " ET"


def latest_refresh_utc(
    rows: list[dict], keys: Iterable[str] | None = None,
) -> datetime | None:
    """Newest true-UTC refresh stamp across rows."""
    stamp_keys = tuple(keys) if keys is not None else tuple(_REFRESH_STAMP_KEYS)
    latest: datetime | None = None
    for row in rows:
        for key in stamp_keys:
            if key not in row:
                continue
            dt = parse_utc_timestamp(row.get(key))
            if dt is None:
                continue
            if latest is None or dt > latest:
                latest = dt
    return latest
