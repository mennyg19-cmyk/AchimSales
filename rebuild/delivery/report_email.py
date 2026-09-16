"""Builds and sends the report email: Excel attached plus a link to open it."""

# === What's in this file ===
# Turns a finished report into an email. The body is short: a line about the
# report and a button/link to open it in the app. The Excel workbook is
# attached -- unless it's too big for a single Graph send, in which case we send
# a link-only version that says the file was too large to attach. The message
# always comes FROM the app's mailbox; Reply-To is the person who set up the
# send, so replies go to them.
#
# MAX_ATTACH_BYTES -- workbook size above which we switch to a link-only email
# report_view_url() -- the public URL that opens a report in the app
# ComposedEmail -- the finished subject + HTML body + attachments
# compose_report_email() -- build the message pieces (no network, easy to test)
# SendResult -- did it send, was the file attached, any error
# EmailService.send_report() -- compose, send via Graph, write an audit entry
# EmailService.send_failure_notice() -- tell the owner a scheduled run failed

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from typing import Optional

from ..config import Config
from ..data.repositories.run_log import RunLogRepository
from .graph_mail import Attachment, GraphMailer, GraphMailError

log = logging.getLogger("rebuild.delivery.email")

# A single Graph sendMail request tops out around 4 MB for the whole message,
# and base64 inflates bytes by about a third (so 3 MB raw -> ~4 MB encoded,
# before the rest of the JSON). Keep the raw workbook under 2.5 MB so the
# encoded message stays comfortably under the limit; bigger reports go out as a
# link instead of risking a rejected send.
MAX_ATTACH_BYTES = 2_500_000


def report_view_url(config: Config, report_key: str) -> str:
    """The link that opens a report in the app, or '' when no base URL is set."""
    if not config.public_base_url:
        return ""
    return f"{config.public_base_url}/reports/{report_key}"


@dataclass(frozen=True)
class ComposedEmail:
    subject: str
    html_body: str
    attachments: list[Attachment]
    attached: bool


def compose_report_email(
    *,
    report_title: str,
    subtitle: str,
    view_url: str,
    xlsx_bytes: bytes,
    xlsx_filename: str,
) -> ComposedEmail:
    subject = f"{report_title} - {subtitle}" if subtitle else report_title
    too_big = len(xlsx_bytes) >= MAX_ATTACH_BYTES

    safe_title = html.escape(report_title)
    safe_subtitle = html.escape(subtitle) if subtitle else ""
    parts = [f"<p>{safe_title}{(' - ' + safe_subtitle) if safe_subtitle else ''}</p>"]
    if view_url:
        safe_url = html.escape(view_url, quote=True)
        parts.append(f'<p><a href="{safe_url}">Open this report in the app</a></p>')
    if too_big:
        parts.append(
            "<p>The workbook was too large to attach to email. "
            "Use the link above to open and download it in the app.</p>"
        )
    else:
        parts.append(f"<p>The report is attached as <strong>{html.escape(xlsx_filename)}</strong>.</p>")

    attachments = [] if too_big else [Attachment(xlsx_filename, xlsx_bytes)]
    return ComposedEmail(subject, "\n".join(parts), attachments, attached=not too_big)


@dataclass(frozen=True)
class SendResult:
    ok: bool
    attached: bool = False
    error: str = ""


class EmailService:
    def __init__(self, config: Config, run_log: RunLogRepository, mailer: Optional[GraphMailer] = None) -> None:
        self._config = config
        self._run_log = run_log
        self._mailer = mailer or GraphMailer(config.tenant_id, config.client_id, config.client_secret)

    @property
    def configured(self) -> bool:
        return bool(self._config.mail_from and self._config.tenant_id and self._config.client_id and self._config.client_secret)

    def send_report(
        self,
        *,
        to: list[str],
        report_key: str,
        report_title: str,
        subtitle: str,
        xlsx_bytes: bytes,
        xlsx_filename: str,
        reply_to: Optional[str] = None,
        requested_by: Optional[str] = None,
    ) -> SendResult:
        if not self.configured:
            return self._fail(report_key, requested_by, "Email isn't set up on this server yet.")

        view_url = report_view_url(self._config, report_key)
        composed = compose_report_email(
            report_title=report_title,
            subtitle=subtitle,
            view_url=view_url,
            xlsx_bytes=xlsx_bytes,
            xlsx_filename=xlsx_filename,
        )
        # A link-only email with no link is useless: refuse rather than send one.
        if not composed.attached and not view_url:
            return self._fail(
                report_key, requested_by,
                "The report is too large to attach and no app link is configured to fall back to.",
            )
        try:
            self._mailer.send(
                sender=self._config.mail_from,
                to=to,
                subject=composed.subject,
                html_body=composed.html_body,
                reply_to=reply_to,
                attachments=composed.attachments,
            )
        except GraphMailError as exc:
            self._run_log.record(
                "report.email", user_email=requested_by, report_key=report_key,
                status="failed", message=str(exc),
            )
            return SendResult(False, error=str(exc))

        self._run_log.record(
            "report.email", user_email=requested_by, report_key=report_key, status="sent",
            message=f"to {len(to)} recipient(s); {'attached' if composed.attached else 'link-only (too big)'}",
        )
        return SendResult(True, attached=composed.attached)

    def send_failure_notice(
        self,
        *,
        to: str,
        report_key: str,
        schedule_title: str,
        reason: str,
    ) -> SendResult:
        """Email the schedule's owner that a scheduled run failed entirely.

        Short and plain: what failed, why, and a link to run it by hand. No
        attachment (there's no report to attach -- it failed). Audited like any
        other send so the history shows the heads-up went out.
        """
        if not self.configured:
            return self._fail(report_key, to, "Email isn't set up on this server yet.", action="schedule.fail_notice")

        safe_title = html.escape(schedule_title)
        safe_reason = html.escape(reason)
        parts = [
            f"<p>Your scheduled report <strong>{safe_title}</strong> didn't go out.</p>",
            f"<p>What went wrong: {safe_reason}</p>",
        ]
        view_url = report_view_url(self._config, report_key)
        if view_url:
            parts.append(f'<p><a href="{html.escape(view_url, quote=True)}">Open the report in the app to run it now</a></p>')
        try:
            self._mailer.send(
                sender=self._config.mail_from,
                to=[to],
                subject=f"Scheduled report didn't run: {schedule_title}",
                html_body="\n".join(parts),
            )
        except GraphMailError as exc:
            return self._fail(report_key, to, str(exc), action="schedule.fail_notice")

        self._run_log.record(
            "schedule.fail_notice", user_email=to, report_key=report_key, status="sent",
            message=f"failure heads-up for '{schedule_title}'",
        )
        return SendResult(True)

    def _fail(self, report_key: str, requested_by: Optional[str], error: str, action: str = "report.email") -> SendResult:
        # Every email attempt is auditable, including the ones we refuse before
        # ever calling Graph (not configured, or too big with no link).
        self._run_log.record(
            action, user_email=requested_by, report_key=report_key,
            status="failed", message=error,
        )
        return SendResult(False, error=error)
