"""
Access-control service.

Centralises the OData-parameter validation and salesman-based access
checks that were previously duplicated across route handlers.
"""

import re

from webapp_v2.db import normalize_key, get_db

_SAFE_ODATA_RE = re.compile(r"^[A-Za-z0-9\-_]+$")


def validate_odata_param(value: str) -> str:
    """Raise *ValueError* if *value* contains characters unsafe for OData filters.

    Returns the original value unchanged when valid.
    """
    if not _SAFE_ODATA_RE.match(value):
        raise ValueError(f"Invalid OData parameter: {value!r}")
    return value


def check_customer_access(salesman_key: str | None, account: str, *, is_admin: bool = False) -> bool:
    """Return True if the user may view the given customer account.

    Admins always have access.  Salesmen only have access when the
    customer's sales_group matches their key.
    """
    if is_admin or not salesman_key:
        return True

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT sales_group FROM dashboard_cache WHERE customer_account = ?",
            (account,),
        ).fetchone()
        if not row:
            return True  # no cache entry — allow (D365 will be queried)
        return normalize_key(salesman_key) == normalize_key(row["sales_group"] or "")
    finally:
        conn.close()


def check_order_access(salesman_key: str | None, customer_account: str, *, is_admin: bool = False) -> bool:
    """Return True if the user may view an order belonging to *customer_account*."""
    return check_customer_access(salesman_key, customer_account, is_admin=is_admin)
