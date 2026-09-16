"""Upload a workbook to SharePoint or OneDrive through Graph (stdlib)."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote, urlparse

import config
import graph_http

log = logging.getLogger(__name__)

SIMPLE_UPLOAD_MAX = 4 * 1024 * 1024
CHUNK_SIZE = 327680 * 10
TIMEOUT = 30
UPLOAD_TIMEOUT = 120
REPORTS_SUBFOLDER = "Direct Reports"
_BAD_SEGMENT = re.compile(r'[\\/:*?"<>|#%]')


class DriveError(RuntimeError):
    pass


def strip_reports_home(path: str) -> str:
    rel = (path or "").replace("\\", "/").strip("/")
    home = REPORTS_SUBFOLDER.lower()
    while rel:
        low = rel.lower()
        if low == home:
            return ""
        if low.startswith(home + "/"):
            rel = rel.split("/", 1)[1]
            continue
        return rel
    return ""


def validate_segments(rel_path: str) -> list[str]:
    rel = (rel_path or "").replace("\\", "/").strip("/")
    if not rel:
        return []
    segments: list[str] = []
    for raw in rel.split("/"):
        seg = raw.strip()
        if not seg or seg in (".", ".."):
            raise DriveError(f"invalid folder path segment: {raw!r}")
        if _BAD_SEGMENT.search(seg):
            raise DriveError(f"illegal character in folder path: {raw!r}")
        segments.append(seg)
    return segments


def configured() -> bool:
    return config.entra_configured()


def upload_sharepoint(rel_folder: str, filename: str, content: bytes) -> dict:
    rel = strip_reports_home(rel_folder)
    validate_segments(rel)
    validate_segments(filename)
    if not configured():
        if config.PRODUCTION:
            raise DriveError("SharePoint is not configured (cannot upload file)")
        return {
            "webUrl": f"mock://{rel}/{filename}".strip("/"),
            "name": filename,
            "mock": True,
        }
    drive_id = _sharepoint_drive_id()
    root = f"{REPORTS_SUBFOLDER}/{rel}".strip("/") if rel else REPORTS_SUBFOLDER
    return _upload_under_drive(f"{graph_http.GRAPH_BASE}/drives/{quote(drive_id)}", root, filename, content)


def upload_onedrive(user_email: str, rel_folder: str, filename: str, content: bytes) -> dict:
    user = (user_email or "").strip().lower()
    if not user or "@" not in user:
        raise DriveError("OneDrive upload needs the schedule owner's email.")
    validate_segments(rel_folder)
    validate_segments(filename)
    if not configured():
        if config.PRODUCTION:
            raise DriveError("OneDrive is not configured (cannot upload file)")
        return {
            "webUrl": f"mock-od://{user}/{rel_folder}/{filename}".strip("/"),
            "name": filename,
            "mock": True,
        }
    base = f"{graph_http.GRAPH_BASE}/users/{quote(user)}/drive"
    return _upload_under_drive(base, rel_folder, filename, content)


def _sharepoint_drive_id() -> str:
    site_url = config.sp_site_url()
    if not site_url:
        raise DriveError("SP_SITE_URL is not set. Cannot resolve the SharePoint library.")
    parsed = urlparse(site_url.rstrip("/"))
    host = parsed.netloc
    path = (parsed.path or "").strip("/")
    site_ref = f"{host}:/{path}" if path else host
    site = graph_http.call("GET", f"{graph_http.GRAPH_BASE}/sites/{site_ref}", timeout=TIMEOUT)
    if not site.ok:
        raise DriveError(f"SharePoint site lookup failed (HTTP {site.status_code}) for SP_SITE_URL.")
    site_id = (site.json() or {}).get("id")
    if not site_id:
        raise DriveError("SharePoint site lookup returned no id.")
    drive = graph_http.call("GET", f"{graph_http.GRAPH_BASE}/sites/{quote(str(site_id))}/drive", timeout=TIMEOUT)
    if not drive.ok:
        raise DriveError(f"SharePoint drive lookup failed (HTTP {drive.status_code}).")
    drive_id = (drive.json() or {}).get("id")
    if not drive_id:
        raise DriveError("SharePoint drive lookup returned no id.")
    return str(drive_id)


def _upload_under_drive(drive_base: str, rel_folder: str, filename: str, content: bytes) -> dict:
    _ensure_folder(drive_base, rel_folder)
    path = _abs_path(rel_folder, filename)
    put_url = f"{drive_base}/root:/{path}:/content"
    session_url = f"{drive_base}/root:/{path}:/createUploadSession"
    body = _put_bytes(put_url, session_url, content)
    url = _web_url(body, f"{drive_base}/root:/{path}:", f"{drive_base}/items")
    return {"webUrl": url or "", "name": body.get("name") or filename, "id": body.get("id") or ""}


def _abs_path(rel_folder: str, filename: str) -> str:
    segments = validate_segments(rel_folder) + validate_segments(filename)
    return "/".join(quote(part) for part in segments)


def _ensure_folder(drive_base: str, rel_folder: str) -> None:
    current = ""
    for part in validate_segments(rel_folder):
        url = f"{drive_base}/root:/{current}:/children" if current else f"{drive_base}/root/children"
        resp = graph_http.call(
            "POST",
            url,
            json_body={"name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
            timeout=TIMEOUT,
        )
        if resp.status_code not in (201, 409):
            raise DriveError(f"Could not create folder {part!r} (HTTP {resp.status_code}).")
        enc = quote(part)
        current = f"{current}/{enc}" if current else enc


def _put_bytes(put_url: str, session_url: str, content: bytes) -> dict:
    if len(content) < SIMPLE_UPLOAD_MAX:
        resp = graph_http.call(
            "PUT",
            put_url,
            data=content,
            extra_headers={"Content-Type": "application/octet-stream"},
            timeout=UPLOAD_TIMEOUT,
        )
        if not resp.ok:
            raise DriveError(f"SharePoint upload failed (HTTP {resp.status_code}).")
        parsed = resp.json()
        return parsed if isinstance(parsed, dict) else {}
    session = graph_http.call(
        "POST",
        session_url,
        json_body={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        timeout=TIMEOUT,
    )
    if not session.ok:
        raise DriveError(f"Could not start a Graph upload session (HTTP {session.status_code}).")
    upload_url = (session.json() or {}).get("uploadUrl")
    if not upload_url:
        raise DriveError("Graph upload session did not return uploadUrl.")
    size = len(content)
    start = 0
    last: dict = {}
    while start < size:
        end = min(start + CHUNK_SIZE, size)
        chunk = content[start:end]
        resp = graph_http.call(
            "PUT",
            str(upload_url),
            data=chunk,
            extra_headers={
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end - 1}/{size}",
            },
            timeout=UPLOAD_TIMEOUT,
        )
        if not resp.ok:
            raise DriveError(f"Graph chunked upload failed (HTTP {resp.status_code}).")
        parsed = resp.json()
        if isinstance(parsed, dict):
            last = parsed
        start = end
    return last


def _web_url(body: dict, get_url: str, items_base: str) -> str:
    url = str(body.get("webUrl") or "").strip()
    if url:
        return url
    item_id = str(body.get("id") or "").strip()
    if item_id:
        got = graph_http.call("GET", f"{items_base}/{quote(item_id)}", timeout=TIMEOUT)
        if got.ok:
            url = str((got.json() or {}).get("webUrl") or "").strip()
            if url:
                return url
    got = graph_http.call("GET", get_url, timeout=TIMEOUT)
    if got.ok:
        return str((got.json() or {}).get("webUrl") or "").strip()
    return ""
