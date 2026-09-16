"""
Send report by email (Graph or SMTP).

Supports two methods (checked in order):

1. **Microsoft Graph** (recommended for business accounts; no app password needed)
   - Set AMAZON_EMAIL_FROM = the mailbox to send from (e.g. reports@company.com).
   - Uses same GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET as SharePoint.
   - App registration needs Mail.Send (application) and admin consent; then app can send as that mailbox.

2. **SMTP** (fallback)
   - Set SMTP_USER and SMTP_PASSWORD (and optionally SMTP_HOST, SMTP_PORT).

Recipients: AMAZON_EMAIL_RECIPIENTS (comma/semicolon list).
If AMAZON_EMAIL_RECIPIENTS is empty, send_report_email no-ops.
"""

import base64
import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote

from core.http import get_session, retry_call

from config.settings import (
    get_client_id,
    get_client_secret,
    get_email_recipients,
    get_graph_email_from,
    get_smtp_host,
    get_smtp_password,
    get_smtp_port,
    get_smtp_user,
    get_tenant_id,
)
from core.auth import get_graph_token

log = logging.getLogger(__name__)

GRAPH_SEND_MAIL_URL = "https://graph.microsoft.com/v1.0/users/{user_id}/sendMail"
GRAPH_TIMEOUT = 60


def _send_via_graph(
    from_address: str,
    to_list: list[str],
    subject: str,
    body: str,
    file_path: str | None,
    content_type: str = "Text",
    cc_list: list[str] | None = None,
    bcc_list: list[str] | None = None,
) -> None:
    """Send mail via Microsoft Graph API (client credentials; no user password)."""
    token = get_graph_token(get_tenant_id(), get_client_id(), get_client_secret())

    to_recipients = [{"emailAddress": {"address": addr}} for addr in to_list]
    message: dict = {
        "subject": subject,
        "body": {"contentType": content_type, "content": body},
        "toRecipients": to_recipients,
    }
    if cc_list:
        message["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc_list]
    if bcc_list:
        message["bccRecipients"] = [{"emailAddress": {"address": addr}} for addr in bcc_list]

    payload = {"message": message, "saveToSentItems": True}

    attachments = []
    if file_path and os.path.isfile(file_path):
        with open(file_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode("ascii")
        attachments.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": os.path.basename(file_path),
            "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "contentBytes": content_b64,
        })
    if attachments:
        message["attachments"] = attachments

    url = GRAPH_SEND_MAIL_URL.format(user_id=quote(from_address, safe=""))
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    session = get_session()
    resp = session.post(url, json=payload, headers=headers, timeout=GRAPH_TIMEOUT)
    resp.raise_for_status()
    log.info("Email sent via Graph to=%s cc=%s bcc=%s (from %s)",
             to_list, cc_list or [], bcc_list or [], from_address)


def _send_via_smtp(
    to_list: list[str],
    subject: str,
    body: str,
    file_path: str | None,
    cc_list: list[str] | None = None,
    bcc_list: list[str] | None = None,
) -> None:
    """Send mail via SMTP (Office 365 / Gmail / etc.) with 1 retry."""
    user = get_smtp_user()
    password = get_smtp_password()

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg.attach(MIMEText(body, "plain"))

    if file_path and os.path.isfile(file_path):
        with open(file_path, "rb") as f:
            part = MIMEApplication(f.read(), _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        part.add_header("Content-Disposition", "attachment", filename=os.path.basename(file_path))
        msg.attach(part)

    host = get_smtp_host()
    port = get_smtp_port()

    all_recipients = list(to_list) + (cc_list or []) + (bcc_list or [])

    def _do_send():
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, all_recipients, msg.as_string())

    retry_call(_do_send, retries=1, delay=2.0)
    log.info("Email sent via SMTP to=%s cc=%s bcc=%s", to_list, cc_list or [], bcc_list or [])


