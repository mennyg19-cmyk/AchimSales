"""
SharePoint file access via Microsoft Graph API.

Thin wrapper around the same Graph endpoints used by
runbooks/universal_runbook.py, but importable from the webapp.
Uses core/auth.py for token acquisition.

Uses the same sites/{site_name}/drive URL pattern that already works
in dashboard_data.py for downloading run_log.csv.
"""

import logging
import os

import requests

from config.settings import get_client_id, get_client_secret, get_tenant_id
from core.auth import get_graph_token

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TIMEOUT = 30
DRIVE_ROOT_PATH = os.environ.get("DriveRootPath", "D365 F&O").strip().strip("/")
REPORTS_CLOUD_ROOT = f"{DRIVE_ROOT_PATH}/Direct Reports"


def _get_token() -> str:
    return get_graph_token(get_tenant_id(), get_client_id(), get_client_secret())


_cached_drive_id: str | None = None


def _resolve_drive_id() -> str:
    """Resolve and cache the SharePoint document library drive ID.

    Uses SP_SITE_URL if set, otherwise searches for the site containing
    the Direct Reports folder.
    """
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
        if r.status_code == 404:
            raise RuntimeError(
                f"SharePoint site lookup failed: SP_SITE_URL points to a site that "
                f"does not exist ({site_url}). Fix the SP_SITE_URL app setting."
            )
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
    """Return the base Graph URL for the SharePoint document library drive."""
    drive_id = _resolve_drive_id()
    return f"{GRAPH_BASE}/drives/{drive_id}"


def list_children(cloud_path: str) -> list[dict]:
    """List children of a SharePoint folder."""
    token = _get_token()
    p = cloud_path.replace("\\", "/").strip("/")
    base = _drive_base_url()
    url = f"{base}/root:/{p}:/children" if p else f"{base}/root/children"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json().get("value", [])


def download_file_content(item_id: str) -> bytes:
    """Download a file's content by item ID."""
    token = _get_token()
    base = _drive_base_url()
    url = f"{base}/items/{item_id}/content"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=120)
    r.raise_for_status()
    return r.content


def download_file_by_path(cloud_path: str) -> bytes:
    """Download a file's content by its SharePoint path."""
    token = _get_token()
    base = _drive_base_url()
    p = cloud_path.replace("\\", "/").strip("/")
    url = f"{base}/root:/{p}:/content"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=120)
    r.raise_for_status()
    return r.content


