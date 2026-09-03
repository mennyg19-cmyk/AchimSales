"""Small in-process helpers for Graph app-only authentication and retries."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import time
from collections.abc import Callable, Mapping
from typing import Any

_REFRESH_EARLY_SECONDS = 60
_DEFAULT_RETRY_SECONDS = 1
_MAX_RETRY_SECONDS = 60


class GraphTokenCache:
    """Cache one client-credentials token until shortly before its expiry."""

    def __init__(self) -> None:
        self._token = ""
        self._expires_at = 0.0

    def get(self, acquire: Callable[[], Mapping[str, Any]]) -> str:
        if self._token and time.monotonic() < self._expires_at - _REFRESH_EARLY_SECONDS:
            return self._token
        payload = acquire()
        token = str(payload.get("access_token") or "")
        if not token:
            raise RuntimeError("Microsoft Graph did not return an access token.")
        expires_in = max(0, int(payload.get("expires_in") or 0))
        self._token = token
        self._expires_at = time.monotonic() + expires_in
        return token

    def clear(self) -> None:
        self._token = ""
        self._expires_at = 0.0


def acquire_client_credentials(
    *,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    timeout: float,
) -> dict[str, Any]:
    """Fetch one app-only Graph token. Callers cache the result in GraphTokenCache."""
    import requests

    response = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Microsoft Graph token endpoint returned a non-object payload.")
    return payload


def cached_app_token(
    cache: GraphTokenCache,
    *,
    refresh: bool,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    timeout: float,
) -> str:
    if refresh:
        cache.clear()
    return cache.get(lambda: acquire_client_credentials(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        timeout=timeout,
    ))


def retry_after_seconds(value: str | None) -> float:
    """Return Graph's Retry-After delay, capped to keep workers responsive."""
    if not value:
        return _DEFAULT_RETRY_SECONDS
    try:
        return min(_MAX_RETRY_SECONDS, max(0, float(int(value))))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return min(_MAX_RETRY_SECONDS, max(0, (retry_at - datetime.now(UTC)).total_seconds()))
        except (TypeError, ValueError):
            return _DEFAULT_RETRY_SECONDS


def retry_graph_response(
    send: Callable[[str], Any],
    token: Callable[[bool], str],
) -> Any:
    """Retry one rejected credential or one throttled/unavailable Graph request."""
    response = send(token(False))
    if getattr(response, "status_code", None) == 401:
        response = send(token(True))
    if getattr(response, "status_code", None) in (429, 503):
        time.sleep(retry_after_seconds(getattr(response, "headers", {}).get("Retry-After")))
        response = send(token(False))
    return response


def graph_get(url: str, token: Callable[[bool], str], *, timeout: float) -> Any:
    import requests

    return retry_graph_response(
        lambda access: requests.get(
            url, headers={"Authorization": f"Bearer {access}"}, timeout=timeout,
        ),
        token,
    )


def graph_post(url: str, token: Callable[[bool], str], *, payload: Mapping[str, Any], timeout: float) -> Any:
    import requests

    return retry_graph_response(
        lambda access: requests.post(
            url,
            headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        ),
        token,
    )
