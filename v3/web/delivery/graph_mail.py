"""Send mail through Microsoft Graph (app-only), same path as live / rebuild.

No mailbox password — uses GRAPH_TENANT_ID / CLIENT_ID / CLIENT_SECRET already
on the App Service. Stdlib HTTP + msal (already a v3 dep).
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from urllib.parse import quote

log = logging.getLogger(__name__)

_GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/users/{user}/sendMail"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_TIMEOUT_SECONDS = 60


class GraphMailError(RuntimeError):
    """Token failure or Graph rejected the send."""


class GraphMailer:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret

    def _token(self) -> str:
        import msal

        try:
            app = msal.ConfidentialClientApplication(
                self._client_id,
                authority=f"https://login.microsoftonline.com/{self._tenant_id}",
                client_credential=self._client_secret,
            )
            token_response = app.acquire_token_for_client(scopes=[_GRAPH_SCOPE])
        except Exception as exc:  # noqa: BLE001
            raise GraphMailError("Could not get a Microsoft Graph token to send mail.") from exc
        token = token_response.get("access_token")
        if not token:
            raise GraphMailError("Could not get a Microsoft Graph token to send mail.")
        return token

    def send(
        self,
        *,
        sender: str,
        to: list[str],
        subject: str,
        body_text: str,
        filename: str,
        xlsx_bytes: bytes,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> None:
        safe_body = (body_text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html_body = "<pre style='font-family:inherit;white-space:pre-wrap'>" + safe_body + "</pre>"
        message = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": addr}} for addr in to],
            "attachments": [{
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename,
                "contentType": _XLSX_CONTENT_TYPE,
                "contentBytes": base64.b64encode(xlsx_bytes).decode("ascii"),
            }],
        }
        if cc:
            message["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc]
        if bcc:
            message["bccRecipients"] = [{"emailAddress": {"address": addr}} for addr in bcc]
        payload = json.dumps({"message": message, "saveToSentItems": True}).encode("utf-8")
        url = _GRAPH_SEND_URL.format(user=quote(sender, safe=""))
        try:
            request = urllib.request.Request(
                url,
                data=payload,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self._token()}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                response.read()
        except GraphMailError:
            raise
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            log.warning("Graph sendMail failed: HTTP %s %s", exc.code, detail)
            raise GraphMailError(f"Microsoft Graph rejected the send (HTTP {exc.code}).") from exc
        except Exception as exc:  # noqa: BLE001
            log.warning("Graph sendMail error: %s", exc)
            raise GraphMailError("Microsoft Graph could not be reached to send mail.") from exc
        log.info("Report email sent via Graph from %s to %s", sender, to)
