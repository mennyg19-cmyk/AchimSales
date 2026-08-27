"""
Access-control service.

Centralises the OData-parameter validation and salesman-based access
checks that were previously duplicated across route handlers.
"""

import re

from webapp.db import get_db, get_user_salesman_access, normalize_key
from webapp.user_map import get_salesman_key, is_admin, is_manager

_SAFE_ODATA_RE = re.compile(r"^[A-Za-z0-9\-_]+$")


def validate_odata_param(value: str) -> str:
    """Raise *ValueError* if *value* contains characters unsafe for OData filters.

    Returns the original value unchanged when valid.
    """
    if not _SAFE_ODATA_RE.match(value):
        raise ValueError(f"Invalid OData parameter: {value!r}")
    return value


def _cached_sales_group(account: str) -> str | None:
    """Normalized sales_group from dashboard_cache, or None if unknown."""
    if not account:
        return None
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT sales_group FROM dashboard_cache WHERE customer_account = ?",
            (account,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    group = normalize_key(row["sales_group"] or "")
    return group or None


def check_customer_access(salesman_key: str | None, account: str, *, is_admin: bool = False) -> bool:
    """Return True if this salesman (or admin) may view the customer.

    Missing cache data is a deny. A missing salesman_key is not admin
    access — managers must use user_can_access_customer.
    """
    if is_admin:
        return True
    if not salesman_key:
        return False
    group = _cached_sales_group(account)
    if group is None:
        return False
    return normalize_key(salesman_key) == group


def check_order_access(salesman_key: str | None, customer_account: str, *, is_admin: bool = False) -> bool:
    """Return True if the user may view an order belonging to *customer_account*."""
    return check_customer_access(salesman_key, customer_account, is_admin=is_admin)


def user_can_access_customer(user: dict | None, account: str, *, sales_group: str | None = None) -> bool:
    """Role-aware customer scope. Unknown book/account is a deny."""
    if not user or not account:
        return False
    if is_admin(user):
        return True
    group = normalize_key(sales_group) if sales_group else ""
    if not group:
        group = _cached_sales_group(account)
    if not group:
        return False
    if is_manager(user):
        allowed = {normalize_key(k) for k in get_user_salesman_access(user.get("email") or "")}
        return group in allowed
    key = get_salesman_key(user)
    return bool(key) and normalize_key(key) == group


def visible_salesman_keys(user: dict | None, requested: str | None = None) -> set[str] | None:
    """Salesman books this user may list.

    None means unrestricted (admin, no filter). An empty set means none.
    """
    if not user:
        return set()
    req = (requested or "").strip() or None
    if is_admin(user):
        return {req} if req else None
    if is_manager(user):
        allowed = {
            normalize_key(k)
            for k in get_user_salesman_access(user.get("email") or "")
            if k
        }
        if req:
            return {req} if normalize_key(req) in allowed else set()
        return allowed
    key = get_salesman_key(user)
    if not key:
        return set()
    if req and normalize_key(req) != normalize_key(key):
        return set()
    return {key}
