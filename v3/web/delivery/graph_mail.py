"""Send mail through Microsoft Graph (app-only), same path as live / rebuild.

No mailbox password — uses GRAPH_TENANT_ID / CLIENT_ID / CLIENT_SECRET already
on the App Service. Stdlib HTTP + msal (already a v3 dep).

`internetMessageId` and `Client-Request-Id` are tracing only. They do not make
Graph sendMail idempotent; delivery_legs status is what skips a second send.
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

from web.delivery.graph_token import GraphTokenCache, GraphTokenError

log = logging.getLogger(__name__)

_GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/users/{user}/sendMail"
_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_TIMEOUT_SECONDS = 60


def _retry_after_seconds(headers, attempt: int) -> float:
    raw = ""
    try:
        raw = headers.get("Retry-After") or headers.get("retry-after") or ""
    except Exception:  # noqa: BLE001
        raw = ""
    try:
        return min(60.0, float(raw))
    except (TypeError, ValueError):
        return min(30.0, float(2 ** attempt))


def _is_pre_submit_failure(exc: BaseException) -> bool:
    """DNS / refused = Graph never saw the body. Timeouts after submit are unknown."""
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, (ConnectionRefusedError, socket.gaierror)):
        return True
    if isinstance(exc, ConnectionRefusedError):
        return True
    text = str(reason or exc).lower()
    return "name or service not known" in text or "nodename nor servname" in text


class GraphMailError(RuntimeError):
    """Token failure or Graph rejected the send."""

    def __init__(self, message: str, status_code: int | None = None, detail: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class GraphUnknownError(GraphMailError):
    """Connection lost after the request was submitted; Graph may have accepted it."""


class GraphMailer:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str,
                 tokens: GraphTokenCache | None = None) -> None:
        self._tokens = tokens or GraphTokenCache(tenant_id, client_id, client_secret)

    def _token(self) -> str:
        try:
            return self._tokens.get()
        except GraphTokenError as exc:
            raise GraphMailError("Could not get a Microsoft Graph token to send mail.") from exc

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
        internet_message_id: str = "",
        client_request_id: str = "",
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
        if internet_message_id:
            # Tracing only — Graph sendMail is not idempotent on this header.
            mid = internet_message_id.strip()
            if mid and not mid.startswith("<"):
                mid = f"<{mid}@reports.achimonline.com>"
            message["internetMessageId"] = mid
        payload = json.dumps({"message": message, "saveToSentItems": True}).encode("utf-8")
        url = _GRAPH_SEND_URL.format(user=quote(sender, safe=""))
        last_exc: Exception | None = None
        token_retried = False
        for attempt in range(1, 4):
            try:
                headers = {
                    "Authorization": f"Bearer {self._token()}",
                    "Content-Type": "application/json",
                }
                if client_request_id:
                    # Tracing only; not a sendMail dedup key.
                    headers["Client-Request-Id"] = client_request_id
                request = urllib.request.Request(
                    url,
                    data=payload,
                    method="POST",
                    headers=headers,
                )
                with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                    response.read()
                log.info("Report email sent via Graph from %s to %s", sender, to)
                return
            except GraphUnknownError:
                raise
            except GraphMailError:
                raise
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:500]
                last_exc = GraphMailError(
                    f"Microsoft Graph rejected the send (HTTP {exc.code}).",
                    status_code=exc.code, detail=detail,
                )
                if exc.code == 401 and not token_retried:
                    token_retried = True
                    self._tokens.clear()
                    log.warning("Graph sendMail HTTP 401; clearing token and retrying once")
                    continue
                if exc.code in (429, 503) and attempt < 3:
                    from web.ops.metrics import note_graph_throttle
                    note_graph_throttle(exc.code)
                    delay = _retry_after_seconds(exc.headers, attempt)
                    log.warning("Graph sendMail HTTP %s; waiting %.0fs (Retry-After)",
                                exc.code, delay)
                    time.sleep(delay)
                    continue
                log.warning("Graph sendMail failed: HTTP %s %s", exc.code, detail)
                raise last_exc from exc
            except Exception as exc:  # noqa: BLE001
                if _is_pre_submit_failure(exc):
                    log.warning("Graph sendMail error: %s", exc)
                    raise GraphMailError(
                        "Microsoft Graph could not be reached to send mail."
                    ) from exc
                log.warning("Graph sendMail unknown after submit: %s", exc)
                raise GraphUnknownError(
                    "Connection lost after submitting mail to Microsoft Graph. "
                    "The message may already be in flight. Do not retry automatically."
                ) from exc
        if last_exc:
            raise last_exc
