"""
Alert helper for runbook failure / warning notifications.

Sends alert emails to ``ALERT_RECIPIENTS`` via the same
Graph/SMTP infrastructure used by ``email_report``.  Falls back to
logging when email configuration is unavailable.
"""

import logging

log = logging.getLogger(__name__)


def send_alert(subject: str, body: str, content_type: str = "Text") -> None:
    """Send an alert email to the configured alert recipients.

    ``content_type`` can be ``"Text"`` (default) or ``"HTML"``.

    If email is not configured, the alert is logged at WARNING level
    so it still appears in Azure Automation output / log files.
    """
    try:
        from config.settings import get_alert_recipients
        recipients = get_alert_recipients()
    except Exception:
        recipients = []

    if not recipients:
        log.warning("ALERT (no recipients configured) -- %s: %s", subject, body)
        return

    try:
        from core.email_report import send_report_email
        send_report_email(
            file_path=None, subject=subject, body=body,
            recipients=recipients, content_type=content_type,
        )
        log.info("Alert sent to %s: %s", recipients, subject)
    except Exception:
        log.exception("Failed to send alert email -- %s: %s", subject, body)
