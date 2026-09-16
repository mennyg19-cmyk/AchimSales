"""Daily digest of silent view workbook parity scores."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from web.data.repositories.app_settings import AppSettingsRepository
from web.delivery.workbook_parity import (
    ViewWorkbookParityRepository,
    format_digest,
)


def _day_end_utc(day: str) -> str:
    from web.delivery.workbook_parity import _eastern_day_end_utc_iso
    return _eastern_day_end_utc_iso(day)

log = logging.getLogger(__name__)
EASTERN = ZoneInfo("America/New_York")


def send_parity_digest(*, db, email_service, settings: AppSettingsRepository | None = None,
                       day: str | None = None) -> str:
    """Email undigested scores through yesterday (or ``day``). Idempotent when empty.

    Includes older undigested rows so a failed mail day is not lost forever.
    """
    settings = settings or AppSettingsRepository(db)
    if not settings.view_workbook_parity_enabled():
        return "parity off"
    today = datetime.now(EASTERN).date()
    day = day or (today - timedelta(days=1)).isoformat()
    repo = ViewWorkbookParityRepository(db)
    rows = repo.undigested_before(_day_end_utc(day))
    if settings.view_parity_digest_sent_day() == day and not rows:
        return f"already sent {day}"
    recipients = settings.view_parity_digest_emails()
    if not recipients:
        return "no digest recipients"
    subject, body = format_digest(day, rows)
    result = email_service.deliver(
        subject=subject,
        recipients_raw="; ".join(recipients),
        body_text=body,
        report_name="View workbook parity",
        filename="",
        xlsx_bytes=None,
    )
    if not result.ok:
        raise RuntimeError(result.error or "parity digest mail failed")
    repo.mark_digested([int(r["id"]) for r in rows], day)
    settings.set_view_parity_digest_sent_day(day)
    log.info("view parity digest sent for %s to %s (%d rows)",
             day, recipients, len(rows))
    return f"sent {day} rows={len(rows)}"


def make_parity_digest_tick(db, email_service):
    """No-arg callable for APScheduler (Eastern 7:05)."""

    def _tick():
        try:
            send_parity_digest(db=db, email_service=email_service)
        except Exception:  # noqa: BLE001 - never kill the scheduler
            log.exception("view parity digest tick failed")

    return _tick
