"""Send mail through Microsoft Graph (app-only), same path as live / rebuild.

No mailbox password — uses GRAPH_TENANT_ID / CLIENT_ID / CLIENT_SECRET already
on the App Service. Stdlib HTTP + msal (already a v3 dep).
"""

from __future__ import annotations

import base64
import html
import json
import logging
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import quote

from web.delivery.graph_auth import GraphTokenCache, retry_after_seconds

log = logging.getLogger(__name__)

_GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/users/{user}/sendMail"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_TIMEOUT_SECONDS = 60


class GraphMailError(RuntimeError):
    """Graph send failure with its durable delivery classification."""

    def __init__(self, message: str, status_code: int | None = None, detail: str = "",
                 delivery_status: str = "failed"):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
        self.delivery_status = delivery_status


class GraphMailer:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_cache = GraphTokenCache()
        self._msal_app = None

    def _token(self) -> str:
        import msal

        try:
            if self._msal_app is None:
                self._msal_app = msal.ConfidentialClientApplication(
                    self._client_id,
                    authority=f"https://login.microsoftonline.com/{self._tenant_id}",
                    client_credential=self._client_secret,
                )
            return self._token_cache.get(
                lambda: self._msal_app.acquire_token_for_client(scopes=[_GRAPH_SCOPE])
            )
        except Exception as exc:  # noqa: BLE001
            raise GraphMailError("Could not get a Microsoft Graph token to send mail.") from exc

    def _clear_token(self) -> None:
        self._token_cache.clear()
        if self._msal_app is not None:
            self._msal_app.remove_tokens_for_client()

    def send(
        self,
        *,
        sender: str,
        to: list[str],
        subject: str,
        body_text: str,
        filename: str = "",
        xlsx_bytes: bytes | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        body_html: str | None = None,
    ) -> None:
        if body_html:
            html_body = body_html
        else:
            safe_body = html.escape(body_text or "")
            html_body = (
                "<pre style='font-family:inherit;white-space:pre-wrap'>"
                + safe_body + "</pre>"
            )
        message = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": addr}} for addr in to],
        }
        if filename and xlsx_bytes:
            message["attachments"] = [{
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename,
                "contentType": _XLSX_CONTENT_TYPE,
                "contentBytes": base64.b64encode(xlsx_bytes).decode("ascii"),
            }]
        if cc:
            message["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc]
        if bcc:
            message["bccRecipients"] = [{"emailAddress": {"address": addr}} for addr in bcc]
        payload = json.dumps({"message": message, "saveToSentItems": True}).encode("utf-8")
        url = _GRAPH_SEND_URL.format(user=quote(sender, safe=""))
        retried_401 = retried_throttle = False
        while True:
            request = urllib.request.Request(
                url, data=payload, method="POST",
                headers={"Authorization": f"Bearer {self._token()}",
                         "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                    response.read()
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 401 and not retried_401:
                    retried_401 = True
                    self._clear_token()
                    continue
                if exc.code in (429, 503) and not retried_throttle:
                    retried_throttle = True
                    time.sleep(retry_after_seconds(exc.headers.get("Retry-After")))
                    continue
                detail = exc.read().decode("utf-8", "replace")[:500]
                log.warning("Graph sendMail failed: HTTP %s %s", exc.code, detail)
                from web.jobs.trace import step as job_step
                job_step("email", f"sendMail HTTP {exc.code}: {detail[:200]}")
                raise GraphMailError(
                    f"Microsoft Graph rejected the send (HTTP {exc.code}).",
                    status_code=exc.code, detail=detail,
                ) from exc
            except (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionResetError, OSError) as exc:
                log.warning("Graph sendMail outcome is unknown after request: %s", exc)
                raise GraphMailError(
                    "Microsoft Graph connection failed after submitting the send; delivery is unknown.",
                    delivery_status="unknown",
                ) from exc
        from web.jobs.trace import step as job_step
        job_step("email", f"sendMail ok to {', '.join(to[:8])}")
        log.info("Report email sent via Graph from %s to %s", sender, to)
