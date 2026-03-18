"""
Maps Microsoft account emails to salesman keys and roles.

Looks up users in the SQLite database to determine:
  - Whether a user is authorized at all
  - Whether they are a salesman (and which one), an admin, or a developer
"""

import logging

log = logging.getLogger(__name__)


def get_user(email: str) -> dict | None:
    """Look up a user by email. Returns their role info dict or None if not authorized."""
    from webapp.db import get_user_by_email
    row = get_user_by_email(email)
    if not row:
        return None
    return {
        "role": row["role"],
        "salesman_key": row.get("salesman_key"),
        "display_name": row.get("display_name"),
    }


def is_admin(user_info: dict) -> bool:
    role = user_info.get("role")
    return role == "admin" or role == "developer"


def is_salesman(user_info: dict) -> bool:
    return user_info.get("role") == "salesman"


def is_developer(user_info: dict) -> bool:
    return user_info.get("role") == "developer"


def get_salesman_key(user_info: dict) -> str | None:
    """Return the salesman_key for a salesman user, or None for admins/devs."""
    if is_salesman(user_info):
        return user_info.get("salesman_key")
    return None


REPORTS_CONFIG = {
    "ordered": {
        "name": "Ordered Report",
        "description": "Sales orders: ordered, shipped, cancelled, remaining",
        "salesman_filter": True,
        "customer_filter": True,
        "has_period": True,
        "has_status": True,
        "icon": "package",
    },
    "invoiced": {
        "name": "Invoiced Report",
        "name_salesman": "Shipped Report",
        "description": "Invoices with commissions and freight details",
        "description_salesman": "Your shipped orders with commissions and freight details",
        "salesman_filter": True,
        "customer_filter": True,
        "has_period": True,
        "has_status": False,
        "icon": "file-text",
    },
    "salesman": {
        "name": "Salesman Report",
        "description": "Monthly salesman comparison: current vs prior year",
        "salesman_filter": False,
        "customer_filter": False,
        "has_period": False,
        "has_status": False,
        "has_year": True,
        "icon": "users",
    },
    "number_4": {
        "name": "Number 4 Report",
        "description": "Invoice lines by item and by customer (rolling 12 months)",
        "salesman_filter": False,
        "customer_filter": False,
        "has_period": False,
        "has_status": False,
        "icon": "bar-chart-2",
    },
    "amazon_weekly": {
        "name": "Amazon Weekly",
        "description": "Amazon (customers 9300, 9301) orders for the last 7 days",
        "salesman_filter": False,
        "customer_filter": False,
        "has_period": False,
        "has_status": False,
        "icon": "shopping-cart",
    },
    "customer_activity": {
        "name": "Customer Activity",
        "description": "All customers with last order info, split by salesman",
        "salesman_filter": True,
        "customer_filter": False,
        "has_period": False,
        "has_status": False,
        "icon": "activity",
    },
}


def get_available_reports(user_info: dict) -> dict:
    """Return the reports available to this user based on their role,
    global report visibility, and per-user overrides.
    """
    from webapp.db import get_report_config_all, get_user_report_overrides

    global_cfg = get_report_config_all()
    email = user_info.get("email", "")
    overrides = get_user_report_overrides(email) if email else {}
    admin = is_admin(user_info)

    result = {}
    for key, cfg in REPORTS_CONFIG.items():
        globally_enabled = global_cfg.get(key, True)

        if not admin and not cfg.get("salesman_filter", False):
            continue

        if key in overrides:
            if not overrides[key]:
                continue
        elif not globally_enabled:
            continue

        entry = cfg.copy()
        if not admin:
            if "name_salesman" in entry:
                entry["name"] = entry["name_salesman"]
            if "description_salesman" in entry:
                entry["description"] = entry["description_salesman"]
        result[key] = entry
    return result
