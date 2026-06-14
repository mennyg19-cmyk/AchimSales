"""De-duplicated coercion helpers.

These were copy-pasted across the five report modules in the `test/` sandbox
(`_num`, `_str`, `_first`, `_sm_key`, `_date_only`). Consolidated here as the
single source of truth (rule: no duplication). Behaviour matches the audited
originals for `num`/`as_int`/`first_of`/`salesman_key`/`date_only`.

PARITY NOTE: the originals' `_str` was inconsistent - four modules return
`str(v)` while `customer_activity._str` returns `str(v).strip()`. `text()` here
takes the non-stripping majority behaviour; the customer_activity builder must
apply `.strip()` explicitly where its original did. Tracked as a parity item in
REVIEW-LOG so it can't drift silently. (Salesman-map normalization is NOT here -
the two originals differ from each other and read from the DB; it will be built
with the salesman/invoiced adapters under a dedicated parity test.)
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Mapping

# Sentinels the Reporting API / stored procedures hand back for "no value".
_BLANKS = (None, "", "NULL")


def map_release(rows: Iterable[Any], convert: Callable[[Any], Any]) -> list:
    """Convert each item with `convert`, freeing each source item as we go.

    A full-year report can be ~500k rows. Holding the raw SP-row list AND the
    converted-fact list in memory at the same time doubles peak usage and pushes
    the small Azure worker over its limit (the out-of-memory crash). Nulling each
    source slot right after converting it keeps memory near a single copy. Order
    is preserved. The input list is consumed (left full of None); callers always
    pass a fresh per-request list, so that's safe. Non-list inputs (e.g. a
    generator in a test) fall back to a plain conversion.
    """
    if not isinstance(rows, list):
        return [convert(r) for r in rows]
    out = []
    for i, r in enumerate(rows):
        out.append(convert(r))
        rows[i] = None
    return out


def num(value: Any) -> float:
    """Coerce to float, treating None / blank / 'NULL' / junk as 0.0."""
    if value is None or value == "" or value == "NULL":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def as_int(value: Any) -> int:
    """Round-then-int, sharing num()'s blank handling."""
    return int(round(num(value)))


def text(value: Any) -> str:
    """Coerce to a stripped str, treating None / 'NULL' as empty string.

    Stripping mirrors LIVE (.str.strip() on every SP string field) so account /
    item / sales-group join + scope keys match across SPs.
    """
    if value is None or value == "NULL":
        return ""
    return str(value).strip()


def first_of(raw: Mapping[str, Any], *keys: str) -> Any:
    """First non-blank value across endpoint field-name variants."""
    for key in keys:
        value = raw.get(key)
        if value not in _BLANKS:
            return value
    return None


def date_only(value: Any) -> str:
    """Trim 'YYYY-MM-DDTHH:MM:SS' (or ' ' separator) to 'YYYY-MM-DD'.

    Only safe for values already in ISO order. For SP fields that can also be
    RFC-1123 ('Thu, 30 Apr 2026 ...'), use iso_date() instead.
    """
    s = text(value)
    return s[:10] if len(s) >= 10 else s


# Date shapes the Reporting API has been observed to return for invoice dates.
_RFC1123_FMTS = ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S")


def iso_date(value: Any) -> str:
    """Robustly coerce an SP date to day-precision 'YYYY-MM-DD'.

    Handles ISO ('2026-04-30T..' / '2026-04-30 ..' / '2026-04-30'), RFC-1123
    ('Thu, 30 Apr 2026 00:00:00 GMT'), and date/datetime objects. Returns ''
    for blanks; returns the raw string unchanged when nothing parses (so a bad
    value is visible rather than silently dropped).

    Carries only the calendar date (no time/tz): an SP 'midnight UTC' value
    must not shift to the previous day when rendered in Eastern time.
    """
    from datetime import date as _date, datetime as _datetime

    if value in _BLANKS:
        return ""
    if isinstance(value, _datetime):
        return value.date().isoformat()
    if isinstance(value, _date):
        return value.isoformat()
    s = str(value).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return _datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            try:
                return _datetime.strptime(s[:10], "%Y-%m-%d").date().isoformat()
            except ValueError:
                pass
    for fmt in _RFC1123_FMTS:
        try:
            return _datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s


def salesman_key(sales_group: str | None) -> str:
    """Normalize a SalesGroup to the salesmen.key form (lowercase alphanumeric)."""
    return re.sub(r"[^a-z0-9]+", "", (sales_group or "").strip().lower())


def filter_facts_by_scope(facts, visible_keys):
    """Filter facts to those whose sales_group is in the caller's scope.

    visible_keys=None means unrestricted (privileged user) — returns all facts.
    An empty set means the user has no access — returns nothing.
    """
    if visible_keys is None:
        return list(facts)
    normalized = {salesman_key(k) for k in visible_keys}
    return [f for f in facts if salesman_key(getattr(f, "sales_group", "")) in normalized]
