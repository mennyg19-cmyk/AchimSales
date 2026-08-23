"""Periodic tick: scan active schedules and enqueue the ones that are due.

Runs once a minute on the single B1 instance (via the APScheduler wrapper). It
never delivers inline - it only enqueues durable ``schedule.run`` jobs, which the
worker drains. ``schedule.run`` enqueue is deduped per (type, id), and cadence's
once-per-day guard means a minute-by-minute tick can't double-fire a schedule.

Clock runs skip Shabbos/Yom Tov (Hebcal, Brooklyn) and flag a catch-up that
fires after havdalah. A manual Run now ignores that skip.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from web.data.repositories.jobs import JobRepository
from web.data.repositories.schedules import (
    MASTER,
    PERSONAL,
    MasterScheduleRepository,
    ScheduleRepository,
    ScheduleRunRepository,
)
from web.scheduling import cadence as C
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

    return tick


def _consider(job_repo, runs, repo, sched, schedule_type: str, now: datetime,
              assur: bool, reason: str, *, owner_user_id: int | None) -> int:
    skip = skip_sabbath_enabled(getattr(sched, "params", None))
    if getattr(sched, "catch_up_pending", False) and not assur:
        repo.set_catch_up(sched.id, False)
        enqueue_schedule_run(
            job_repo, schedule_id=sched.id, schedule_type=schedule_type,
            owner_user_id=owner_user_id,
        )
        return 1
    last = C.later_iso(
        runs.last_run_at(sched.id, schedule_type),
        getattr(sched, "last_claimed_at", None),
    )
    if not C.due_now(sched.cadence, last, now):
        return 0
    if skip and assur:
        run_id = runs.start(sched.id, schedule_type)
        runs.finish(
            run_id, status="skipped",
            debug_log=f"Skipped ({reason or 'Shabbos'}); will run after Shabbos",
        )
        repo.set_catch_up(sched.id, True)
        log.info("schedule %s:%s skipped (%s); catch-up after havdalah",
                 schedule_type, sched.id, reason or "Shabbos")
        return 0
    if getattr(sched, "catch_up_pending", False):
        repo.set_catch_up(sched.id, False)
    enqueue_schedule_run(
        job_repo, schedule_id=sched.id, schedule_type=schedule_type,
        owner_user_id=owner_user_id,
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
