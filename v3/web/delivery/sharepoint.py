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
from typing import Any
from urllib.parse import urlparse

from web.config import Config

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TIMEOUT = 30
UPLOAD_TIMEOUT = 120
REPORTS_SUBFOLDER = "Direct Reports"

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
        return bool(self.cfg.tenant_id and self.cfg.client_id and self.cfg.client_secret)

    def root_path(self) -> str:
        return self._root

    # -- public API ---------------------------------------------------------

    def list_folders(self, rel_path: str = "") -> list[dict]:
        if not self.is_configured():
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
        if not self.is_configured():
            log.info("SharePoint mock: pretending to upload %s (%d bytes) to %r",
                     filename, len(content), rel_folder)
            return {"webUrl": f"mock://{rel_folder}/{filename}", "name": filename,
                    "id": f"mock-{rel_folder}-{filename}".replace(" ", "_"), "mock": True}
        import requests

        self._ensure_folder(rel_folder)
        url = f"{self._drive_base()}/root:/{self._abs(rel_folder)}/{filename}:/content"
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
        rel = (rel_path or "").replace("\\", "/").strip("/")
        return f"{self._root}/{rel}" if rel else self._root

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
        parsed = urlparse(self.cfg.sp_site_url.rstrip("/"))
        host = parsed.netloc
        path = (parsed.path or "").strip("/")
        site_ref = f"{host}:/{path}" if path else host
        site = requests.get(f"{GRAPH_BASE}/sites/{site_ref}", headers=headers, timeout=TIMEOUT)
        site.raise_for_status()
        drive = requests.get(f"{GRAPH_BASE}/sites/{site.json()['id']}/drive",
                             headers=headers, timeout=TIMEOUT)
        drive.raise_for_status()
        self._drive_id = drive.json()["id"]
        return self._drive_id

    def _ensure_folder(self, rel_path: str) -> None:
        import requests

        rel = (rel_path or "").replace("\\", "/").strip("/")
        if not rel:
            return
        headers = {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}
        base = self._drive_base()
        current = ""
        for part in f"{self._root}/{rel}".split("/"):
            if not part:
                continue
            url = f"{base}/root:/{current}:/children" if current else f"{base}/root/children"
            r = requests.post(url, headers=headers, timeout=TIMEOUT, json={
                "name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"})
            if r.status_code not in (201, 409):
                r.raise_for_status()
            current = f"{current}/{part}" if current else part


def _mock_folders(rel_path: str) -> list[dict]:
    rel = (rel_path or "").strip("/")
    return [
        {"name": name, "path": f"{rel}/{name}".strip("/"),
         "id": f"mock-{rel}-{name}".replace(" ", "_")}
        for name in _MOCK_TREE.get(rel, [])
    ]
