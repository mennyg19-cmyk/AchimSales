"""SharePoint delivery via Microsoft Graph (app-only client credentials).

Files land under ``<DriveRootPath>/Direct Reports`` - the folder users already
recognize from the live app. When Graph creds are absent the service runs in
mock mode: it returns a small folder tree and pretends uploads succeed, so the
picker and the email/schedule flows work end-to-end in local dev.

Tokens and the resolved drive id are cached on the instance (the service is a
singleton in app.config).
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote, urlparse

from web.config import Config

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TIMEOUT = 30
UPLOAD_TIMEOUT = 120
REPORTS_SUBFOLDER = "Direct Reports"

# Characters that must never appear in a folder/file segment we interpolate into a
# Graph path (path traversal, drive-path separators, and OneDrive-reserved chars).
_BAD_SEGMENT = re.compile(r'[\\/:*?"<>|#%]')

_MOCK_TREE: dict[str, list[str]] = {
    "": ["Invoiced", "Ordered", "Salesman", "Customer Activity"],
    "Invoiced": ["Daily", "Weekly", "Monthly"],
    "Ordered": ["Daily", "Weekly", "Pending"],
    "Invoiced/Monthly": ["2025", "2026"],
}


class SharePointService:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._root = f"{cfg.sp_drive_root}/{REPORTS_SUBFOLDER}".strip("/")
        self._token: str | None = None
        self._drive_id: str | None = None

    def is_configured(self) -> bool:
        return bool(self.cfg.tenant_id and self.cfg.client_id
                    and self.cfg.client_secret)

    def root_path(self) -> str:
        return self._root

    def _mock_or_raise(self, what: str):
        """Non-prod falls back to the mock tree; prod must fail loudly rather than
        silently pretend a delivery happened."""
        if self.cfg.is_prod:
            raise RuntimeError(f"SharePoint is not configured (cannot {what})")
        return None

    # -- public API ---------------------------------------------------------

    def list_folders(self, rel_path: str = "") -> list[dict]:
        if not self.is_configured():
            self._mock_or_raise("list folders")
            return _mock_folders(rel_path)
        import requests

        url = f"{self._drive_base()}/root:/{self._abs(rel_path)}:/children"
        r = requests.get(url, headers={"Authorization": f"Bearer {self._get_token()}"}, timeout=TIMEOUT)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        rel_clean = (rel_path or "").strip("/")
        out = [
            {"name": it.get("name", ""),
             "path": f"{rel_clean}/{it.get('name', '')}".strip("/"),
             "id": it.get("id", "")}
            for it in r.json().get("value", []) if "folder" in it
        ]
        out.sort(key=lambda f: f["name"].lower())
        return out

    def upload_file(self, rel_folder: str, filename: str, content: bytes) -> dict[str, Any]:
        _validate_segments(rel_folder)
        _validate_segments(filename)
        if not self.is_configured():
            self._mock_or_raise("upload file")
            log.info("SharePoint mock: pretending to upload %s (%d bytes) to %r",
                     filename, len(content), rel_folder)
            return {"webUrl": f"mock://{rel_folder}/{filename}", "name": filename,
                    "id": f"mock-{rel_folder}-{filename}".replace(" ", "_"), "mock": True}
        import requests

        self._ensure_folder(rel_folder)
        url = f"{self._drive_base()}/root:/{self._abs(rel_folder)}/{quote(filename)}:/content"
        r = requests.put(
            url,
            headers={"Authorization": f"Bearer {self._get_token()}",
                     "Content-Type": "application/octet-stream"},
            data=content, timeout=UPLOAD_TIMEOUT,
        )
        if r.status_code not in (200, 201):
            r.raise_for_status()
        body = r.json()
        return {"webUrl": body.get("webUrl"), "name": body.get("name"), "id": body.get("id")}

    # -- internals ----------------------------------------------------------

    def _abs(self, rel_path: str) -> str:
        """Build the Graph drive-path under our root, URL-encoding every segment.

        Validates the caller-supplied segments first so a crafted path can't escape
        the root (`..`) or inject Graph path operators."""
        segments = _validate_segments(rel_path)
        root_enc = "/".join(quote(s) for s in self._root.split("/") if s)
        rel_enc = "/".join(quote(s) for s in segments)
        return f"{root_enc}/{rel_enc}" if rel_enc else root_enc

    def _get_token(self) -> str:
        if self._token:
            return self._token
        import requests

        url = f"https://login.microsoftonline.com/{self.cfg.tenant_id}/oauth2/v2.0/token"
        r = requests.post(url, data={
            "client_id": self.cfg.client_id, "client_secret": self.cfg.client_secret,
            "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials",
        }, timeout=TIMEOUT)
        r.raise_for_status()
        self._token = r.json()["access_token"]
        return self._token

    def _drive_base(self) -> str:
        return f"{GRAPH_BASE}/drives/{self._resolve_drive_id()}"

    def _resolve_drive_id(self) -> str:
        if self._drive_id:
            return self._drive_id
        import requests

        headers = {"Authorization": f"Bearer {self._get_token()}"}
        site_url = (self.cfg.sp_site_url or "").strip()

        site_id: str | None = None

        if site_url:
            parsed = urlparse(site_url.rstrip("/"))
            host = parsed.netloc
            path = (parsed.path or "").strip("/")
            site_ref = f"{host}:/{path}" if path else host
            site = requests.get(f"{GRAPH_BASE}/sites/{site_ref}", headers=headers, timeout=TIMEOUT)
            if site.ok:
                site_id = site.json()["id"]
            else:
                log.warning("SP_SITE_URL resolved to 404 (%s), falling back to search", site_ref)

        if site_id is None:
            r = requests.get(f"{GRAPH_BASE}/sites?search=achim", headers=headers, timeout=TIMEOUT)
            r.raise_for_status()
            for s in r.json().get("value", []):
                sid = s.get("id")
                dr = requests.get(f"{GRAPH_BASE}/sites/{sid}/drive", headers=headers, timeout=TIMEOUT)
                if dr.status_code != 200:
                    continue
                did = dr.json()["id"]
                test = requests.get(
                    f"{GRAPH_BASE}/drives/{did}/root:/{self._root}:/children",
                    headers=headers, timeout=TIMEOUT)
                if test.status_code == 200:
                    self._drive_id = did
                    log.info("resolved SharePoint drive %s via search", did)
                    return did
            raise RuntimeError("Could not find SharePoint site with Direct Reports folder")

        drive = requests.get(f"{GRAPH_BASE}/sites/{site_id}/drive",
                             headers=headers, timeout=TIMEOUT)
        drive.raise_for_status()
        self._drive_id = drive.json()["id"]
        log.info("resolved SharePoint drive %s via site URL", self._drive_id)
        return self._drive_id

    def _ensure_folder(self, rel_path: str) -> None:
        import requests

        segments = [s for s in self._root.split("/") if s] + _validate_segments(rel_path)
        if not segments:
            return
        headers = {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}
        base = self._drive_base()
        current_enc = ""
        for part in segments:
            url = f"{base}/root:/{current_enc}:/children" if current_enc else f"{base}/root/children"
            r = requests.post(url, headers=headers, timeout=TIMEOUT, json={
                "name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"})
            if r.status_code not in (201, 409):
                r.raise_for_status()
            seg_enc = quote(part)
            current_enc = f"{current_enc}/{seg_enc}" if current_enc else seg_enc


def _validate_segments(rel_path: str) -> list[str]:
    """Split a caller-supplied relative path into clean segments or raise.

    Rejects empty/`.`/`..` segments and OneDrive/Graph-reserved characters so a
    crafted folder path can neither traverse out of our root nor inject path ops."""
    rel = (rel_path or "").replace("\\", "/").strip("/")
    if not rel:
        return []
    segments: list[str] = []
    for raw in rel.split("/"):
        seg = raw.strip()
        if not seg or seg in (".", ".."):
            raise ValueError(f"invalid SharePoint path segment: {raw!r}")
        if _BAD_SEGMENT.search(seg):
            raise ValueError(f"illegal character in SharePoint path segment: {raw!r}")
        segments.append(seg)
    return segments


def _mock_folders(rel_path: str) -> list[dict]:
    rel = (rel_path or "").strip("/")
    return [
        {"name": name, "path": f"{rel}/{name}".strip("/"),
         "id": f"mock-{rel}-{name}".replace(" ", "_")}
        for name in _MOCK_TREE.get(rel, [])
    ]
