"""The minute tick that finds due schedules and queues them to run."""

# === What's in this file ===
# A small daemon thread that wakes about once a minute, looks at every enabled
# schedule, and queues a durable schedule.run job for any that are due. It never
# sends mail itself -- the worker drains the jobs. The job's dedup key is the
# schedule id plus today's Eastern date, so even if the tick fires many times
# before the job runs, a schedule is queued at most once per day.
#
# Two reasons a schedule gets queued:
#  1. its cadence says it's due now and it hasn't run today, OR
#  2. it was skipped earlier for Shabbos/Yom Tov and that's now over -- this is
#     the catch-up, so a Saturday-morning send goes out Saturday night instead
#     of waiting a whole week.
#
# enqueue_due() -- scan schedules once and queue the due ones (returns the count)
# SchedulePoller.start() / request_stop() -- run/stop the background tick

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from ..data.repositories.jobs import JobRepository
from ..data.repositories.schedules import SchedulesRepository
from ..jobs.types import JOB_SCHEDULE_RUN
from . import cadence as C
from .sabbath import melacha_assur

log = logging.getLogger("rebuild.scheduling.poller")

_TICK_SECONDS = 60


def enqueue_due(db, jobs: JobRepository, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    today = C.eastern_today_iso(now)
    schedules = SchedulesRepository(db)
    queued = 0
    for schedule in schedules.list_active():
        if C.due_now(schedule.cadence, schedule.last_run_at, now):
            jobs.enqueue(
                JOB_SCHEDULE_RUN,
                report_key=schedule.report_key,
                cache_key=f"schedule:{schedule.id}:{today}",
                params={"schedule_id": schedule.id},
                requested_by=schedule.owner_email,
            )
            # Stamp it as having fired today the moment it's safely queued. The job
            # is durable (a crash/restart still drains it), so claiming the day
            # here -- not after the send finishes -- is what stops a timed-out or
            # failed run from being re-queued every minute for the rest of the day.
            schedules.mark_ran(schedule.id, now.isoformat())
            queued += 1
        elif schedule.catch_up_pending and not melacha_assur(now)[0]:
            # Skipped earlier for Shabbos/Yom Tov and the day is now over: send the
            # catch-up. A separate dedup key from the normal slot lets it queue even
            # though the schedule already "ran" (was skipped) today. The run handler
            # clears the catch-up flag when it actually runs.
            jobs.enqueue(
                JOB_SCHEDULE_RUN,
                report_key=schedule.report_key,
                cache_key=f"schedule:{schedule.id}:{today}:catchup",
                params={"schedule_id": schedule.id},
                requested_by=schedule.owner_email,
            )
            queued += 1
    return queued


class SchedulePoller:
    def __init__(self, db, config) -> None:
        self._db = db
        self._jobs = JobRepository(db, config.job_queue_max, config.job_stale_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="schedule-poller", daemon=True)
        self._thread.start()
        log.info("schedule poller started (every %ds)", _TICK_SECONDS)

    def request_stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                count = enqueue_due(self._db, self._jobs)
                if count:
                    log.info("schedule poller queued %d due schedule(s)", count)
            except Exception:  # noqa: BLE001 - a bad tick must not kill the poller
                log.exception("schedule poller tick failed")
            self._stop.wait(_TICK_SECONDS)
