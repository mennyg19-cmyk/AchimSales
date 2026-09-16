"""APScheduler wrapper for periodic work on the single B1 instance.

Thin and lazily-imported so importing this module never hard-requires APScheduler
(handy for unit tests). Exactly one instance owns the schedule, so no owner
election or distributed locks are needed.
"""

from __future__ import annotations

import logging
from typing import Callable

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, timezone: str = "America/New_York"):
        self._timezone = timezone
        self._scheduler = None  # apscheduler instance, created on start()
        self._pending: list[tuple[str, Callable, dict]] = []

    def add_cron(self, job_id: str, func: Callable, **cron_kwargs) -> None:
        """Register a cron job. Queued until start() if the scheduler isn't running."""
        self._pending.append((job_id, func, cron_kwargs))
        if self._scheduler is not None:
            self._add(job_id, func, cron_kwargs)

    def _add(self, job_id: str, func: Callable, cron_kwargs: dict) -> None:
        self._scheduler.add_job(
            func, trigger="cron", id=job_id, replace_existing=True, **cron_kwargs
        )

    def start(self) -> None:
        from apscheduler.schedulers.background import BackgroundScheduler

        if self._scheduler is not None:
            return
        # Explicit B1 operating contract for a process that may sleep/restart:
        # coalesce missed runs into one, allow a 5-min misfire grace, never run a
        # given job concurrently with itself.
        self._scheduler = BackgroundScheduler(
            timezone=self._timezone,
            job_defaults={"coalesce": True, "misfire_grace_time": 300, "max_instances": 1},
        )
        for job_id, func, cron_kwargs in self._pending:
            self._add(job_id, func, cron_kwargs)
        self._scheduler.start()
        log.info("scheduler started with %d job(s)", len(self._pending))

    def shutdown(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
