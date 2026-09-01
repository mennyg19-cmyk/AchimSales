"""Upload bytes to a Graph drive item.

Simple PUT /content works up to 4 MB. Larger files (YTD Ordered workbooks)
must use an upload session or Graph rejects the request. A crash mid-session
resumes from Graph `nextExpectedRanges` when the session URL is still valid.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Protocol

SIMPLE_UPLOAD_MAX = 4 * 1024 * 1024
# Graph requires chunk sizes that are a multiple of 320 KiB (except the last).
CHUNK_SIZE = 327680 * 10  # 3.2 MiB

SessionHook = Callable[[str], None]


class _Requests(Protocol):
    def put(self, url: str, **kwargs): ...
    def post(self, url: str, **kwargs): ...


def upload_drive_item(
    requests: _Requests, *,
    put_url: str,
    session_url: str,
    headers: dict[str, str],
    content: bytes,
    put_timeout: float,
    session_timeout: float = 30,
    resume_url: str = "",
    on_session: SessionHook | None = None,
) -> dict[str, Any]:
    """PUT small files; createUploadSession + ranged PUTs when over 4 MB."""
    if len(content) < SIMPLE_UPLOAD_MAX:
        r = _put_with_retry(
            requests, put_url,
            data=content,
            headers={**headers, "Content-Type": "application/octet-stream"},
            timeout=put_timeout,
        )
        if r.status_code not in (200, 201):
            r.raise_for_status()
        return r.json()

    upload_url = (resume_url or "").strip()
    start = 0
    if upload_url:
        nxt = _session_next_start(requests, upload_url, timeout=session_timeout)
        if nxt is None:
            upload_url = ""
        else:
            start = nxt
    if not upload_url:
        r = _request_with_retry(
            requests, "post", session_url,
            headers={**headers, "Content-Type": "application/json"},
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            timeout=session_timeout,
        )
        r.raise_for_status()
        upload_url = r.json()["uploadUrl"]
        start = 0
        if on_session is not None:
            on_session(upload_url)
    size = len(content)
    last = None
    while start < size:
        end = min(start + CHUNK_SIZE, size)
        chunk = content[start:end]
        last = _request_with_retry(
            requests, "put", upload_url,
            data=chunk,
            headers={
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end - 1}/{size}",
            },
            timeout=put_timeout,
        )
        try:
            last.raise_for_status()
        except Exception:
            nxt = _session_next_start(requests, upload_url, timeout=session_timeout)
            if nxt is None or nxt == start:
                raise
            start = nxt
            continue
        start = end
    return last.json() if last is not None else {}


def _session_next_start(requests, upload_url: str, *, timeout: float) -> int | None:
    getter = getattr(requests, "get", None)
    if getter is None:
        return None
    r = getter(upload_url, timeout=timeout)
    if r.status_code in (404, 410):
        return None
    if r.status_code >= 400:
        return None
    try:
        ranges = (r.json() or {}).get("nextExpectedRanges") or []
    except Exception:  # noqa: BLE001
        return None
    if not ranges:
        return 0
    first = str(ranges[0]).split("-", 1)[0].strip()
    try:
        return int(first)
    except ValueError:
        return 0


def _put_with_retry(requests, url, *, data, headers, timeout, attempts: int = 3):
    return _request_with_retry(
        requests, "put", url, data=data, headers=headers, timeout=timeout,
        attempts=attempts,
    )


def _request_with_retry(requests, method, url, *, attempts: int = 3, **kwargs):
    call = getattr(requests, method)
    last = None
    for attempt in range(1, attempts + 1):
        last = call(url, **kwargs)
        if last.status_code in (429, 503) and attempt < attempts:
            from web.ops.metrics import note_graph_throttle
            note_graph_throttle(last.status_code)
            raw = last.headers.get("Retry-After") or last.headers.get("retry-after") or ""
            try:
                delay = min(60.0, float(raw))
            except (TypeError, ValueError):
                delay = min(30.0, float(2 ** attempt))
            time.sleep(delay)
            continue
        return last
    return last
