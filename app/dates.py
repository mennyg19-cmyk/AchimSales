"""Coerce report cells to day-precision YYYY-MM-DD. Same behaviour as Flask iso_date."""

from __future__ import annotations

from datetime import date as _date, datetime as _datetime
from typing import Any

_BLANKS = (None, "", "NULL")
_RFC1123_FMTS = ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S")


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
