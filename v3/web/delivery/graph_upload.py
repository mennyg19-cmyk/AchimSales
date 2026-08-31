"""Upload bytes to a Graph drive item.

Simple PUT /content works up to 4 MB. Larger files (YTD Ordered workbooks)
must use an upload session or Graph rejects the request.
"""

from __future__ import annotations

from typing import Any, Protocol

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
    with no webUrl. The file is on the drive; we have to ask for the item.
    """
    url = web_url_from_item(body)
    if url:
        return url
    item_id = str((body or {}).get("id") or "")
    try:
        r = requests.get(get_url, headers=headers, timeout=timeout)
        if getattr(r, "ok", False):
            data = r.json() if hasattr(r, "json") else {}
            url = web_url_from_item(data)
            if url:
                return url
            item_id = str(data.get("id") or item_id)
    except Exception:  # noqa: BLE001 - still try createLink from the upload id
        pass
    if not item_id:
        return ""
    try:
        r = requests.post(
            f"{items_base}/{item_id}/createLink",
            headers={**headers, "Content-Type": "application/json"},
            json={"type": "view", "scope": "organization"},
            timeout=timeout,
        )
        if not getattr(r, "ok", False):
            return ""
        data = r.json() if hasattr(r, "json") else {}
        return web_url_from_item(data)
    except Exception:  # noqa: BLE001 - caller can still send the mail without a URL
        return ""


def upload_drive_item(
    requests: _Requests, *,
    put_url: str,
    session_url: str,
    headers: dict[str, str],
    content: bytes,
    put_timeout: float,
    session_timeout: float = 30,
) -> dict[str, Any]:
    """PUT small files; createUploadSession + ranged PUTs when over 4 MB."""
    if len(content) < SIMPLE_UPLOAD_MAX:
        r = requests.put(
            put_url,
            headers={**headers, "Content-Type": "application/octet-stream"},
            data=content, timeout=put_timeout,
        )
        if r.status_code not in (200, 201):
            r.raise_for_status()
        return r.json()

    r = requests.post(
        session_url,
        headers={**headers, "Content-Type": "application/json"},
        json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        timeout=session_timeout,
    )
    r.raise_for_status()
    upload_url = r.json()["uploadUrl"]
    size = len(content)
    start = 0
    last = None
    while start < size:
        end = min(start + CHUNK_SIZE, size)
        chunk = content[start:end]
        last = requests.put(
            upload_url,
            data=chunk,
            headers={
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end - 1}/{size}",
            },
            timeout=put_timeout,
        )
        last.raise_for_status()
        start = end
    return last.json() if last is not None else {}
