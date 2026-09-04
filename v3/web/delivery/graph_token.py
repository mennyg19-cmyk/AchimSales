"""App-only Graph access tokens.

SharePoint and OneDrive sit on a long-lived worker. Caching the token with no
expiry left overnight jobs posting with a dead bearer while Graph mail (which
fetches a token per send) still succeeded.
"""

from __future__ import annotations

import time

TIMEOUT = 30
_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


class GraphAppToken:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._valid_until = 0.0

    def forget(self) -> None:
        self._token = None
        self._valid_until = 0.0

    def get(self, requests) -> str:
        if self._token and time.monotonic() < self._valid_until:
            return self._token
        r = requests.post(
            _TOKEN_URL.format(tenant=self._tenant_id),
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        ttl = int(body.get("expires_in") or 3600)
        self._valid_until = time.monotonic() + max(30, ttl - 300)
        return self._token


def graph_call(requests, tokens: GraphAppToken, verb: str, url: str, *,
               on_retry=None, **kwargs):
    """One Graph call; on 401 drop the cache and retry once with a new token."""
    headers = dict(kwargs.pop("headers", None) or {})
    call = getattr(requests, verb)
    last = None
    for attempt in (0, 1):
        headers["Authorization"] = f"Bearer {tokens.get(requests)}"
        last = call(url, headers=headers, **kwargs)
        if last.status_code != 401 or attempt:
            return last
        tokens.forget()
        if on_retry:
            on_retry()
    return last
