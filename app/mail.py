"""Microsoft Graph sendMail via stdlib urllib. No mailbox password."""

from __future__ import annotations

import base64
import html
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

import config

log = logging.getLogger(__name__)

_GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/users/{user}/sendMail"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_TIMEOUT_SECONDS = 60
MAX_GRAPH_ATTACH_BYTES = 2_500_000
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class GraphMailError(RuntimeError):
    """Token failure or Graph rejected the send."""

    def __init__(self, message: str, status_code: int | None = None, detail: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def split_recipients(raw: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[,;]", raw or "") if part.strip()]
    return [part for part in parts if _EMAIL_RE.match(part)]


class GraphMailer:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret

    def _token(self) -> str:
        url = _TOKEN_URL.format(tenant=urllib.parse.quote(self._tenant_id, safe=""))
        body = urllib.parse.urlencode(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": _GRAPH_SCOPE,
                "grant_type": "client_credentials",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
        except Exception as exc:
            raise GraphMailError("Could not get a Microsoft Graph token to send mail.") from exc
        token = payload.get("access_token") if isinstance(payload, dict) else None
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
        filename: str = "",
        xlsx_bytes: bytes | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        body_html: str | None = None,
    ) -> None:
        if not to:
            raise GraphMailError("Microsoft Graph send needs at least one To address.")
        if body_html:
            html_body = body_html
        else:
            safe_body = html.escape(body_text or "")
            html_body = (
                "<pre style='font-family:inherit;white-space:pre-wrap'>" + safe_body + "</pre>"
            )
        message: dict = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": addr}} for addr in to],
        }
        attach = filename and xlsx_bytes and len(xlsx_bytes) < MAX_GRAPH_ATTACH_BYTES
        if attach:
            message["attachments"] = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": filename,
                    "contentType": _XLSX_CONTENT_TYPE,
                    "contentBytes": base64.b64encode(xlsx_bytes).decode("ascii"),
                }
            ]
        if cc:
            message["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc]
        if bcc:
            message["bccRecipients"] = [{"emailAddress": {"address": addr}} for addr in bcc]
        payload = json.dumps({"message": message, "saveToSentItems": True}).encode("utf-8")
        url = _GRAPH_SEND_URL.format(user=urllib.parse.quote(sender, safe=""))
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
            raise GraphMailError(
                f"Microsoft Graph rejected the send (HTTP {exc.code}).",
                status_code=exc.code,
                detail=detail,
            ) from exc
        except Exception as exc:
            log.warning("Graph sendMail error: %s", exc)
            raise GraphMailError("Microsoft Graph could not be reached to send mail.") from exc
        log.info("Report email sent via Graph from %s to %s", sender, to)


def mailer() -> GraphMailer:
    return GraphMailer(
        config.graph_tenant(),
        config.graph_client_id(),
        config.graph_client_secret(),
    )
