"""Operator alert and reconcile for unknown Graph send outcomes."""

from __future__ import annotations

import logging

from web.data.repositories.app_settings import AppSettingsRepository
from web.data.repositories.notifications import NotificationRepository
from web.data.repositories.users import UserRepository
from web.delivery.states import UNKNOWN

log = logging.getLogger(__name__)

DELIVERY_UNKNOWN = "delivery_unknown"


def alert_unknown_delivery(db, settings: AppSettingsRepository, *, delivery,
                           subject: str, body: str,
                           attempt_key: str = "", run_id: int | None = None) -> None:
    emails = settings.test_emails()
    email = getattr(delivery, "email", None)
    send = getattr(email, "send_notice", None) if email is not None else None
    if send is not None and emails:
        try:
            text = body
            if attempt_key:
                text = (
                    f"{body}\n\nAttempt key: {attempt_key}\n"
                    "Open Schedules (unknown email-now) or History: mark "
                    "'I received it' if the mail arrived, or 'Send again' only "
                    "if it is missing."
                )
            send(to=emails, subject=subject, body_text=text)
        except Exception:  # noqa: BLE001 - never hide the original outcome
            log.exception("Could not send unknown-delivery notice")
    _notify_privileged(db, subject, body, attempt_key=attempt_key, run_id=run_id)


def alert_unknown_legs(db, legs) -> None:
    if not legs:
        return
    from web.data.repositories.app_settings import AppSettingsRepository
    settings = AppSettingsRepository(db)
    lines = []
    for leg in legs:
        lines.append(f"{leg.kind} {leg.target}: {leg.error or 'unknown'}")
    body = (
        "One or more email sends may already be in a mailbox. "
        "Do not retry automatically.\n\n"
        + "\n".join(lines)
        + "\n\nOpen the schedule History: mark 'I received it' if the mail "
        "arrived, or 'Send again' only if it is missing."
    )
    delivery = None
    try:
        from flask import current_app
        delivery = current_app.config.get("DELIVERY_SERVICE")
    except Exception:  # noqa: BLE001
        delivery = None
    alert_unknown_delivery(
        db, settings, delivery=delivery or type("D", (), {"email": None})(),
        subject="[UNKNOWN] scheduled send",
        body=body,
        attempt_key=legs[0].attempt_key if legs else "",
    )


def _notify_privileged(db, subject: str, body: str, *, attempt_key: str,
                       run_id: int | None) -> None:
    users = UserRepository(db)
    notifs = NotificationRepository(db)
    payload = {
        "title": subject,
        "message": body[:500],
        "attempt_key": attempt_key,
        "run_id": run_id,
    }
    for user in users.all_users():
        if user.role not in ("admin", "developer"):
            continue
        notifs.create(user.id, DELIVERY_UNKNOWN, payload)
