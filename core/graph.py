"""
Microsoft Graph API client for SharePoint operations.

Handles site/drive resolution, file download/upload, folder creation,
and recursive tree upload. Used by runbooks for cloud execution.

All functions accept *access_token* as either a plain ``str`` or a
``core.auth.TokenManager`` instance; in the latter case the token is
resolved (and refreshed if needed) on every API call so long uploads
never hit a 401 due to token expiry.
"""

import logging
import os
from urllib.parse import urlparse

from core.http import get_session

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TIMEOUT = 30
UPLOAD_TIMEOUT = 120


def _resolve_token(access_token) -> str:
    """Return a valid token string, refreshing via TokenManager if needed."""
    if hasattr(access_token, "token"):
        return access_token.token
    return access_token


def resolve_site_and_drive(site_url: str, access_token) -> tuple[str, str]:
    """Return (site_id, drive_id) for a SharePoint site URL."""
    token = _resolve_token(access_token)
    parsed = urlparse(site_url.strip().rstrip("/"))
    hostname = parsed.netloc
    path_part = (parsed.path or "").strip("/")

    if not path_part or path_part.lower() in ("", "sites", "sites/"):
        req_url = f"{GRAPH_BASE}/sites/root"
    else:
        site_path = "/" + path_part if not path_part.startswith("/") else path_part
        req_url = f"{GRAPH_BASE}/sites/{hostname}:{site_path}"

    session = get_session()
    headers = {"Authorization": f"Bearer {token}"}
    r = session.get(req_url, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    site_id = r.json()["id"]

    dr = session.get(f"{GRAPH_BASE}/sites/{site_id}/drive", headers=headers, timeout=TIMEOUT)
    dr.raise_for_status()
    drive_id = dr.json()["id"]

    log.info("Resolved site=%s drive=%s", site_id[:20], drive_id[:20])
    return site_id, drive_id


def list_children(drive_id: str, item_path: str, access_token) -> list[dict]:
    """List children of a drive folder by path."""
    token = _resolve_token(access_token)
    path_clean = item_path.replace("\\", "/").strip("/")
    if path_clean:
        url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{path_clean}:/children"
    else:
        url = f"{GRAPH_BASE}/drives/{drive_id}/root/children"

    session = get_session()
    r = session.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json().get("value", [])


def download_file_content(drive_id: str, item_id: str, access_token) -> bytes:
    """Download file content by item ID."""
    token = _resolve_token(access_token)
    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
    session = get_session()
    r = session.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=UPLOAD_TIMEOUT, stream=True)
    r.raise_for_status()
    return r.content


def download_file_by_path(drive_id: str, cloud_path: str, local_path: str, access_token) -> bool:
    """Download a single file from cloud_path to local_path. Returns True if successful."""
    token = _resolve_token(access_token)
    path_clean = cloud_path.replace("\\", "/").strip("/")
    url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{path_clean}"
    session = get_session()
    r = session.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if r.status_code != 200:
        log.warning("download_file_by_path %s returned status %d", path_clean, r.status_code)
        return False
    data = r.json()
    if "folder" in data:
        return False

    content = download_file_content(drive_id, data["id"], access_token)
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(content)
    log.info("Downloaded: %s", path_clean)
    return True


def upload_file(drive_id: str, parent_path: str, local_path: str, access_token) -> str | None:
    """Upload a single file to parent_path in the drive.

    Returns the SharePoint ``webUrl`` of the uploaded file, or ``None``
    if the URL could not be extracted from the response.

    Raises ``RuntimeError`` on non-200/201 so callers know the upload failed.
    """
    token = _resolve_token(access_token)
    name = os.path.basename(local_path)
    path_clean = parent_path.replace("\\", "/").strip("/")
    url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{path_clean}/{name}:/content"

    session = get_session()
    with open(local_path, "rb") as f:
        r = session.put(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"},
            data=f,
            timeout=UPLOAD_TIMEOUT,
        )
    if r.status_code in (200, 201):
        log.info("Uploaded: %s/%s", path_clean, name)
        try:
            return r.json().get("webUrl")
        except Exception:
            return None
    else:
        msg = "Upload failed (%d): %s/%s - %s" % (r.status_code, path_clean, name, r.text[:200])
        log.error(msg)
        raise RuntimeError(msg)


def ensure_folder(drive_id: str, folder_path: str, access_token) -> None:
    """Ensure a folder path exists in the drive (create if needed).

    Raises ``RuntimeError`` if a required folder cannot be created.
    """
    token = _resolve_token(access_token)
    path = folder_path.replace("\\", "/").strip("/")
    if not path:
        return
    session = get_session()
    parts = path.split("/")
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{current}:/children"
        r = session.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
        if r.status_code == 404:
            parent = "/".join(current.split("/")[:-1])
            if parent:
                create_url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{parent}:/children"
            else:
                create_url = f"{GRAPH_BASE}/drives/{drive_id}/root/children"
            body = {"name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"}
            cr = session.post(
                create_url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
                timeout=TIMEOUT,
            )
            if cr.status_code not in (200, 201):
                msg = "Could not create folder %s: %d" % (current, cr.status_code)
                log.error(msg)
                raise RuntimeError(msg)


def upload_tree(
    drive_id: str,
    cloud_root: str,
    local_dir: str,
    access_token,
    rel_path: str = "",
) -> tuple[int, list[str]]:
    """Recursively upload a local directory tree.

    Returns ``(file_count, [webUrl, ...])``.  The webUrl list contains
    the SharePoint URL for each successfully uploaded file.
    """
    cloud_root = cloud_root.replace("\\", "/").strip("/")
    uploaded = 0
    urls: list[str] = []
    for name in os.listdir(local_dir):
        local_full = os.path.join(local_dir, name)
        cloud_rel = f"{rel_path}/{name}" if rel_path else name
        if os.path.isdir(local_full):
            folder_cloud = f"{cloud_root}/{cloud_rel}".replace("//", "/").strip("/")
            ensure_folder(drive_id, folder_cloud, access_token)
            sub_count, sub_urls = upload_tree(drive_id, cloud_root, local_full, access_token, cloud_rel)
            uploaded += sub_count
            urls.extend(sub_urls)
        else:
            parent_cloud = f"{cloud_root}/{rel_path}".replace("//", "/").strip("/") if rel_path else cloud_root
            ensure_folder(drive_id, parent_cloud, access_token)
            web_url = upload_file(drive_id, parent_cloud, local_full, access_token)
            uploaded += 1
            if web_url:
                urls.append(web_url)
    return uploaded, urls
