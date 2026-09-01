"""
Unified authentication for D365 F&O (OData) and Microsoft Graph (SharePoint).

Both use MSAL client-credentials flow with the same tenant/client/secret,
but different scopes (D365 env URL vs graph.microsoft.com).

Token acquisition is wrapped with a simple retry (2 retries, 1 s delay) to
handle transient Azure AD / network hiccups.

D365TokenManager provides auto-refreshing tokens for long-running OData
fetches that may exceed the default ~60 min token lifetime.
"""

import logging
import time

import msal

from core.http import retry_call

log = logging.getLogger(__name__)

_TOKEN_REFRESH_MARGIN = 300  # refresh 5 min before expiry


def _build_msal_app(tenant_id: str, client_id: str, client_secret: str) -> msal.ConfidentialClientApplication:
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    return msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret,
    )


def _acquire_token(app: msal.ConfidentialClientApplication, scopes: list[str], label: str) -> dict:
    """Acquire a token dict, raising ``RuntimeError`` on failure."""
    result = app.acquire_token_for_client(scopes=scopes)
    if not result or "access_token" not in result:
        err = result.get("error_description", result) if result else "No result"
        raise RuntimeError(f"Failed to acquire {label} token: {err}")
    return result


class D365TokenManager:
    """Auto-refreshing D365 token for long-running OData fetches.

    Use as a drop-in replacement for a plain token string -- call
    ``str(mgr)`` or access ``mgr.token`` to get a fresh token.
    The OData layer resolves this automatically via ``resolve_token()``.
    """

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, env_url: str):
        self._app = _build_msal_app(tenant_id, client_id, client_secret)
        self._scope = [f"{env_url.rstrip('/')}/.default"]
        self._token: str | None = None
        self._acquired_at = 0.0
        self._lifetime = 3600

    def _acquire(self):
        result = retry_call(_acquire_token, self._app, self._scope, "D365", retries=2, delay=1.0)
        self._token = result["access_token"]
        self._acquired_at = time.monotonic()
        self._lifetime = int(result.get("expires_in", 3600))
        log.info("D365 token acquired (expires_in=%ds)", self._lifetime)

    @property
    def token(self) -> str:
        age = time.monotonic() - self._acquired_at
        if self._token is None or age >= (self._lifetime - _TOKEN_REFRESH_MARGIN):
            self._acquire()
        return self._token  # type: ignore[return-value]

    def __str__(self) -> str:
        return self.token


def resolve_token(token) -> str:
    """Accept a plain string or a D365TokenManager and return a fresh token string."""
    if isinstance(token, D365TokenManager):
        return token.token
    return token


def get_d365_token(tenant_id: str, client_id: str, client_secret: str, env_url: str) -> str:
    """Acquire OAuth2 token for D365 F&O (client credentials) with retry.

    Args:
        env_url: D365 environment base URL, e.g. https://org.operations.dynamics.com

    Note: For long-running fetches (>30 min), use D365TokenManager instead
    to avoid token expiration mid-request.
    """
    app = _build_msal_app(tenant_id, client_id, client_secret)
    scope = f"{env_url.rstrip('/')}/.default"
    result = retry_call(_acquire_token, app, [scope], "D365", retries=2, delay=1.0)
    log.info("D365 token acquired")
    return result["access_token"]


def get_graph_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Acquire OAuth2 token for Microsoft Graph (client credentials) with retry."""
    app = _build_msal_app(tenant_id, client_id, client_secret)
    result = retry_call(
        _acquire_token, app, ["https://graph.microsoft.com/.default"], "Graph",
        retries=2, delay=1.0,
    )
    log.info("Graph token acquired")
    return result["access_token"]
