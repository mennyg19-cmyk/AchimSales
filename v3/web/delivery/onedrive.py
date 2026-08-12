"""Personal OneDrive delivery via Microsoft Graph (app-only client credentials).

Uploads go to ``/users/{user-email}/drive`` so overnight schedules can write into
that person's OneDrive without them being signed in. Needs Graph app permission
``Files.ReadWrite.All`` (admin consent once).

When Graph creds are missing, non-prod uses a mock folder tree (same idea as
SharePointService) so local schedule setup still works.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

from web.config import Config
from web.delivery.sharepoint import _validate_segments

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TIMEOUT = 30
UPLOAD_TIMEOUT = 120

_BAD_EMAIL = re.compile(r"[^a-zA-Z0-9._%+\-@]")

_MOCK_TREE: dict[str, list[str]] = {
    "": ["Documents", "Reports"],
    "Documents": ["Sales"],
    "Reports": ["Ordered", "Invoiced"],
}


class OneDriveService:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._token: str | None = None

    def is_configured(self) -> bool:
        return bool(self.cfg.tenant_id and self.cfg.client_id
                    and self.cfg.client_secret)

    def _mock_or_raise(self, what: str):
        if self.cfg.is_prod:
            raise RuntimeError(f"OneDrive is not configured (cannot {what})")
        return None

    def list_folders(self, user_email: str, rel_path: str = "") -> list[dict]:
        user = _user_key(user_email)
        if not self.is_configured():
            self._mock_or_raise("list folders")
            return _mock_folders(rel_path)
        import requests

        url = f"{self._drive_root(user)}:{self._enc_path(rel_path)}:/children"
        r = requests.get(url, headers=self._headers(), timeout=TIMEOUT)
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

    def upload_file(self, user_email: str, rel_folder: str, filename: str,
                    content: bytes) -> dict[str, Any]:
        user = _user_key(user_email)
        _validate_segments(rel_folder)
        _validate_segments(filename)
        if not self.is_configured():
            self._mock_or_raise("upload file")
            log.info("OneDrive mock: pretending to upload %s (%d bytes) to %s:%r",
                     filename, len(content), user, rel_folder)
            return {"webUrl": f"mock-od://{user}/{rel_folder}/{filename}",
                    "name": filename, "id": f"mock-od-{filename}", "mock": True}
        import requests

        self._ensure_folder(user, rel_folder)
        folder = self._enc_path(rel_folder)
        url = f"{self._drive_root(user)}:{folder}/{quote(filename)}:/content"
        r = requests.put(
            url,
            headers={**self._headers(), "Content-Type": "application/octet-stream"},
            data=content, timeout=UPLOAD_TIMEOUT,
        )
        if r.status_code not in (200, 201):
            r.raise_for_status()
        body = r.json()
        return {"webUrl": body.get("webUrl"), "name": body.get("name"), "id": body.get("id")}

    def _drive_root(self, user: str) -> str:
        return f"{GRAPH_BASE}/users/{quote(user)}/drive/root"

    def _enc_path(self, rel_path: str) -> str:
        segments = _validate_segments(rel_path)
        if not segments:
            return ""
        return "/" + "/".join(quote(s) for s in segments)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_token()}"}

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

    def _ensure_folder(self, user: str, rel_path: str) -> None:
        import requests

        segments = _validate_segments(rel_path)
        if not segments:
            return
        headers = {**self._headers(), "Content-Type": "application/json"}
        current_enc = ""
        for part in segments:
            parent = f"{self._drive_root(user)}:{current_enc}:/children" if current_enc else f"{self._drive_root(user)}/children"
            r = requests.post(parent, headers=headers, timeout=TIMEOUT, json={
                "name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"})
            if r.status_code not in (201, 409):
                r.raise_for_status()
            seg_enc = quote(part)
            current_enc = f"{current_enc}/{seg_enc}" if current_enc else f"/{seg_enc}"


def _user_key(email: str) -> str:
    e = (email or "").strip().lower()
    if not e or "@" not in e or _BAD_EMAIL.search(e):
        raise ValueError(f"invalid OneDrive user email: {email!r}")
    return e


def _mock_folders(rel_path: str) -> list[dict]:
    key = (rel_path or "").strip("/")
    names = _MOCK_TREE.get(key, [])
    return [{"name": n, "path": f"{key}/{n}".strip("/"), "id": f"mock-{n}"} for n in names]
