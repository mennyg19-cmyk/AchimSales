"""The worker: pulls jobs off the queue and runs them in the background."""

# === What's in this file ===
# The worker is what actually runs reports. It loops: grab the next queued job
# (atomically, so two workers never run the same one), run its handler in a side
# thread with a time limit, keep a heartbeat ticking so we can tell it's alive,
# and record success or failure. A small maintenance loop requeues jobs whose
# worker died. The exact same code runs whether it's a separate process or a
# daemon thread inside the web app (the in-process fallback).
#
# Worker.start() -- spawn the loop threads and return (used by the in-process mode)
# Worker.run_forever() -- start, then block until stopped (used by worker_main.py)
# Worker.request_stop() -- ask the loops to finish and exit
# _run_one() -- run a single job with heartbeat + timeout + cancel handling

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from ..config import Config
from ..data.connection import Database
from ..data.repositories.jobs import JobRepository
from .types import HandlerRegistry, JobContext, registry as default_registry

log = logging.getLogger("rebuild.worker")

_POLL_SECONDS = 1.0


class Worker:
    def __init__(
        self,
        db: Database,
        config: Config,
        handler_registry: HandlerRegistry = default_registry,
    ) -> None:
        self._db = db
        self._config = config
        self._registry = handler_registry
        self._jobs = JobRepository(db, config.job_queue_max, config.job_stale_seconds)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        # Requeue anything a previous (crashed) worker left mid-run before we begin.
        try:
            self._jobs.recover_orphans()
        except Exception:  # noqa: BLE001 - a recovery hiccup must not stop the worker starting
            log.exception("orphan recovery at startup failed")

        count = max(1, self._config.job_worker_threads)
        for i in range(count):
            t = threading.Thread(target=self._loop, name=f"worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)
        maint = threading.Thread(target=self._maintenance_loop, name="worker-maint", daemon=True)
        maint.start()
        self._threads.append(maint)
        log.info("worker started (%d loop thread(s), mode=%s)", count, self._config.worker_mode)

    def run_forever(self) -> None:
        self.start()
        try:
            while not self._stop.is_set():
                self._stop.wait(60)
        except KeyboardInterrupt:
            pass
        finally:
            self.request_stop()

    def request_stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        # Each loop thread owns a one-slot executor purely so it can enforce a
        # per-job time limit via Future.result(timeout=...).
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            while not self._stop.is_set():
                try:
                    job = self._jobs.claim_next()
                except Exception:  # noqa: BLE001 - keep polling even if one claim fails
                    log.exception("claim_next failed")
                    self._stop.wait(_POLL_SECONDS)
                    continue
                if job is None:
                    self._stop.wait(_POLL_SECONDS)
                    continue
                self._run_one(job, executor)
        finally:
            executor.shutdown(wait=False)

    def _run_one(self, job, executor: ThreadPoolExecutor) -> None:
        handler = self._registry.get(job.job_type)
        if handler is None:
            self._jobs.mark_failed(job.id, f"No handler registered for job type '{job.job_type}'.")
            return

        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop, args=(job.id, heartbeat_stop), daemon=True
        )
        heartbeat.start()

        ctx = JobContext(job=job, config=self._config, db=self._db, jobs=self._jobs)
        future = executor.submit(handler, ctx)
        try:
            result_ref = future.result(timeout=self._config.max_job_seconds)
            if self._jobs.is_cancelled(job.id):
                log.info("job %s finished but was cancelled; leaving as cancelled", job.id)
            else:
                self._jobs.mark_done(job.id, result_ref)
        except FutureTimeout:
            self._jobs.mark_failed(
                job.id,
                f"The report took longer than {self._config.max_job_seconds} seconds and was stopped.",
            )
            log.warning("job %s timed out after %ss", job.id, self._config.max_job_seconds)
        except Exception as exc:  # noqa: BLE001 - any handler error fails the job, not the worker
            log.exception("job %s handler raised", job.id)
            self._jobs.mark_failed(job.id, str(exc))
        finally:
            heartbeat_stop.set()

    def _heartbeat_loop(self, job_id: str, stop: threading.Event) -> None:
        interval = max(5, self._config.job_stale_seconds // 3)
        while not stop.is_set():
            try:
                self._jobs.heartbeat(job_id)
            except Exception:  # noqa: BLE001 - a missed heartbeat isn't fatal
                log.exception("heartbeat write failed for job %s", job_id)
            stop.wait(interval)

    def _maintenance_loop(self) -> None:
        interval = max(30, self._config.job_stale_seconds)
        while not self._stop.is_set():
            self._stop.wait(interval)
            if self._stop.is_set():
                break
            try:
                self._jobs.recover_orphans()
            except Exception:  # noqa: BLE001 - keep the worker alive through a bad sweep
                log.exception("periodic orphan recovery failed")
