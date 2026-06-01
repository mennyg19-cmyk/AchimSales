"""Periodic tick: scan active schedules and enqueue the ones that are due.

Runs once a minute on the single B1 instance (via the APScheduler wrapper). It
never delivers inline - it only enqueues durable ``schedule.run`` jobs, which the
worker drains. ``schedule.run`` enqueue is deduped per (type, id), and cadence's
once-per-day guard means a minute-by-minute tick can't double-fire a schedule.
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

log = logging.getLogger(__name__)


def enqueue_due(db, job_repo: JobRepository, now: datetime | None = None) -> int:
    """Enqueue every active schedule that is due right now. Returns the count."""
    now = now or datetime.now(timezone.utc)
    sched_repo = ScheduleRepository(db)
    master_repo = MasterScheduleRepository(db)
    runs = ScheduleRunRepository(db)
    enqueued = 0

    for s in sched_repo.list_active():
        if not _within_window(s, now):
            continue
        if C.due_now(s.cadence, runs.last_run_at(s.id, PERSONAL), now):
            enqueue_schedule_run(job_repo, schedule_id=s.id, schedule_type=PERSONAL,
                                 owner_user_id=s.owner_user_id)
            enqueued += 1

    for m in master_repo.list_active():
        if C.due_now(m.cadence, runs.last_run_at(m.id, MASTER), now):
            enqueue_schedule_run(job_repo, schedule_id=m.id, schedule_type=MASTER)
            enqueued += 1

    return enqueued


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
