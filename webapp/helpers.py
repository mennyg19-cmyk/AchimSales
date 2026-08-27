"""
Shared utilities used across all blueprints.

Centralises auth helpers, the D365 connection factory, and the
salesmen-list builder so they aren't duplicated in every blueprint.
"""

import logging
from functools import wraps

from flask import redirect, request, session, url_for

log = logging.getLogger(__name__)


# -- Auth helpers ----------------------------------------------------------

def refresh_session_user(user: dict | None) -> dict | None:
    """Re-resolve role from the user directory. Session is identity only.

    Returns None when the account is gone (caller must drop the session).
    Local DEV_BYPASS_AUTH fake users are not in app_users and stay as-is.
    The _dev impersonation flag is kept only while _dev_email is still a
    developer in the directory.
    """
    if not user or not user.get("email"):
        return None
    from webapp.config import dev_bypass_auth
    from webapp.db import get_user_by_email

    actor_email = str(user.get("_dev_email") or "").strip().lower()
    try:
        if user.get("_dev") and actor_email:
            actor = get_user_by_email(actor_email)
            if actor is None:
                if dev_bypass_auth():
                    return user
                return None
            if actor.get("role") != "developer":
                return None

        email = str(user.get("email") or "").strip().lower()
        row = get_user_by_email(email)
    except Exception:
        log.exception("session refresh: user lookup failed")
        return user
    if row is None:
        if dev_bypass_auth():
            return user
        return None
    out = dict(user)
    out["email"] = row["email"]
    out["role"] = row["role"]
    out["salesman_key"] = row.get("salesman_key")
    return out


def get_current_user() -> dict | None:
    """Return the current user dict from the session, or None.

    Role and salesman_key are taken from the directory on every call so a
    demotion or deletion takes effect before the cookie expires.
    """
    user = session.get("user")
    refreshed = refresh_session_user(user)
    if refreshed is None:
        if user:
            session.pop("user", None)
        return None
    if (
        refreshed.get("role") != user.get("role")
        or refreshed.get("salesman_key") != user.get("salesman_key")
    ):
        session["user"] = refreshed
    return refreshed


def require_login(f):
    """Decorator: redirect to login page if the user is not authenticated."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            dest = (request.script_root or "") + (
                request.full_path if request.full_path != "/?" else "/"
            )
            if dest.endswith("?"):
                dest = dest[:-1]
            return redirect(url_for("auth.login", next=dest))
        return f(*args, **kwargs)
    return wrapper


# -- Salesmen list ---------------------------------------------------------

def get_salesmen_list(user_email: str | None = None) -> list[dict]:
    """Return the salesman list from DB with inactive ones filtered out."""
    try:
        from webapp.db import get_all_salesmen_db

        all_sm = get_all_salesmen_db()
        salesmen = [
            {"key": s["key"], "name": s["full_name"], "display": s["display_name"]}
            for s in all_sm
            if s["active"] and s["number"] != "?unassigned"
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
    """Make the current theme and feature flags available in every template."""
    from webapp.db import get_feature_flag, get_db
    global_dash = get_feature_flag("dashboard_enabled", True)
    global_orders = get_feature_flag("order_entry_enabled", False)
    global_test = get_feature_flag("test_site_enabled", False)
    global_beta = get_feature_flag("beta_site_enabled", True)
    user_dash = True
    user_test = False
    user_beta = False
    try:
        user = get_current_user()
        if user:
            email = user.get("email", "").lower().strip()
            if email:
                conn = get_db()
                try:
                    row = conn.execute(
                        "SELECT dashboard_enabled, test_access_enabled, beta_access_enabled "
                        "FROM app_users WHERE email = ?",
                        (email,)
                    ).fetchone()
                    if row is not None:
                        user_dash = bool(row["dashboard_enabled"])
                        user_test = bool(row["test_access_enabled"]) if row["test_access_enabled"] is not None else False
                        try:
                            user_beta = bool(row["beta_access_enabled"])
                        except (IndexError, KeyError):
                            user_beta = False
                finally:
                    conn.close()
    except Exception:
        pass
    return {
        "theme": session.get("theme", "light"),
        "dashboard_enabled": global_dash and user_dash,
        "order_entry_enabled": global_orders,
        "test_site_enabled": global_test and user_test,
        "beta_site_enabled": global_beta and user_beta,
    }
