"""Cached Microsoft Graph app-only token with expiry."""

from __future__ import annotations

import time

from web.delivery.states import TOKEN_REFRESH_SKEW_SECONDS

_GRAPH_SCOPE = "https://graph.microsoft.com/.default"


class GraphTokenError(RuntimeError):
    """Could not acquire a Graph token."""


class GraphTokenCache:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at = 0.0

    def get(self) -> str:
        now = time.time()
        if self._token and now < self._expires_at - TOKEN_REFRESH_SKEW_SECONDS:
            return self._token
        token, expires_in = self._acquire()
        self._token = token
        self._expires_at = now + max(60.0, float(expires_in))
        return token

    def clear(self) -> None:
        self._token = None
        self._expires_at = 0.0

    def _acquire(self) -> tuple[str, int]:
        import msal

        try:
            app = msal.ConfidentialClientApplication(
                self._client_id,
                authority=f"https://login.microsoftonline.com/{self._tenant_id}",
                client_credential=self._client_secret,
            )
            token_response = app.acquire_token_for_client(scopes=[_GRAPH_SCOPE])
        except Exception as exc:  # noqa: BLE001
            raise GraphTokenError("Could not get a Microsoft Graph token.") from exc
        token = token_response.get("access_token")
        if not token:
            raise GraphTokenError("Could not get a Microsoft Graph token.")
        expires_in = int(token_response.get("expires_in") or 3600)
        return token, expires_in
