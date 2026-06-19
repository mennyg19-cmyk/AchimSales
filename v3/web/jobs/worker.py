"""Bounded in-process worker draining the durable job table.

Capacity is bounded by a semaphore so we never mark more jobs `running` than we
can actually execute on a 1-vCPU B1. The poller claims a job only after acquiring
capacity, runs the registered handler, and records success/failure in the DB.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from web.data.connection import Database
from web.data.repositories.jobs import Job, JobRepository

log = logging.getLogger(__name__)


@dataclass
class JobContext:
    """Passed to a handler. `set_progress` writes through to the durable table."""
    job: Job
    _repo: JobRepository

    def set_progress(self, pct: int) -> None:
        self._repo.set_progress(self.job.id, pct)


# A handler runs the work and returns a result_ref (e.g. a cache key), or "".
Handler = Callable[[JobContext], str]


class JobWorker:
    def __init__(self, db: Database, max_workers: int = 2):
        self.repo = JobRepository(db)
        self.max_workers = max(1, max_workers)
        self.handlers: dict[str, Handler] = {}
        self._sem = threading.BoundedSemaphore(self.max_workers)
        self._stop = threading.Event()
        self._executor: ThreadPoolExecutor | None = None
        self._poller: threading.Thread | None = None

    def register(self, job_type: str, handler: Handler) -> None:
        self.handlers[job_type] = handler

    @property
    def running(self) -> bool:
        """True once the background poller thread is started (see start())."""
        return self._poller is not None

    def health(self) -> dict:
        """Live snapshot of the poller for the admin diagnostic. Lets us tell a
        worker that never started from one whose poller thread died from one
        that's wedged with every capacity slot held by a hung handler. Only the
        background-leader process actually runs a poller; on a follower this
        reports started=False (which is correct for that process)."""
        return {
            "started": self._poller is not None,
            "poller_alive": bool(self._poller and self._poller.is_alive()),
            "max_workers": self.max_workers,
            "free_slots": self._sem._value,  # how many jobs it could claim right now
            "handler_types": sorted(self.handlers),
        }

    # --- synchronous driving (used by tests + simple call sites) -----------

    def process_next(self) -> str | None:
        """Claim and run a single job inline. Returns the job id or None."""
        job = self.repo.claim_next()
        if job is None:
            return None
        self._run(job)
        return job.id

    def drain(self, limit: int = 1000) -> int:
        """Run queued jobs inline until empty or `limit` reached. Returns count."""
        count = 0
        while count < limit and self.process_next() is not None:
            count += 1
        return count

    def _run(self, job: Job) -> None:
        handler = self.handlers.get(job.type)
        if handler is None:
            self.repo.mark_failure(job.id, f"no handler for job type {job.type!r}")
            return
        try:
            result_ref = handler(JobContext(job, self.repo)) or ""
            self.repo.mark_success(job.id, result_ref)
        except Exception as exc:  # noqa: BLE001 - record failure, keep worker alive
            log.exception("job %s (%s) failed", job.id, job.type)
            self.repo.mark_failure(job.id, str(exc))

    # --- background lifecycle ----------------------------------------------

    def start(self, poll_interval: float = 1.0) -> None:
        if self._poller is not None:
            return
        # Recover jobs orphaned in 'running' by a previous crash/restart before we
        # begin claiming new ones (plan section 10: jobs survive a B1 restart).
        recovered = self.repo.recover_orphans()
        if recovered:
            log.info("recovered %d orphaned running job(s) on startup", recovered)
        self._stop.clear()
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="job")
        self._poller = threading.Thread(target=self._loop, args=(poll_interval,), daemon=True)
        self._poller.start()

    def _loop(self, poll_interval: float) -> None:
        while not self._stop.is_set():
            if not self._sem.acquire(timeout=poll_interval):
                continue
            try:
                job = self.repo.claim_next()
                if job is None:
                    self._sem.release()
                    self._stop.wait(poll_interval)
                    continue
                self._executor.submit(self._run_and_release, job)
            except Exception:  # noqa: BLE001 - infra error must not kill the poller
                log.exception("job poller iteration failed")
                self._sem.release()
                self._stop.wait(poll_interval)

    def _run_and_release(self, job: Job) -> None:
        try:
            self._run(job)
        finally:
            self._sem.release()

    def stop(self, wait: bool = True) -> None:
        self._stop.set()
        if self._poller is not None:
            self._poller.join(timeout=5)
            self._poller = None
        if self._executor is not None:
            self._executor.shutdown(wait=wait)
            self._executor = None
