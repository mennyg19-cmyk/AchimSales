"""Email delivery: compose an RFC-822 message with the xlsx attached, persist a
``.eml`` artifact to the outbox dir, send via Microsoft Graph (preferred) or
SMTP when configured, optionally push the workbook to SharePoint, and log the
attempt to the ``outbox`` table.

When neither Graph nor SMTP is configured the ``.eml`` + outbox row are the
delivery record — nothing is silently dropped, but nothing reaches an inbox
either (that was the Friday “success with no email” failure mode).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from uuid import uuid4

from web.config import Config
from web.data.repositories.outbox import OutboxRepository
from web.delivery.graph_mail import GraphMailError, GraphMailer
from web.delivery.sharepoint import SharePointService

log = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_XLSX_MIME = "vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def split_recipients(raw: str) -> list[str]:
    parts = [x.strip() for x in re.split(r"[,;]", raw or "") if x.strip()]
    return [p for p in parts if _EMAIL_RE.match(p)]


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (s or "").strip())[:40] or "msg"


@dataclass
class DeliveryResult:
    ok: bool
    error: str = ""
    recipients: list[str] = field(default_factory=list)
    eml_name: str = ""
    # True when Graph or SMTP actually transmitted (legacy name kept for meta JSON).
    sent_via_smtp: bool = False
    # "graph" | "smtp" | "outbox" | "" (no email target)
    send_channel: str = ""
    sharepoint_saved: bool = False
    sharepoint_url: str | None = None
    sharepoint_error: str | None = None
    outbox_id: int | None = None


class EmailService:
    def __init__(self, cfg: Config, outbox: OutboxRepository, sharepoint: SharePointService,
                 graph: GraphMailer | None = None):
        self.cfg = cfg
        self.outbox = outbox
        self.sharepoint = sharepoint
        self._graph = graph

    def _graph_mailer(self) -> GraphMailer | None:
        if self._graph is not None:
            return self._graph
        if not (self.cfg.tenant_id and self.cfg.client_id and self.cfg.client_secret
                and self.cfg.email_from):
            return None
        return GraphMailer(self.cfg.tenant_id, self.cfg.client_id, self.cfg.client_secret)

    def deliver(self, *, subject: str, recipients_raw: str, body_text: str,
                report_name: str, filename: str, xlsx_bytes: bytes,
                sharepoint_path: str | None = None) -> DeliveryResult:
        recipients = split_recipients(recipients_raw)
        if not recipients and not sharepoint_path:
            return DeliveryResult(ok=False, error="No valid recipients.")

        msg = self._compose(subject, recipients, body_text, report_name, filename, xlsx_bytes)
        eml_name = self._write_eml(msg, report_name)
        body = body_text or f"{report_name}\n\nSee the attached workbook: {filename}\n"

        sent = False
        channel = ""
        if recipients:
            graph = self._graph_mailer()
            if graph is not None:
                try:
                    graph.send(
                        sender=self.cfg.email_from, to=recipients,
                        subject=subject or report_name, body_text=body,
                        filename=filename, xlsx_bytes=xlsx_bytes,
                    )
                    sent = True
                    channel = "graph"
                except GraphMailError as exc:
                    log.exception("Graph send failed")
                    return self._record(subject, recipients, filename, eml_name, sent=False,
                                        channel="", sp_path=sharepoint_path,
                                        error=f"Graph failed: {exc}")
            elif self.cfg.smtp_host:
                try:
                    self._smtp_send(msg, recipients)
                    sent = True
                    channel = "smtp"
                except Exception as exc:  # noqa: BLE001 - record, never crash the run
                    log.exception("SMTP send failed")
                    return self._record(subject, recipients, filename, eml_name, sent=False,
                                        channel="", sp_path=sharepoint_path,
                                        error=f"SMTP failed: {exc}")
            else:
                channel = "outbox"

        sp_saved, sp_url, sp_err = self._maybe_sharepoint(sharepoint_path, filename, xlsx_bytes)

        result = self._record(subject, recipients, filename, eml_name, sent=sent,
                              channel=channel, sp_path=sharepoint_path, sp_saved=sp_saved,
                              sp_url=sp_url, sp_error=sp_err)
        return result

    # -- internals ----------------------------------------------------------

    def _compose(self, subject, recipients, body_text, report_name, filename, xlsx_bytes):
        msg = EmailMessage()
        msg["Subject"] = subject or report_name
        msg["From"] = self.cfg.email_from
        msg["To"] = ", ".join(recipients) or self.cfg.email_from
        msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        msg.set_content(body_text or f"{report_name}\n\nSee the attached workbook: {filename}\n")
        msg.add_attachment(xlsx_bytes, maintype="application", subtype=_XLSX_MIME, filename=filename)
        return msg

    def _write_eml(self, msg: EmailMessage, report_name: str) -> str:
        self.cfg.outbox_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # Short random suffix so two sends of the same report within one second
        # don't collide and overwrite each other's .eml artifact.
        name = f"{ts}_{_slug(report_name)}_{uuid4().hex[:8]}.eml"
        (self.cfg.outbox_dir / name).write_bytes(bytes(msg))
        return name

    def _smtp_send(self, msg: EmailMessage, recipients: list[str]) -> None:
        import smtplib

        with smtplib.SMTP(self.cfg.smtp_host, self.cfg.smtp_port, timeout=30) as s:
            if self.cfg.smtp_starttls:
                s.starttls()
            if self.cfg.smtp_user:
                s.login(self.cfg.smtp_user, self.cfg.smtp_password)
            s.send_message(msg, from_addr=self.cfg.email_from, to_addrs=recipients)

    def _maybe_sharepoint(self, path, filename, xlsx_bytes):
        if not path:
            return False, None, None
        try:
            res = self.sharepoint.upload_file(path, filename, xlsx_bytes)
            return True, res.get("webUrl"), None
        except Exception as exc:  # noqa: BLE001
            log.exception("SharePoint upload failed")
            return False, None, str(exc)

    def _record(self, subject, recipients, filename, eml_name, *, sent, channel="",
                sp_path=None, sp_saved=False, sp_url=None, sp_error=None, error="") -> DeliveryResult:
        # "Success" means every REQUESTED target was actually delivered. An email
        # target is delivered when recipients exist and the send didn't hard-fail
        # (the .eml + outbox row is the delivery record when Graph/SMTP are
        # unconfigured). A requested SharePoint upload that failed makes the whole
        # delivery fail — otherwise a SharePoint-only send could look successful
        # while nothing was actually delivered.
        sp_requested = bool(sp_path)
        if not error and sp_requested and not sp_saved:
            error = sp_error or "SharePoint upload failed"
        email_delivered = bool(recipients) and not error
        ok = (email_delivered or sp_saved) and not error
        status = "sent" if (ok and sent) else ("outbox" if ok else "failed")
        if not channel and recipients and ok and not sent:
            channel = "outbox"
        outbox_id = self.outbox.enqueue(
            subject=subject, recipients=", ".join(recipients),
            attachment_meta={"filename": filename, "eml": eml_name},
            sharepoint_meta={"path": sp_path or "", "saved": sp_saved, "url": sp_url, "error": sp_error},
            status=status,
        )
        return DeliveryResult(
            ok=ok, error=error, recipients=recipients, eml_name=eml_name,
            sent_via_smtp=sent, send_channel=channel, sharepoint_saved=sp_saved,
            sharepoint_url=sp_url, sharepoint_error=sp_error, outbox_id=outbox_id,
        )
