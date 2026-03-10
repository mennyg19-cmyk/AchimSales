"""
Unified authentication for D365 F&O (OData) and Microsoft Graph (SharePoint).

Both use MSAL client-credentials flow with the same tenant/client/secret,
but different scopes (D365 env URL vs graph.microsoft.com).

Token acquisition is wrapped with a simple retry (2 retries, 1 s delay) to
handle transient Azure AD / network hiccups.

``TokenManager`` keeps a cached token and transparently refreshes it before
expiry so long-running operations (large uploads) never hit a 401.
"""

import logging
import time
from functools import lru_cache

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


class TokenManager:
    """Auto-refreshing token wrapper.

    Use ``mgr.token`` to get a valid access-token string; the manager
    re-acquires transparently when the token is within
    ``_TOKEN_REFRESH_MARGIN`` seconds of expiry.
    """

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, scopes: list[str], label: str = ""):
        self._app = _build_msal_app(tenant_id, client_id, client_secret)
        self._scopes = scopes
        self._label = label
        self._access_token: str | None = None
        self._acquired_at: float = 0.0
        self._lifetime: int = 3600

    def _acquire(self):
        result = retry_call(_acquire_token, self._app, self._scopes, self._label, retries=2, delay=1.0)
        self._access_token = result["access_token"]
        self._acquired_at = time.monotonic()
        self._lifetime = int(result.get("expires_in", 3600))
        log.info("%s token acquired (expires_in=%ds)", self._label or "OAuth", self._lifetime)

    @property
    def token(self) -> str:
        age = time.monotonic() - self._acquired_at
        if self._access_token is None or age >= (self._lifetime - _TOKEN_REFRESH_MARGIN):
            self._acquire()
        return self._access_token  # type: ignore[return-value]


def get_d365_token(tenant_id: str, client_id: str, client_secret: str, env_url: str) -> str:
    """Acquire OAuth2 token for D365 F&O (client credentials) with retry.

    Args:
        env_url: D365 environment base URL, e.g. https://org.operations.dynamics.com
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


def get_graph_token_manager(tenant_id: str, client_id: str, client_secret: str) -> TokenManager:
    """Return a ``TokenManager`` for Microsoft Graph that auto-refreshes."""
    return TokenManager(tenant_id, client_id, client_secret, ["https://graph.microsoft.com/.default"], "Graph")
