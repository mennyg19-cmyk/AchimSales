"""Sends mail through Microsoft Graph using the company app's own identity."""

# === What's in this file ===
# The app sends report emails through Microsoft Graph with the same app-only
# mail permission the live distribution uses, so no mailbox password is needed.
# It always sends FROM one mailbox (e.g. reports@achimonline.com); Reply-To can
# be set to the person who scheduled the report, so replies reach them while the
# app stays the sender. Built on the standard library (plus msal for the token)
# to match the rest of the app -- no extra HTTP dependency.
#
# GraphMailError -- getting a token failed, or Graph rejected the send
# Attachment -- one file to attach (name + bytes + content type)
# GraphMailer.send() -- send one message via Graph

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

log = logging.getLogger("rebuild.delivery.graph")

_GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/users/{user}/sendMail"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_TIMEOUT_SECONDS = 60


class GraphMailError(RuntimeError):
    """Couldn't get a token, or Microsoft Graph rejected the send."""


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes
    content_type: str = _XLSX_CONTENT_TYPE


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
        except Exception as exc:  # noqa: BLE001 - any token failure becomes a clean error
            log.warning("Graph token acquisition raised: %s", exc)
            raise GraphMailError("Could not get a Microsoft Graph token to send mail.") from exc
        token = token_response.get("access_token")
        if not token:
            log.warning(
                "Graph token request failed: %s / %s",
                token_response.get("error"), token_response.get("error_description"),
            )
            raise GraphMailError("Could not get a Microsoft Graph token to send mail.")
        return token

    def send(
        self,
        *,
        sender: str,
        to: list[str],
        subject: str,
        html_body: str,
        reply_to: str | None = None,
        cc: list[str] | None = None,
        attachments: list[Attachment] | None = None,
    ) -> None:
        message: dict = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": _recipients(to),
        }
        if cc:
            message["ccRecipients"] = _recipients(cc)
        if reply_to:
            message["replyTo"] = _recipients([reply_to])
        if attachments:
            message["attachments"] = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": attachment.filename,
                    "contentType": attachment.content_type,
                    "contentBytes": base64.b64encode(attachment.content).decode("ascii"),
                }
                for attachment in attachments
            ]

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
        except Exception as exc:  # noqa: BLE001 - network errors become a clean error
            log.warning("Graph sendMail error: %s", exc)
            raise GraphMailError("Microsoft Graph could not be reached to send mail.") from exc
        log.info("Report email sent from %s to %s (reply_to=%s)", sender, to, reply_to or "")


def _recipients(addresses: list[str]) -> list[dict]:
    return [{"emailAddress": {"address": addr}} for addr in addresses]
