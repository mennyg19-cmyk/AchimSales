"""Job types and the registry that maps each type to the code that runs it."""

# === What's in this file ===
# Adding a new kind of background job means registering a handler here, not
# editing the worker loop. A handler is a plain function that takes a JobContext
# and returns an optional "result reference" (e.g. the cache key of a stored
# report) which gets saved on the job row.
#
# JOB_REPORT_RUN etc. -- the known job-type names
# JobContext -- what a handler is given: the job, config, db, and a cancel check
# HandlerRegistry -- register(type, fn) / get(type); one shared `registry` instance

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..config import Config
from ..data.connection import Database
from ..data.repositories.jobs import Job, JobRepository

JOB_REPORT_RUN = "report.run"
JOB_REPORT_EXPORT = "report.export"
JOB_CACHE_CLEANUP = "maintenance.cache_cleanup"


@dataclass
class JobContext:
    job: Job
    config: Config
    db: Database
    jobs: JobRepository

    def cancelled(self) -> bool:
        """Handlers should check this between chunks and stop early if true."""
        return self.jobs.is_cancelled(self.job.id)


Handler = Callable[[JobContext], Optional[str]]


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, job_type: str, handler: Handler) -> None:
        self._handlers[job_type] = handler

    def get(self, job_type: str) -> Optional[Handler]:
        return self._handlers.get(job_type)


registry = HandlerRegistry()
