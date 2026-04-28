"""Email 'outbox' for the test sandbox.

Instead of hitting SMTP, we compose a full RFC 822 message (with the xlsx
as an attachment) and drop it into ``test/outbox/`` as ``.eml``. The file
name is timestamped and safe to open in Outlook / Mail.app / a browser's
download preview, so the user can inspect exactly what the live app would
have sent.

A row is also inserted into the ``outbox`` SQLite table so we can surface
a small "Sent preview" page later.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from test.config.settings import OUTBOX_DIR
from test.webapp.db import connect

log = logging.getLogger(__name__)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _split_recipients(raw: str) -> list[str]:
    parts = [x.strip() for x in re.split(r"[,;]", raw or "") if x.strip()]
    return [p for p in parts if _EMAIL_RE.match(p)]


def _safe_slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (s or "").strip())[:40] or "msg"


def send_report_email(
    *,
    sender_email: str,
    recipients_raw: str,
    subject: str,
    report_key: str,
    report_name: str,
    xlsx_bytes: bytes,
    filename: str,
    sharepoint_path: str | None = None,
) -> dict:
    """Build + persist the email. Returns an info dict for the caller.

    On validation failure we return ``{"ok": False, "error": "..."}`` so the
    endpoint can surface a useful message without raising.

    If ``sharepoint_path`` is given, the workbook is also uploaded to the
    specified SharePoint folder (relative to the Direct Reports root) and
    the outbox row records the save.
    """
    recipients = _split_recipients(recipients_raw)
    if not recipients:
        return {"ok": False, "error": "No valid recipients."}

    sender_email = (sender_email or "test-sandbox@local").strip() or "test-sandbox@local"

    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = ", ".join(recipients)
    msg["X-Test-Sandbox"] = "yes"
    msg["X-Report-Key"] = report_key
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    body_text = (
        f"{report_name}\n"
        f"{'=' * len(report_name)}\n\n"
        f"This message was generated from the TEST sandbox.\n"
        f"See the attached workbook: {filename}\n"
    )
    msg.set_content(body_text)

    msg.add_attachment(
        xlsx_bytes,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    eml_name = f"{ts}_{_safe_slug(report_key)}_{_safe_slug(sender_email)}.eml"
    eml_path = OUTBOX_DIR / eml_name
    eml_path.write_bytes(bytes(msg))

    sharepoint_saved = False
    sharepoint_web_url: str | None = None
    sharepoint_error: str | None = None
    if sharepoint_path:
        try:
            from test.webapp.services.sharepoint import upload_file
            result = upload_file(sharepoint_path, filename, xlsx_bytes)
            sharepoint_saved = True
            sharepoint_web_url = result.get("webUrl")
            log.info("outbox: uploaded %s to SharePoint %s", filename, sharepoint_path)
        except Exception as e:
            sharepoint_error = str(e)
            log.exception("outbox: SharePoint upload failed")

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO outbox
                (user_email, report_key, report_name, subject, recipients, eml_path,
                 sharepoint_saved, sharepoint_path, created_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sender_email.lower(), report_key, report_name, subject,
             ", ".join(recipients), str(eml_path),
             1 if sharepoint_saved else 0, sharepoint_path if sharepoint_saved else None,
             now_iso),
        )

    log.info("outbox: wrote %s for %s", eml_path.name, recipients)

    return {
        "ok":                 True,
        "recipients_count":   len(recipients),
        "eml_path":           str(eml_path),
        "eml_name":           eml_name,
        "sharepoint_saved":   sharepoint_saved,
        "sharepoint_url":     sharepoint_web_url,
        "sharepoint_error":   sharepoint_error,
        "created_utc":        now_iso,
    }
