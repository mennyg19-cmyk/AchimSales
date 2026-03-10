"""
Shared utilities used across all blueprints.

Centralises auth helpers, the D365 connection factory, and the
salesmen-list builder so they aren't duplicated in every blueprint.
"""

import logging
from functools import wraps

from flask import redirect, session, url_for

log = logging.getLogger(__name__)


# -- Auth helpers ----------------------------------------------------------

def get_current_user() -> dict | None:
    """Return the current user dict from the session, or None."""
    return session.get("user")


def require_login(f):
    """Decorator: redirect to login page if the user is not authenticated."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


# -- Salesmen list ---------------------------------------------------------

def get_salesmen_list(user_email: str | None = None) -> list[dict]:
    """Return the salesman list with excluded ones filtered out."""
    try:
        from config.salesman_map import SALESMAN_MAP
        from webapp_v2.db import get_excluded_salesmen

        excluded = get_excluded_salesmen(user_email) if user_email else []
        salesmen = [
            {"key": k, "name": v[1], "display": v[2]}
            for k, v in SALESMAN_MAP.items()
            if v[0] != "?unassigned" and k not in excluded
        ]
        salesmen.sort(key=lambda x: x["name"])
        return salesmen
    except Exception:
        log.exception("Failed to load salesmen list")
        return []


# -- D365 connection ------------------------------------------------------

def get_d365_connection():
    """Return *(base_url, token, company_id)* for D365 OData calls."""
    from config.settings import (
        get_client_id, get_client_secret, get_company_id,
        get_d365_env_url, get_tenant_id, validate_d365_config,
    )
    from core.auth import get_d365_token

    validate_d365_config()
    env_url = get_d365_env_url().rstrip("/")
    base_url = (
        f"{env_url}/data/"
        if "/data" not in env_url.lower()
        else (env_url if env_url.endswith("/") else f"{env_url}/")
    )
    token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), env_url)
    company = get_company_id() or None
    return base_url, token, company


# -- Theme context processor -----------------------------------------------

def inject_theme() -> dict:
    """Make the current theme available in every template."""
    return {"theme": session.get("theme", "light")}
