"""Small value-cleaning helpers shared across the report engine."""

# === What's in this file ===
# Stored procedures hand back messy values (strings where we want numbers, half
# a dozen date shapes, blank cells). These helpers turn one raw cell into the
# clean type the rest of the engine expects, in one place so every report cleans
# values the same way.
#
# num() -- any cell -> float (blank/garbage -> 0.0)
# money() -- num() rounded to cents
# text() -- any cell -> trimmed string
# iso_date() -- any date-ish cell -> 'YYYY-MM-DD' (or '')
# parse_bool() -- truthy/falsy cell -> bool
# first_present() -- first alias key that actually has a value in a row
# is_credit_number() -- LIVE fallback: CRD/CM/FC anywhere in the invoice number

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Mapping, Optional, Sequence

_CREDIT_RE = re.compile(r"CRD|CM|FC", re.IGNORECASE)
_TRUE = {"1", "true", "yes", "y", "t"}


def num(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def money(value: Any) -> float:
    return round(num(value), 2)


def text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def iso_date(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip()
    if not s:
        return ""
    # Already ISO ('YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS'): keep the date part.
    head = s.replace("T", " ").split(" ")[0]
    if len(head) >= 10 and head[4] == "-" and head[7] == "-":
        return head[:10]
    # RFC 1123 / 2822, e.g. 'Fri, 15 Jan 2026 00:00:00 GMT' (what the SP sends).
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(s)
        if parsed is not None:
            return parsed.date().isoformat()
    except (TypeError, ValueError):
        pass
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(head, fmt).date().isoformat()
        except ValueError:
            continue
    return head


def parse_bool(value: Any) -> Optional[bool]:
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip().lower() in _TRUE


def first_present(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    for key in aliases:
        if key in row and row[key] not in (None, ""):
            return row[key]
    # Fall back to the first alias that exists at all (even if blank).
    for key in aliases:
        if key in row:
            return row[key]
    return None


def is_credit_number(invoice_number: str) -> bool:
    return bool(invoice_number and _CREDIT_RE.search(invoice_number))
