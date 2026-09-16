"""App-only Microsoft Graph HTTP via stdlib urllib. No `requests` package."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

import config

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_SCOPE = "https://graph.microsoft.com/.default"
_TOKEN_TIMEOUT = 30

_cached_token = ""
_cached_until = 0.0


class GraphHttpError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, detail: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class GraphResponse:
    def __init__(self, status_code: int, raw: bytes):
        self.status_code = status_code
        self.raw = raw
        self.ok = 200 <= status_code < 300

    def json(self) -> dict | list:
        if not self.raw:
            return {}
        try:
            parsed = json.loads(self.raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, (dict, list)) else {}


def forget_token() -> None:
    global _cached_token, _cached_until
    _cached_token = ""
    _cached_until = 0.0


def token() -> str:
    global _cached_token, _cached_until
    if _cached_token and time.monotonic() < _cached_until:
        return _cached_token
    url = _TOKEN_URL.format(tenant=urllib.parse.quote(config.graph_tenant(), safe=""))
    body = urllib.parse.urlencode(
        {
            "client_id": config.graph_client_id(),
            "client_secret": config.graph_client_secret(),
            "scope": _SCOPE,
            "grant_type": "client_credentials",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TOKEN_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except Exception as exc:
        raise GraphHttpError("Could not get a Microsoft Graph token.") from exc
    access = payload.get("access_token") if isinstance(payload, dict) else None
    if not access:
        raise GraphHttpError("Could not get a Microsoft Graph token.")
    ttl = int(payload.get("expires_in") or 3600)
    _cached_token = access
    _cached_until = time.monotonic() + max(30, ttl - 300)
    return access


def call(
    method: str,
    url: str,
    *,
    json_body: dict | None = None,
    data: bytes | None = None,
    extra_headers: dict | None = None,
    timeout: int = 30,
) -> GraphResponse:
    headers = {"Authorization": f"Bearer {token()}"}
    if extra_headers:
        headers.update(extra_headers)
    payload = data
    if json_body is not None:
        payload = json.dumps(json_body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=payload, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return GraphResponse(response.status, response.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        if exc.code == 401:
            forget_token()
        return GraphResponse(exc.code, raw)
    except Exception as exc:
        raise GraphHttpError(f"Microsoft Graph could not be reached ({method} {url}).") from exc
