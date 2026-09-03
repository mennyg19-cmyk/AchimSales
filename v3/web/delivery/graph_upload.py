"""Upload bytes to a Graph drive item.

Simple PUT /content works up to 4 MB. Larger files (YTD Ordered workbooks)
must use an upload session or Graph rejects the request.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol

from web.delivery.graph_auth import retry_graph_response

log = logging.getLogger(__name__)

SIMPLE_UPLOAD_MAX = 4 * 1024 * 1024
# Graph requires chunk sizes that are a multiple of 320 KiB (except the last).
CHUNK_SIZE = 327680 * 10  # 3.2 MiB


class _Requests(Protocol):
    def put(self, url: str, **kwargs): ...
    def post(self, url: str, **kwargs): ...
    def get(self, url: str, **kwargs): ...


def web_url_from_item(body: dict | None) -> str:
    """Graph driveItem.webUrl, or createLink's nested link.webUrl."""
    if not body:
        return ""
    url = str(body.get("webUrl") or "").strip()
    if url:
        return url
    link = body.get("link")
    if isinstance(link, dict):
        return str(link.get("webUrl") or "").strip()
    return ""


def _json_dict(response: Any) -> dict:
    if response is None or not getattr(response, "ok", False):
        return {}
    try:
        data = response.json() if hasattr(response, "json") else {}
    except Exception:  # noqa: BLE001 - treat as empty; caller tries the next URL
        return {}
    return data if isinstance(data, dict) else {}


def _path_get_urls(get_url: str) -> list[str]:
    """Graph item-by-path is `root:/path:` (trailing colon). Callers often omit it."""
    url = (get_url or "").rstrip("/")
    if not url:
        return []
    urls = [url]
    if not url.endswith(":"):
        urls.append(url + ":")
    return urls


def resolve_web_url(
    requests: _Requests, *,
    headers: dict[str, str],
    body: dict | None,
    get_url: str,
    items_base: str,
    timeout: float,
) -> str:
    """webUrl from the upload body, else GET the item, else an org view link.

    Chunked upload sessions often return {expirationDateTime, nextExpectedRanges}
    or a driveItem id with no webUrl. Number 4 (~13 MB) always uses the session.
    GET /items/{id} is the app-only way to read webUrl; createLink often 403s.
    """
    url = web_url_from_item(body)
    if url:
        return url
    items = (items_base or "").rstrip("/")
    item_id = str((body or {}).get("id") or "").strip()

    def try_get(target: str) -> dict:
        if not target:
            return {}
        try:
            return _json_dict(requests.get(target, headers=headers, timeout=timeout))
        except Exception:  # noqa: BLE001 - try the next candidate
            return {}

    if item_id and items:
        url = web_url_from_item(try_get(f"{items}/{item_id}"))
        if url:
            return url

    for path_url in _path_get_urls(get_url):
        data = try_get(path_url)
        url = web_url_from_item(data)
        if url:
            return url
        item_id = str(data.get("id") or item_id).strip()
        if item_id and items:
            url = web_url_from_item(try_get(f"{items}/{item_id}"))
            if url:
                return url

    if not item_id or not items:
        return ""
    try:
        r = requests.post(
            f"{items}/{item_id}/createLink",
            headers={**headers, "Content-Type": "application/json"},
            json={"type": "view", "scope": "organization"},
            timeout=timeout,
        )
        if not getattr(r, "ok", False):
            log.warning("Graph createLink failed for item %s: %s",
                        item_id, getattr(r, "status_code", None))
            return ""
        return web_url_from_item(_json_dict(r))
    except Exception:  # noqa: BLE001 - caller can still send the mail without a URL
        log.warning("Graph createLink raised for item %s", item_id, exc_info=True)
        return ""


def upload_drive_item(
    requests: _Requests, *,
    put_url: str,
    session_url: str,
    headers: dict[str, str],
    content: bytes,
    put_timeout: float,
    session_timeout: float = 30,
    token: Callable[[bool], str] | None = None,
) -> dict[str, Any]:
    """PUT small files; createUploadSession + ranged PUTs when over 4 MB."""
    def current_token(refresh: bool) -> str:
        if token:
            return token(refresh)
        return headers["Authorization"].removeprefix("Bearer ")

    def authenticated_headers(access_token: str, extra: dict[str, str]) -> dict[str, str]:
        return {**headers, **extra, "Authorization": f"Bearer {access_token}"}

    if len(content) < SIMPLE_UPLOAD_MAX:
        r = retry_graph_response(
            lambda access_token: requests.put(
                put_url,
                headers=authenticated_headers(access_token, {"Content-Type": "application/octet-stream"}),
                data=content, timeout=put_timeout,
            ),
            current_token,
        )
        if r.status_code not in (200, 201):
            r.raise_for_status()
        return r.json()

    r = retry_graph_response(
        lambda access_token: requests.post(
            session_url,
            headers=authenticated_headers(access_token, {"Content-Type": "application/json"}),
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            timeout=session_timeout,
        ),
        current_token,
    )
    r.raise_for_status()
    upload_url = r.json()["uploadUrl"]
    size = len(content)
    start = 0
    last = None
    resumed = False
    while start < size:
        end = min(start + CHUNK_SIZE, size)
        chunk = content[start:end]
        try:
            last = retry_graph_response(
                lambda _access_token: requests.put(
                    upload_url, data=chunk,
                    headers={"Content-Length": str(len(chunk)),
                             "Content-Range": f"bytes {start}-{end - 1}/{size}"},
                    timeout=put_timeout,
                ),
                current_token,
            )
            last.raise_for_status()
            start = end
        except Exception:
            if resumed:
                raise
            session = requests.get(upload_url, timeout=session_timeout)
            session.raise_for_status()
            ranges = session.json().get("nextExpectedRanges") or []
            next_start = _next_expected_offset(ranges)
            if next_start is None or next_start >= size:
                raise
            log.info(
                "Graph upload chunk failed at byte %s; resuming existing session at byte %s",
                start, next_start,
            )
            resumed = True
            start = next_start
    return last.json() if last is not None else {}


def _next_expected_offset(ranges: list[Any]) -> int | None:
    """Read the first byte offset Graph still expects from its session status."""
    if not ranges or not isinstance(ranges[0], str):
        return None
    try:
        return int(ranges[0].split("-", 1)[0])
    except ValueError:
        return None
