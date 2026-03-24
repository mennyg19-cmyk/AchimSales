"""
Microsoft Entra ID (Azure AD) login flow using MSAL for Python.

Uses the authorization code flow (interactive user login), NOT client credentials.
Reuses the same app registration as the scripts (GRAPH_CLIENT_ID etc).
"""

import msal
from flask import request, session

from webapp.config import AUTHORITY, CLIENT_ID, CLIENT_SECRET, REDIRECT_PATH, SCOPES


def _build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
        token_cache=cache,
    )


def _get_redirect_uri():
    """Build the redirect URI, forcing https when behind a reverse proxy."""
    root = request.url_root.rstrip("/")
    if request.headers.get("X-Forwarded-Proto") == "https" and root.startswith("http://"):
        root = "https://" + root[7:]
    return root + REDIRECT_PATH


def build_login_url():
    """Build the Microsoft login URL and store the flow state in the session."""
    app = _build_msal_app()
    flow = app.initiate_auth_code_flow(
        scopes=SCOPES,
        redirect_uri=_get_redirect_uri(),
    )
    session["auth_flow"] = flow
    return flow["auth_uri"]


def complete_login():
    """Complete the login after Microsoft redirects back. Returns user info dict or None."""
    flow = session.pop("auth_flow", None)
    if not flow:
        return None

    auth_response = dict(request.args)
    if request.method == "POST":
        auth_response = dict(request.form)

    app = _build_msal_app()
    try:
        result = app.acquire_token_by_auth_code_flow(flow, auth_response)
    except Exception:
        return None

    if "error" in result:
        return None

    id_token_claims = result.get("id_token_claims", {})
    return {
        "name": id_token_claims.get("name", ""),
        "email": (
            id_token_claims.get("preferred_username", "")
            or id_token_claims.get("email", "")
            or id_token_claims.get("upn", "")
        ).lower().strip(),
        "oid": id_token_claims.get("oid", ""),
    }