def send_report_email(
    file_path: str | None,
    subject: str,
    body: str,
    recipients: list[str] | None = None,
    content_type: str = "Text",
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> None:
    """Send an email with optional Excel attachment.

    Uses Microsoft Graph if AMAZON_EMAIL_FROM is set (and Graph credentials exist);
    otherwise uses SMTP if SMTP_USER and SMTP_PASSWORD are set.

    Args:
        file_path: Path to Excel file to attach; None = no attachment.
        subject: Email subject.
        body: Email body (plain text or HTML).
        recipients: Override; if None, uses AMAZON_EMAIL_RECIPIENTS from config.
        content_type: ``"Text"`` (default) or ``"HTML"``.
        cc: Optional list of CC email addresses.
        bcc: Optional list of BCC email addresses.
    """
    to_list = recipients if recipients is not None else get_email_recipients()
    if not to_list:
        log.info("Email skipped: no AMAZON_EMAIL_RECIPIENTS configured")
        return

    cc = cc or []
    bcc = bcc or []

    from_graph = get_graph_email_from()
    if from_graph and get_tenant_id() and get_client_id() and get_client_secret():
        try:
            _send_via_graph(from_graph, to_list, subject, body, file_path,
                            content_type=content_type, cc_list=cc, bcc_list=bcc)
            return
        except Exception:
            log.exception("Graph send failed, falling back to SMTP if configured")

    user = get_smtp_user()
    password = get_smtp_password()
    if user and password:
        _send_via_smtp(to_list, subject, body, file_path, cc_list=cc, bcc_list=bcc)
        return

    log.warning(
        "Email skipped: set AMAZON_EMAIL_FROM (and Graph credentials) for Graph, "
        "or SMTP_USER and SMTP_PASSWORD for SMTP"
    )


def send_multi_attachment_email(
    attachments: list[tuple[str, bytes]],
    subject: str,
    body: str,
    recipients: list[str],
    content_type: str = "Text",
    cc: list[str] | None = None,
) -> None:
    """Send an email with multiple in-memory file attachments.

    Args:
        attachments: List of (filename, content_bytes) tuples.
        subject: Email subject.
        body: Email body.
        recipients: List of To addresses.
        content_type: ``"Text"`` or ``"HTML"``.
        cc: Optional CC addresses.
    """
    if not recipients:
        log.info("Multi-attachment email skipped: no recipients")
        return

    cc = cc or []

    from_graph = get_graph_email_from()
    tenant = get_tenant_id()
    client = get_client_id()
    secret = get_client_secret()

    if from_graph and tenant and client and secret:
        try:
            _send_multi_via_graph(from_graph, recipients, subject, body,
                                 attachments, content_type=content_type, cc_list=cc)
            return
        except Exception:
            log.exception("Graph multi-send failed, falling back to SMTP if configured")

    user = get_smtp_user()
    password = get_smtp_password()
    if user and password:
        _send_multi_via_smtp(recipients, subject, body, attachments,
                             cc_list=cc)
        return

    raise RuntimeError(
        "No email provider configured. "
        f"EMAIL_FROM_ADDRESS={'set' if from_graph else 'MISSING'}, "
        f"GRAPH_TENANT_ID={'set' if tenant else 'MISSING'}, "
        f"GRAPH_CLIENT_ID={'set' if client else 'MISSING'}, "
        f"GRAPH_CLIENT_SECRET={'set' if secret else 'MISSING'}. "
        "Set EMAIL_FROM_ADDRESS (for Graph) or SMTP_USER + SMTP_PASSWORD (for SMTP) in Azure App Service settings."
    )


def _send_multi_via_graph(
    from_address: str,
    to_list: list[str],
    subject: str,
    body: str,
    attachments: list[tuple[str, bytes]],
    content_type: str = "Text",
    cc_list: list[str] | None = None,
) -> None:
    token = get_graph_token(get_tenant_id(), get_client_id(), get_client_secret())
    message: dict = {
        "subject": subject,
        "body": {"contentType": content_type, "content": body},
        "toRecipients": [{"emailAddress": {"address": addr}} for addr in to_list],
    }
    if cc_list:
        message["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc_list]

    graph_attachments = []
    for filename, content_bytes in attachments:
        graph_attachments.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": filename,
            "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "contentBytes": base64.b64encode(content_bytes).decode("ascii"),
        })
    if graph_attachments:
        message["attachments"] = graph_attachments

    payload = {"message": message, "saveToSentItems": True}
    url = GRAPH_SEND_MAIL_URL.format(user_id=quote(from_address, safe=""))
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    session = get_session()
    resp = session.post(url, json=payload, headers=headers, timeout=GRAPH_TIMEOUT)
    resp.raise_for_status()
    log.info("Multi-attachment email sent via Graph to=%s cc=%s (%d files, from %s)",
             to_list, cc_list or [], len(attachments), from_address)


def _send_multi_via_smtp(
    to_list: list[str],
    subject: str,
    body: str,
    attachments: list[tuple[str, bytes]],
    cc_list: list[str] | None = None,
) -> None:
    user = get_smtp_user()
    password = get_smtp_password()

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg.attach(MIMEText(body, "plain"))

    for filename, content_bytes in attachments:
        part = MIMEApplication(content_bytes,
                               _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    host = get_smtp_host()
    port = get_smtp_port()
    all_recipients = list(to_list) + (cc_list or [])

    def _do_send():
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, all_recipients, msg.as_string())

    retry_call(_do_send, retries=1, delay=2.0)
    log.info("Multi-attachment email sent via SMTP to=%s cc=%s (%d files)",
             to_list, cc_list or [], len(attachments))
