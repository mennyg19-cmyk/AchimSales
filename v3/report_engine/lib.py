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
from typing import Any, Mapping

# Sentinels the Reporting API / stored procedures hand back for "no value".
_BLANKS = (None, "", "NULL")


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
    """Coerce to str, treating None / 'NULL' as empty string."""
    if value is None or value == "NULL":
        return ""
    return str(value)


def first_of(raw: Mapping[str, Any], *keys: str) -> Any:
    """First non-blank value across endpoint field-name variants."""
    for key in keys:
        value = raw.get(key)
        if value not in _BLANKS:
            return value
    return None


def date_only(value: Any) -> str:
    """Trim 'YYYY-MM-DDTHH:MM:SS' (or ' ' separator) to 'YYYY-MM-DD'."""
    s = text(value)
    return s[:10] if len(s) >= 10 else s


def salesman_key(sales_group: str | None) -> str:
    """Normalize a SalesGroup to the salesmen.key form (lowercase alphanumeric)."""
    return re.sub(r"[^a-z0-9]+", "", (sales_group or "").strip().lower())
