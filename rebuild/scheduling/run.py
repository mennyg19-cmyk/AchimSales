"""Running one due schedule: build the report(s), scope them, email them."""

# === What's in this file ===
# When the poller decides a schedule is due it drops a schedule.run job; this is
# the code that job runs. It turns one schedule into a list of "deliveries" (who
# gets what slice of the data), then for each delivery it builds the report
# scoped to that slice, makes the Excel file, and emails it. Every send is
# audited. If it's Shabbos/Yom Tov and the schedule opted to skip, nothing goes
# out NOW -- instead it's flagged to run as a catch-up the moment the day ends.
# A schedule fires at most once per day (the cadence's once-per-day guard plus
# stamping last_run_at after the attempt). If every delivery fails, the owner
# gets an immediate heads-up email, and for a private schedule an in-app message.
#
# Delivery -- one (scope, recipients, reply-to) target built from a schedule
# expand_deliveries() -- turn a schedule into its list of deliveries
# run_schedule() -- build + email every delivery for one schedule, then stamp it
# schedule_run_handler() -- the worker job entry point (reads schedule_id, runs it)
# _notify_failure() -- email the owner (+ in-app note) when a whole run failed

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ..auth.authorization import build_principal
from ..data.connection import dedupe_emails
from ..data.repositories.jobs import STATUS_RUNNING
from ..data.repositories.notifications import KIND_SCHEDULE_FAILED, NotificationsRepository
from ..data.repositories.run_log import RunLogRepository
from ..data.repositories.schedules import KIND_MASTER, KIND_SELF, Schedule, SchedulesRepository
from ..data.repositories.user_scope import UserScopeRepository
from ..delivery.report_email import EmailService
from ..reporting.authz import resolve_access, salesman_scope_token
from ..reports import export as export_file
from ..reports.runner import build_report_snapshot
from ..reports.views import result_tab
from .sabbath import melacha_assur

log = logging.getLogger("rebuild.scheduling.run")


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
        recipients = dedupe_emails([schedule.owner_email, *extra])
        return [Delivery(access.scope_token, recipients, schedule.owner_email, "")]

    if schedule.kind == KIND_MASTER:
        # A master schedule mails other people their salesman's data, so it may
        # only run while its owner is STILL privileged. If they've lost admin
        # rights since it was created, it sends nothing.
        if not build_principal(config, schedule.owner_email, "").is_privileged:
            return []
        deliveries: list[Delivery] = []
        for number in schedule.salesmen:
            recipients = dedupe_emails([*user_scope.emails_for_salesman(number), *extra])
            if not recipients:
                continue  # nobody to send this salesman's slice to
            deliveries.append(
                Delivery(salesman_scope_token([number]), recipients, schedule.owner_email, f"salesman {number}")
            )
        return deliveries

    return []


def run_schedule(db, config, schedule_id: str, *, now=None, should_continue=None, ignore_sabbath: bool = False) -> None:
    """Build and email a schedule's deliveries.

    ``should_continue`` is an optional check (the worker's "is this job still
    running?"). It's checked before each delivery and again right before each
    send, so if the job is cancelled or timed out the handler stops emailing
    instead of running on in a thread the worker can no longer kill.

    ``ignore_sabbath`` is set for a manual "run it now" press: the person asked
    for it on purpose, so we don't apply the Shabbos/Yom Tov skip.
    """
    keep_going = should_continue or (lambda: True)
    schedules = SchedulesRepository(db)
    schedule = schedules.get(schedule_id)
    if schedule is None or not schedule.enabled:
        return
    was_catch_up = schedule.catch_up_pending

    run_log = RunLogRepository(db)
    if schedule.skip_sabbath and not ignore_sabbath:
        assur, reason = melacha_assur(now)
        if assur:
            run_log.record(
                "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
                status="skipped", message=f"{schedule.title}: skipped ({reason}); will run after Shabbos",
            )
            schedules.mark_skipped_for_sabbath(schedule_id)
            return

    # The once-a-day "ran today" stamp is owned by the poller (it stamps the moment
    # the job is queued) and by the Shabbos-skip path above -- NOT here. Stamping
    # here would let a manual "run now" eat today's scheduled slot, and a run that
    # finishes after Eastern midnight would wrongly stamp tomorrow. Any owed
    # Shabbos catch-up is cleared only once we reach a terminal outcome below that
    # wasn't a cancellation -- so a cancelled/timed-out catch-up isn't lost.

    deliveries = expand_deliveries(schedule, UserScopeRepository(db), config)
    if not deliveries:
        run_log.record(
            "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
            status="skipped", message=f"{schedule.title}: nobody to send to / no access",
        )
        schedules.clear_catch_up(schedule_id)  # nobody to send to is a real, settled outcome
        return

    email = EmailService(config, run_log)
    attempted = 0
    errors: list[str] = []
    stopped = False
    for delivery in deliveries:
        if not keep_going():
            log.warning("schedule %s: job no longer running, stopping before remaining sends", schedule.id)
            stopped = True
            break
        error = _deliver_one(db, config, schedule, delivery, email, run_log, keep_going)
        if error is None:  # the job was cancelled mid-delivery, not a failure
            stopped = True
            break
        attempted += 1
        if error:
            errors.append(error)

    if stopped:
        # Cancelled/timed out before finishing. If this job was satisfying an owed
        # catch-up (the poller cleared the flag when it queued us), re-set it now
        # so the poller retries next tick instead of silently dropping the send.
        if was_catch_up:
            schedules.set_catch_up(schedule_id)
        return

    # We reached a settled outcome (sent, partly sent, or fully failed), so this run
    # is what any owed catch-up was waiting for -- clear it now.
    schedules.clear_catch_up(schedule_id)

    # "Failed entirely" = we tried at least one delivery and every one failed.
    # Tell the owner right away.
    if attempted and len(errors) == attempted:
        _notify_failure(db, schedule, email, errors[0])


