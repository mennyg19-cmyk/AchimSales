"""Durable job worker with killable production child processes.

The synchronous helpers run in-process for focused unit tests. The production
poller runs every claimed handler in a child process so a timeout stops the work,
then records the outcome and releases its capacity slot.
"""

from __future__ import annotations

import logging
import multiprocessing
import threading
from dataclasses import dataclass
from queue import Empty
from time import monotonic
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
DEFAULT_MAX_WORKERS = 1
DEFAULT_JOB_TIMEOUT_SECONDS = 45 * 60
DEFAULT_QUEUE_MAX_DEPTH = 100
DEFAULT_QUEUE_MAX_AGE_SECONDS = 60 * 60


def _run_child(handler: Handler, job: Job, db: Database, outcomes) -> None:
    """Run a registered handler in the child and report its terminal outcome."""
    try:
        result_ref = handler(JobContext(job, JobRepository(db))) or ""
        outcomes.put(("success", result_ref))
    except BaseException as exc:  # noqa: BLE001 - never leave a row running after child exit
        outcomes.put(("failure", str(exc)))


class JobWorker:
    def __init__(
        self,
        db: Database,
        max_workers: int = DEFAULT_MAX_WORKERS,
        *,
        job_timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS,
        queue_max_depth: int = DEFAULT_QUEUE_MAX_DEPTH,
        queue_max_age_seconds: float = DEFAULT_QUEUE_MAX_AGE_SECONDS,
    ):
        self.db = db
        self.repo = JobRepository(db)
        self.max_workers = max(1, max_workers)
        self.job_timeout_seconds = max(1, job_timeout_seconds)
        self.queue_max_depth = max(1, queue_max_depth)
        self.queue_max_age_seconds = max(1, queue_max_age_seconds)
        self.handlers: dict[str, Handler] = {}
        self._sem = threading.BoundedSemaphore(self.max_workers)
        self._stop = threading.Event()
        self._poller: threading.Thread | None = None
        self._processes: dict[str, multiprocessing.Process] = {}
        self._processes_lock = threading.Lock()

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
            "job_timeout_seconds": self.job_timeout_seconds,
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

    def start(self, poll_interval: float = 1.0, heartbeat: Callable[[], None] | None = None) -> None:
        if self._poller is not None:
            return
        # Recover jobs orphaned in 'running' by a previous crash/restart before we
        # begin claiming new ones (plan section 10: jobs survive a B1 restart).
        recovered = self.repo.recover_orphans()
        if recovered:
            log.info("recovered %d orphaned running job(s) on startup", recovered)
        self._stop.clear()
        self._poller = threading.Thread(
            target=self._loop, args=(poll_interval, heartbeat), daemon=True
        )
        self._poller.start()

    def _loop(self, poll_interval: float, heartbeat: Callable[[], None] | None) -> None:
        # Heartbeat so the logs PROVE the poller is actually iterating (an alive
        # thread that isn't looping looks identical from the outside otherwise).
        # ~30s cadence at the default 1s poll: quiet enough to leave on in prod.
        heartbeat_every = max(1, int(30 / poll_interval))
        iterations = 0
        log.info("job poller loop entered (max_workers=%d, poll=%.1fs)", self.max_workers, poll_interval)
        while not self._stop.is_set():
            iterations += 1
            if iterations % heartbeat_every == 0:
                log.info("job poller heartbeat: iterations=%d free_slots=%d", iterations, self._sem._value)
                if heartbeat is not None:
                    try:
                        heartbeat()
                    except Exception:  # noqa: BLE001 - a status write cannot stop jobs
                        log.exception("job worker heartbeat write failed")
            if not self._sem.acquire(timeout=poll_interval):
                continue
            try:
                if not self.repo.queue_within_limits(
                    max_depth=self.queue_max_depth,
                    max_age_seconds=self.queue_max_age_seconds,
                ):
                    self._sem.release()
                    self._stop.wait(poll_interval)
                    continue
                job = self.repo.claim_next()
                if job is None:
                    self._sem.release()
                    self._stop.wait(poll_interval)
                    continue
                log.info("job poller claimed %s (%s)", job.id, job.type)
                self._start_child(job)
            except Exception:  # noqa: BLE001 - infra error must not kill the poller
                log.exception("job poller iteration failed")
                self._sem.release()
                self._stop.wait(poll_interval)
        log.warning("job poller loop exited (stop=%s)", self._stop.is_set())

    def _start_child(self, job: Job) -> None:
        handler = self.handlers.get(job.type)
        if handler is None:
            self.repo.mark_failure(job.id, f"no handler for job type {job.type!r}")
            self._sem.release()
            return
        # Azure App Service uses Linux. Fork preserves the already-registered
        # handlers without trying to pickle their application-bound closures.
        context = multiprocessing.get_context("fork")
        outcomes = context.Queue()
        process = context.Process(target=_run_child, args=(handler, job, self.db, outcomes))
        process.start()
        with self._processes_lock:
            self._processes[job.id] = process
        threading.Thread(
            target=self._await_child,
            args=(job, process, outcomes),
            name=f"job-monitor-{job.id[:8]}",
            daemon=True,
        ).start()

    def _await_child(self, job: Job, process: multiprocessing.Process, outcomes) -> None:
        timed_out = False
        try:
            deadline = monotonic() + self.job_timeout_seconds
            while process.is_alive() and not self._stop.is_set():
                if self._is_cancelled(job.id):
                    process.terminate()
                    break
                remaining = deadline - monotonic()
                if remaining <= 0:
                    timed_out = True
                    process.terminate()
                    break
                process.join(min(0.1, remaining))
            if process.is_alive():
                process.terminate()
            process.join()
            if timed_out:
                self.repo.mark_failure(
                    job.id,
                    f"job timed out after {self.job_timeout_seconds:g} seconds; child was terminated",
                )
                return
            if self._is_cancelled(job.id):
                return
            try:
                outcome, detail = outcomes.get_nowait()
            except Empty:
                self.repo.mark_failure(job.id, "job child exited without reporting an outcome")
                return
            if outcome == "success":
                self.repo.mark_success(job.id, detail)
            else:
                self.repo.mark_failure(job.id, detail)
        finally:
            outcomes.close()
            with self._processes_lock:
                self._processes.pop(job.id, None)
            self._sem.release()

    def _is_cancelled(self, job_id: str) -> bool:
        current = self.repo.get(job_id)
        return current is not None and current.status == "cancelled"

    def stop(self, wait: bool = True) -> None:
        self._stop.set()
        if self._poller is not None:
            self._poller.join(timeout=5)
            self._poller = None
        with self._processes_lock:
            processes = list(self._processes.values())
        for process in processes:
            if process.is_alive():
                process.terminate()
        if wait:
            for process in processes:
                process.join(timeout=5)
