"""Periodic tick: scan active schedules and enqueue the ones that are due.

Runs once a minute on the single B1 instance (via the APScheduler wrapper). It
never delivers inline - it only enqueues durable ``schedule.run`` jobs, which the
worker drains. ``schedule.run`` enqueue is deduped per (type, id), and cadence's
once-per-day guard means a minute-by-minute tick can't double-fire a schedule.

Clock runs skip Shabbos/Yom Tov (Hebcal, Brooklyn). A skipped send waits for
the next scheduled HH:MM — skip-class periods use the next regular slot;
reschedule-class periods use the next weekday so a Friday 10pm skip runs
Monday 10pm, not motzei Shabbos. A manual Send now ignores that skip.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from web.data.repositories.jobs import JobRepository
from web.data.repositories.exports import ExportRepository
from web.reporting.cache import ReportCache
from web.data.repositories.schedules import (
    MASTER,
    PERSONAL,
    MasterScheduleRepository,
    ScheduleRepository,
    ScheduleRunRepository,
)
from web.scheduling import cadence as C
from web.scheduling.catchup import classify_action, makeup_due
from web.scheduling.jobs import enqueue_schedule_run
from web.scheduling.sabbath import melacha_assur, skip_sabbath_enabled

log = logging.getLogger(__name__)


def enqueue_due(db, job_repo: JobRepository, now: datetime | None = None) -> int:
    """Enqueue every active schedule that is due right now. Returns the count."""
    now = now or datetime.now(timezone.utc)
    sched_repo = ScheduleRepository(db)
    master_repo = MasterScheduleRepository(db)
    runs = ScheduleRunRepository(db)
    assur, reason = melacha_assur(now)
    enqueued = 0

    for s in sched_repo.list_active():
        if not _within_window(s, now):
            continue
        enqueued += _consider(
            job_repo, runs, sched_repo, s, PERSONAL, now, assur, reason,
            owner_user_id=s.owner_user_id,
        )

    for m in master_repo.list_active():
        enqueued += _consider(
            job_repo, runs, master_repo, m, MASTER, now, assur, reason,
            owner_user_id=None,
        )

    from web.ops.metrics import note_scheduler_tick
    note_scheduler_tick(due_enqueued=enqueued)
    return enqueued


def hold_until_next_slot(repo, runs: ScheduleRunRepository, sched,
                         schedule_type: str, now: datetime | None = None) -> bool:
    """If the next tick would fire this schedule, claim today instead.

    Turning a schedule On or saving an edit must wait for the next scheduled
    time. A schedule that was already On still catch-up-fires if the slot
    was missed (app down).
    """
    if not getattr(sched, "is_active", True):
        return False
    now = now or datetime.now(timezone.utc)
    last = C.later_iso(
        runs.last_run_at(sched.id, schedule_type),
        getattr(sched, "last_claimed_at", None),
    )
    if not C.due_now(sched.cadence, last, now):
        return False
    repo.claim_slot(sched.id, now.isoformat())
    return True


def make_tick(db, job_repo: JobRepository):
    """Build the no-arg callable APScheduler will fire each minute."""
    def tick() -> None:
        try:
            n = enqueue_due(db, job_repo)
            if n:
                log.info("schedule tick enqueued %d due schedule(s)", n)
        except Exception:  # noqa: BLE001 - a tick must never crash the scheduler
            log.exception("schedule tick failed")
        try:
            ReportCache(db).prune(6 * 3600)
            ExportRepository(db).prune()
            hung = job_repo.fail_hung(45 * 60)
            if hung:
                log.warning("hung-job cap failed %d running job(s)", hung)
        except Exception:  # noqa: BLE001 - reaper must not kill the tick
            log.exception("cache/export/hung-job reaper failed")

    return tick


def _consider(job_repo, runs, repo, sched, schedule_type: str, now: datetime,
              assur: bool, reason: str, *, owner_user_id: int | None) -> int:
    skip = skip_sabbath_enabled(getattr(sched, "params", None))
    last = C.later_iso(
        runs.last_run_at(sched.id, schedule_type),
        getattr(sched, "last_claimed_at", None),
    )
    due = C.due_now(sched.cadence, last, now)
    if skip and due and assur:
        run_id = runs.start(sched.id, schedule_type, started_at=now.isoformat())
        runs.finish(
            run_id, status="skipped",
            debug_log=f"Skipped ({reason or 'Shabbos'}); will run at the next scheduled time",
        )
        repo.set_catch_up(sched.id, True, for_date=C.eastern_date_iso(now))
        log.info("schedule %s:%s skipped (%s); owed at next scheduled time",
                 schedule_type, sched.id, reason or "Shabbos")
        return 0

    pending = bool(getattr(sched, "catch_up_pending", False))
    skipped_iso = getattr(sched, "catch_up_for_date", None)
    action = "skip"
    if pending and skipped_iso:
        try:
            skipped = date.fromisoformat(str(skipped_iso)[:10])
            action = classify_action(
                getattr(sched, "params", None), sched.report_key, skipped, sched.cadence,
            )
        except ValueError:
            action = "reschedule"

    makeup = pending and makeup_due(
        sched.cadence, last, now, action=action, assur=assur,
    )
    regular = due and not (skip and assur)
    if pending:
        weekday = now.astimezone(C.EASTERN).weekday() if now.tzinfo else now.weekday()
        # Never send the owed run on Saturday night (motzei Shabbos).
        # Reschedule-class waits until Monday; skip-class may use Sunday.
        if weekday == 5 or (action == "reschedule" and weekday >= 5):
            regular = False
    if not makeup and not regular:
        return 0
    enqueue_schedule_run(
        job_repo, schedule_id=sched.id, schedule_type=schedule_type,
        owner_user_id=owner_user_id,
        catch_up_for_date=skipped_iso if pending else None,
        include_regular=regular,
    )
    return 1


def _within_window(schedule, now: datetime) -> bool:
    """Honor a personal schedule's optional start/end date bounds (inclusive).

    Compared in US/Eastern (the cadence's business timezone), not UTC, so the
    window flips on the right business day."""
    today = C.eastern_date_iso(now)
    if schedule.start_date and today < schedule.start_date:
        return False
    if schedule.end_date and today > schedule.end_date:
        return False
    return True