def schedule_run_handler(ctx) -> Optional[str]:
    params = ctx.job.params or {}
    schedule_id = params.get("schedule_id")
    if not schedule_id:
        return None

    def still_running() -> bool:
        job = ctx.jobs.get(ctx.job.id)
        return job is not None and job.status == STATUS_RUNNING

    run_schedule(
        ctx.db, ctx.config, schedule_id,
        should_continue=still_running, ignore_sabbath=bool(params.get("manual")),
    )
    return None


def _notify_failure(db, schedule: Schedule, email: EmailService, reason: str) -> None:
    """A whole scheduled run failed: email the owner now, and for a private
    schedule leave an in-app message offering to run it by hand."""
    email.send_failure_notice(
        to=schedule.owner_email, report_key=schedule.report_key,
        schedule_title=schedule.title, reason=reason,
    )
    if schedule.kind == KIND_SELF:
        NotificationsRepository(db).create(
            user_email=schedule.owner_email, kind=KIND_SCHEDULE_FAILED,
            title=f"Scheduled report didn't run: {schedule.title}",
            body="We couldn't send it on schedule. You can run it now or dismiss this.",
            schedule_id=schedule.id,
        )


def _deliver_one(db, config, schedule: Schedule, delivery: Delivery, email: EmailService, run_log: RunLogRepository, keep_going) -> Optional[str]:
    """Build and send one delivery. Returns "" on success, an error reason on
    failure, or None if the job was cancelled mid-way (so the caller can tell a
    real failure apart from a deliberate stop)."""
    who = delivery.label or "self"
    try:
        snapshot = build_report_snapshot(
            db, config, schedule.report_key, schedule.filters, delivery.scope_token,
            requested_by=schedule.owner_email, cancelled=lambda: not keep_going(),
        )
    except Exception as exc:  # noqa: BLE001 - one delivery failing shouldn't stop the rest
        # A build that blew up because the job was already cancelled/timed out is a
        # stop, not a failure -- don't cry wolf with a failure alert.
        if not keep_going():
            return None
        log.exception("schedule %s: building report failed", schedule.id)
        run_log.record(
            "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
            status="failed", message=f"{schedule.title} ({who}): {exc}",
        )
        return str(exc)

    if snapshot is None:  # build_report_snapshot bailed because the job was cancelled
        return None

    tab = _pick_tab(snapshot, schedule.tab_key)
    if tab is None:
        run_log.record(
            "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
            status="failed", message=f"{schedule.title}: report has no tab to send",
        )
        return "the report had no tab to send"

    try:
        return _export_and_send(snapshot, tab, schedule, delivery, email, run_log, keep_going)
    except Exception as exc:  # noqa: BLE001 - export/send failure is per-delivery, not fatal
        if not keep_going():
            return None
        log.exception("schedule %s: export/send failed for %s", schedule.id, who)
        run_log.record(
            "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
            status="failed", message=f"{schedule.title} ({who}): {exc}",
        )
        return str(exc)


def _export_and_send(snapshot: dict, tab: dict, schedule: Schedule, delivery: Delivery, email: EmailService, run_log: RunLogRepository, keep_going) -> Optional[str]:
    """Build the workbook, gate on cancellation, then send. Returns "" on success,
    None if cancelled, or raises on unexpected error (caller catches)."""
    who = delivery.label or "self"
    if not keep_going():
        return None
    xlsx_bytes = export_file.to_xlsx(tab)
    if not keep_going():
        return None

    subtitle = " - ".join(part for part in (tab.get("label") or "", delivery.label) if part)
    send_result = email.send_report(
        to=delivery.recipients,
        report_key=schedule.report_key,
        report_title=snapshot.get("title") or schedule.report_key,
        subtitle=subtitle,
        xlsx_bytes=xlsx_bytes,
        xlsx_filename=export_file.filename_for(schedule.report_key, tab["key"], "xlsx"),
        reply_to=delivery.reply_to,
        requested_by=schedule.owner_email,
    )
    if send_result.ok:
        run_log.record(
            "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
            status="sent", message=f"{schedule.title} ({who}): to {len(delivery.recipients)} recipient(s)",
        )
        return ""
    if not keep_going():
        return None
    run_log.record(
        "schedule.run", user_email=schedule.owner_email, report_key=schedule.report_key,
        status="failed", message=f"{schedule.title} ({who}): {send_result.error}",
    )
    return send_result.error or "the email could not be sent"


def _pick_tab(snapshot: dict, tab_key: Optional[str]) -> Optional[dict]:
    if tab_key:
        tab = result_tab(snapshot, tab_key)
        if tab is not None:
            return tab
    tabs = snapshot.get("tabs", [])
    return dict(tabs[0]) if tabs else None
