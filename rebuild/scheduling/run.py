"""Running one due schedule: build the report(s), scope them, email them."""

# === What's in this file ===
# When the poller decides a schedule is due it drops a schedule.run job; this is
# the code that job runs. It turns one schedule into a list of "deliveries" (who
# gets what slice of the data), then for each delivery it builds the report
# scoped to that slice, makes the Excel file, and emails it. Every send is
# audited. If it's Shabbos/Yom Tov and the schedule opted to skip, nothing goes
# out. A schedule fires at most once per day either way (the cadence's
# once-per-day guard plus stamping last_run_at after the attempt).
#
# Delivery -- one (scope, recipients, reply-to) target built from a schedule
# expand_deliveries() -- turn a schedule into its list of deliveries
# run_schedule() -- build + email every delivery for one schedule, then stamp it
# schedule_run_handler() -- the worker job entry point (reads schedule_id, runs it)

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ..auth.authorization import build_principal
from ..data.repositories.run_log import RunLogRepository
from ..data.repositories.schedules import KIND_MASTER, KIND_SELF, Schedule, SchedulesRepository
from ..data.repositories.user_scope import UserScopeRepository
from ..delivery.report_email import EmailService
from ..reporting.authz import resolve_access
from ..reports import export as export_file
from ..reports.runner import build_report_snapshot
from ..reports.views import result_tab
from .sabbath import melacha_assur

log = logging.getLogger("rebuild.scheduling.run")

_SCOPE_PREFIX = "sm:"


@dataclass(frozen=True)
class Delivery:
    scope_token: str
    recipients: list[str]
    reply_to: str
    label: str  # extra subject text, e.g. "salesman 42"


def expand_deliveries(schedule: Schedule, user_scope: UserScopeRepository, config) -> list[Delivery]:
    """Turn a schedule into the concrete sends it produces.

    A 'self' schedule is one send scoped to the owner. A 'master' schedule is one
    send per salesman number, each scoped to that number and addressed to the
    people mapped to it (plus any extra recipients the admin listed).
    """
    extra = list(schedule.recipients)
    if schedule.kind == KIND_SELF:
        owner = build_principal(config, schedule.owner_email, "")
        access = resolve_access(owner, schedule.report_key, user_scope)
        if not access.allowed:
            return []
        recipients = _dedupe([schedule.owner_email, *extra])
        return [Delivery(access.scope_token, recipients, schedule.owner_email, "")]

    if schedule.kind == KIND_MASTER:
        deliveries: list[Delivery] = []
        for number in schedule.salesmen:
            recipients = _dedupe([*user_scope.emails_for_salesman(number), *extra])
            if not recipients:
                continue  # nobody to send this salesman's slice to
            deliveries.append(
                Delivery(_SCOPE_PREFIX + number, recipients, schedule.owner_email, f"salesman {number}")
            )
        return deliveries

    return []


def run_schedule(db, config, schedule_id: str, *, now=None) -> None:
    schedules = SchedulesRepository(db)
    schedule = schedules.get(schedule_id)
    if schedule is None or not schedule.enabled:
        return

    run_log = RunLogRepository(db)
    if schedule.skip_sabbath:
        assur, reason = melacha_assur(now)
        if assur:
            run_log.record(
                "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
                status="skipped", message=f"{schedule.title}: skipped ({reason})",
            )
            schedules.mark_ran(schedule_id)
            return

    deliveries = expand_deliveries(schedule, UserScopeRepository(db), config)
    if not deliveries:
        run_log.record(
            "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
            status="skipped", message=f"{schedule.title}: nobody to send to / no access",
        )
        schedules.mark_ran(schedule_id)
        return

    email = EmailService(config, run_log)
    for delivery in deliveries:
        _deliver_one(db, config, schedule, delivery, email, run_log)

    # Stamp it whether sends succeeded or not so a schedule fires at most once a
    # day. A failed send shows in the audit log; the owner can re-run by hand.
    schedules.mark_ran(schedule_id)


def schedule_run_handler(ctx) -> Optional[str]:
    schedule_id = (ctx.job.params or {}).get("schedule_id")
    if not schedule_id:
        return None
    run_schedule(ctx.db, ctx.config, schedule_id)
    return None


def _deliver_one(db, config, schedule: Schedule, delivery: Delivery, email: EmailService, run_log: RunLogRepository) -> None:
    try:
        snapshot = build_report_snapshot(
            db, config, schedule.report_key, schedule.filters, delivery.scope_token,
            requested_by=schedule.owner_email,
        )
    except Exception as exc:  # noqa: BLE001 - one delivery failing shouldn't stop the rest
        log.exception("schedule %s: building report failed", schedule.id)
        run_log.record(
            "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
            status="failed", message=f"{schedule.title} ({delivery.label or 'self'}): {exc}",
        )
        return

    if snapshot is None:
        return

    tab = _pick_tab(snapshot, schedule.tab_key)
    if tab is None:
        run_log.record(
            "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
            status="failed", message=f"{schedule.title}: report has no tab to send",
        )
        return

    subtitle = " - ".join(part for part in (tab.get("label") or "", delivery.label) if part)
    result = email.send_report(
        to=delivery.recipients,
        report_key=schedule.report_key,
        report_title=snapshot.get("title") or schedule.report_key,
        subtitle=subtitle,
        xlsx_bytes=export_file.to_xlsx(tab),
        xlsx_filename=export_file.filename_for(schedule.report_key, tab["key"], "xlsx"),
        reply_to=delivery.reply_to,
        requested_by=schedule.owner_email,
    )
    # The email layer logs its own "report.email" entry; this "schedule.run" entry
    # is the schedule's own history line (so the page shows successes too, not just
    # skips and build failures).
    who = delivery.label or "self"
    if result.ok:
        run_log.record(
            "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
            status="sent", message=f"{schedule.title} ({who}): to {len(delivery.recipients)} recipient(s)",
        )
    else:
        run_log.record(
            "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
            status="failed", message=f"{schedule.title} ({who}): {result.error}",
        )


def _pick_tab(snapshot: dict, tab_key: Optional[str]) -> Optional[dict]:
    if tab_key:
        tab = result_tab(snapshot, tab_key)
        if tab is not None:
            return tab
    tabs = snapshot.get("tabs", [])
    return dict(tabs[0]) if tabs else None


def _dedupe(emails: list[str]) -> list[str]:
    seen: list[str] = []
    for raw in emails:
        email = (raw or "").strip().lower()
        if email and email not in seen:
            seen.append(email)
    return seen
