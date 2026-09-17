"""Coerce report cells to YYYY-MM-DD or Eastern YYYY-MM-DD HH:MM:SS."""

from __future__ import annotations

import re
from datetime import date as _date, datetime as _datetime, timezone as _timezone
from typing import Any

from period import EASTERN

_BLANKS = (None, "", "NULL")
_RFC1123_FMTS = ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S")
_NORMALIZED = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$")


def date_only(value: Any) -> str:
    """Deprecated name — use iso_date."""
    return iso_date(value)


def iso_date(value: Any) -> str:
    """Coerce any date-ish value to day-precision 'YYYY-MM-DD'.

    Handles ISO, RFC-1123 ('Tue, 15 Sep 2026 16:21:16 GMT'), slash/dash forms,
    and date/datetime objects. Returns '' for blanks; keeps N/A-style
    placeholders; returns the raw string when nothing parses.

    Calendar date only — midnight UTC must not shift to the previous Eastern day.
    """
    if value in _BLANKS:
        return ""
    if isinstance(value, _datetime):
        return value.date().isoformat()
    if isinstance(value, _date):
        return value.isoformat()
    s = str(value).strip()
    if not s:
        return ""
    if s.upper() in ("N/A", "NA", "NONE", "-"):
        return s
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return _datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            try:
                return _datetime.strptime(s[:10], "%Y-%m-%d").date().isoformat()
            except ValueError:
                pass
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(s)
        if parsed is not None:
            return parsed.date().isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    for fmt in _RFC1123_FMTS:
        try:
            return _datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    head = s.replace("T", " ").split(" ")[0]
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return _datetime.strptime(head, fmt).date().isoformat()
        except ValueError:
            continue
    return s


def eastern_datetime(value: Any) -> str:
    """Timestamp cell: Eastern wall clock, with time when the source had one.

    Date-only values stay YYYY-MM-DD (same as iso_date, no TZ shift). RFC-1123
    and ISO datetimes convert to America/New_York as 'YYYY-MM-DD HH:MM:SS'.
    Naive datetimes are treated as UTC. Already-normalized YYYY-MM-DD or
    YYYY-MM-DD HH:MM:SS strings are left as-is.
    """
    if value in _BLANKS:
        return ""
    if isinstance(value, _datetime):
        return _eastern_clock(value)
    if isinstance(value, _date):
        return value.isoformat()
    s = str(value).strip()
    if not s:
        return ""
    if s.upper() in ("N/A", "NA", "NONE", "-"):
        return s
    if _NORMALIZED.match(s):
        return s
    parsed, has_clock = _parse_clock(s)
    if parsed is None:
        return iso_date(value)
    if not has_clock:
        return parsed.date().isoformat()
    return _eastern_clock(parsed)


def _eastern_clock(dt: _datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_timezone.utc)
    return dt.astimezone(EASTERN).strftime("%Y-%m-%d %H:%M:%S")


def _parse_clock(s: str):
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        has_clock = len(s) > 10 and (s[10] in "T " or ":" in s[10:])
        try:
            parsed = _datetime.fromisoformat(s.replace("Z", "+00:00"))
            return parsed, has_clock
        except ValueError:
            try:
                parsed = _datetime.strptime(s[:10], "%Y-%m-%d")
                return parsed, False
            except ValueError:
                pass
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(s)
        if parsed is not None:
            return parsed, True
    except (TypeError, ValueError, IndexError):
        pass
    for fmt in _RFC1123_FMTS:
        try:
            return _datetime.strptime(s, fmt), True
        except ValueError:
            continue
    head = s.replace("T", " ").split(" ")[0]
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return _datetime.strptime(head, fmt), False
        except ValueError:
            continue
    return None, False
