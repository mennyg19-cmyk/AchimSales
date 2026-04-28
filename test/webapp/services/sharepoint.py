"""SharePoint file access for the v2 app.

Thin wrapper around Microsoft Graph. Uploads files, browses folders, and
falls back to mock data when Graph creds are not configured (dev mode).

Root is pinned to the 'Direct Reports' folder under the configured
document library, which is what users already recognize from the live app.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from test.config.settings import AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID, USE_MOCK_DATA

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TIMEOUT = 30
UPLOAD_TIMEOUT = 120

DRIVE_ROOT_PATH = os.environ.get("DriveRootPath", "D365 F&O").strip().strip("/")
REPORTS_CLOUD_ROOT = f"{DRIVE_ROOT_PATH}/Direct Reports"


class SharePointNotConfigured(RuntimeError):
    """Raised when SP env vars are missing and mock fallback is disabled."""


# ---------------------------------------------------------------------------
# Auth / drive resolution
# ---------------------------------------------------------------------------

_cached_token: str | None = None
_cached_drive_id: str | None = None


def is_configured() -> bool:
    """True when we have enough env vars to talk to Graph."""
    return bool(AZURE_TENANT_ID and AZURE_CLIENT_ID and AZURE_CLIENT_SECRET)


def get_root_path() -> str:
    """Direct reports root path, shown to users in the folder picker."""
    return REPORTS_CLOUD_ROOT


def _get_token() -> str:
    global _cached_token
    if _cached_token:
        return _cached_token
    if not is_configured():
        raise SharePointNotConfigured(
            "Graph credentials not configured (need AZURE_TENANT_ID / CLIENT_ID / CLIENT_SECRET)"
        )
    url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token"
    body = {
        "client_id":     AZURE_CLIENT_ID,
        "client_secret": AZURE_CLIENT_SECRET,
        "scope":         "https://graph.microsoft.com/.default",
        "grant_type":    "client_credentials",
    }
    r = requests.post(url, data=body, timeout=TIMEOUT)
    r.raise_for_status()
    _cached_token = r.json()["access_token"]
    return _cached_token


def _resolve_drive_id() -> str:
    """Resolve and cache the SharePoint drive ID."""
    global _cached_drive_id
    if _cached_drive_id:
        return _cached_drive_id

    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}

    site_url = os.environ.get("SP_SITE_URL", "").strip()
    if site_url:
        from urllib.parse import urlparse
        parsed = urlparse(site_url.rstrip("/"))
        hostname = parsed.netloc
        path_part = (parsed.path or "").strip("/")
        if path_part and path_part.lower() not in ("", "sites", "sites/"):
            site_path = "/" + path_part if not path_part.startswith("/") else path_part
            req_url = f"{GRAPH_BASE}/sites/{hostname}:{site_path}"
        else:
            req_url = f"{GRAPH_BASE}/sites/{hostname}"
        r = requests.get(req_url, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        site_id = r.json()["id"]
    else:
        r = requests.get(f"{GRAPH_BASE}/sites?search=achim", headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        sites = r.json().get("value", [])
        site_id = None
        for s in sites:
            sid = s.get("id")
            dr = requests.get(f"{GRAPH_BASE}/sites/{sid}/drive", headers=headers, timeout=TIMEOUT)
            if dr.status_code != 200:
                continue
            did = dr.json()["id"]
            test = requests.get(
                f"{GRAPH_BASE}/drives/{did}/root:/{REPORTS_CLOUD_ROOT}:/children",
                headers=headers, timeout=TIMEOUT,
            )
            if test.status_code == 200:
                _cached_drive_id = did
                log.info("Resolved SharePoint drive: %s (site: %s)", did, s.get("displayName"))
                return did
        raise RuntimeError("Could not find SharePoint site with Direct Reports folder")

    dr = requests.get(f"{GRAPH_BASE}/sites/{site_id}/drive", headers=headers, timeout=TIMEOUT)
    dr.raise_for_status()
    _cached_drive_id = dr.json()["id"]
    log.info("Resolved SharePoint drive: %s", _cached_drive_id)
    return _cached_drive_id


def _drive_base_url() -> str:
    return f"{GRAPH_BASE}/drives/{_resolve_drive_id()}"


# ---------------------------------------------------------------------------
# Mock tree (used when Graph creds are absent AND USE_MOCK_DATA is true)
# ---------------------------------------------------------------------------

_MOCK_TREE: dict[str, list[str]] = {
    "":                            ["Invoiced", "Ordered", "Salesman", "Customer Activity"],
    "Invoiced":                    ["Daily", "Weekly", "Monthly"],
    "Invoiced/Daily":              [],
    "Invoiced/Weekly":             [],
    "Invoiced/Monthly":            ["2025", "2026"],
    "Invoiced/Monthly/2025":       [],
    "Invoiced/Monthly/2026":       [],
    "Ordered":                     ["Daily", "Weekly", "Pending"],
    "Ordered/Daily":               [],
    "Ordered/Weekly":               [],
    "Ordered/Pending":              [],
    "Salesman":                    [],
    "Customer Activity":           [],
}


def _mock_list_folders(rel_path: str) -> list[dict]:
    rel = rel_path.strip("/")
    children = _MOCK_TREE.get(rel, [])
    return [
        {
            "name": name,
            "path": f"{rel}/{name}".strip("/"),
            "id":   f"mock-{rel}-{name}".replace(" ", "_"),
        }
        for name in children
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _abs_path(rel_path: str) -> str:
    """Convert picker-relative path to absolute drive path."""
    rel = (rel_path or "").replace("\\", "/").strip("/")
    return f"{REPORTS_CLOUD_ROOT}/{rel}" if rel else REPORTS_CLOUD_ROOT


def list_folders(rel_path: str = "") -> list[dict]:
    """List folders under the Direct Reports root at the given relative path.

    Returns a list of {name, path, id} where `path` is relative to
    REPORTS_CLOUD_ROOT (what the picker passes back and what gets stored
    in the schedule.sharepoint_path column).
    """
    if not is_configured():
        if USE_MOCK_DATA:
            log.info("SharePoint mock mode: returning mock folders for %r", rel_path)
            return _mock_list_folders(rel_path)
        raise SharePointNotConfigured(
            "Graph credentials not configured (set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET)"
        )

    token = _get_token()
    abs_path = _abs_path(rel_path)
    base = _drive_base_url()
    url = f"{base}/root:/{abs_path}:/children"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    items = r.json().get("value", [])
    rel_clean = (rel_path or "").strip("/")
    result = []
    for it in items:
        if "folder" not in it:
            continue
        name = it.get("name", "")
        path = f"{rel_clean}/{name}".strip("/")
        result.append({"name": name, "path": path, "id": it.get("id", "")})
    result.sort(key=lambda r: r["name"].lower())
    return result


def ensure_folder(rel_path: str) -> None:
    """Create folder hierarchy if missing. Idempotent."""
    if not is_configured():
        if USE_MOCK_DATA:
            log.info("SharePoint mock mode: pretending to ensure %r", rel_path)
            return
        raise SharePointNotConfigured("Graph credentials not configured")

    token = _get_token()
    base = _drive_base_url()
    rel = (rel_path or "").replace("\\", "/").strip("/")
    if not rel:
        return
    parts = f"{REPORTS_CLOUD_ROOT}/{rel}".split("/")
    current = ""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for part in parts:
        if not part:
            continue
        if current:
            url = f"{base}/root:/{current}:/children"
        else:
            url = f"{base}/root/children"
        body = {"name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}
        r = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
        # 201 = created, 409 = already exists (fine)
        if r.status_code not in (201, 409):
            r.raise_for_status()
        current = f"{current}/{part}" if current else part


def upload_file(rel_folder_path: str, filename: str, content: bytes) -> dict[str, Any]:
    """Upload bytes to SharePoint. Returns {webUrl, name, id}.

    Creates the folder if missing.
    """
    if not is_configured():
        if USE_MOCK_DATA:
            log.info("SharePoint mock mode: pretending to upload %s (%d bytes) to %r",
                     filename, len(content), rel_folder_path)
            return {
                "webUrl": f"mock://{rel_folder_path}/{filename}",
                "name":   filename,
                "id":     f"mock-{rel_folder_path}-{filename}".replace(" ", "_"),
            }
        raise SharePointNotConfigured("Graph credentials not configured")

    ensure_folder(rel_folder_path)
    token = _get_token()
    base = _drive_base_url()
    abs_path = _abs_path(rel_folder_path)
    url = f"{base}/root:/{abs_path}/{filename}:/content"
    r = requests.put(
        url,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/octet-stream"},
        data=content, timeout=UPLOAD_TIMEOUT,
    )
    if r.status_code not in (200, 201):
        r.raise_for_status()
    body = r.json()
    return {"webUrl": body.get("webUrl"), "name": body.get("name"), "id": body.get("id")}
