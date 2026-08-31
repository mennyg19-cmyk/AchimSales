"""Durable job drain: in-process for tests, killable child processes in prod.

Capacity on the B1 is one child at a time. The parent claims a row, spawns
``python -m web.jobs.child JOB_ID``, and waits with a hard timeout. Timeout
kills the child process group and records cancelled.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Callable

from web.data.connection import Database
from web.data.repositories.jobs import Job, JobRepository
from web.jobs.limits import JOB_TIMEOUT_SECONDS, WORKER_BEAT_EVERY_SECONDS

log = logging.getLogger(__name__)


@dataclass
class JobContext:
    """Passed to a handler. `set_progress` writes through to the durable table."""
    job: Job
    _repo: JobRepository

    def set_progress(self, pct: int) -> None:
        self._repo.set_progress(self.job.id, pct)

    def is_cancelled(self) -> bool:
        current = self._repo.get(self.job.id)
        return current is None or current.status == "cancelled"

    def abort_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise JobCancelled()


class JobCancelled(Exception):
    """The user cancelled this job; skip remaining side effects."""


# A handler runs the work and returns a result_ref (e.g. a cache key), or "".
Handler = Callable[[JobContext], str]


class JobWorker:
    def __init__(self, db: Database, max_workers: int = 1, app=None):
        self.repo = JobRepository(db)
        self.max_workers = max(1, max_workers)
        self.app = app
        self.handlers: dict[str, Handler] = {}
        self._sem = threading.BoundedSemaphore(self.max_workers)
        self._stop = threading.Event()
        self._executor: ThreadPoolExecutor | None = None
        self._poller: threading.Thread | None = None
        self._child_proc: subprocess.Popen | None = None
        self._killed_by_parent = False

    def register(self, job_type: str, handler: Handler) -> None:
        self.handlers[job_type] = handler

    @property
    def running(self) -> bool:
        """True once the background poller thread is started (see start())."""
        return self._poller is not None

    def health(self) -> dict:
        """Live snapshot of the poller for the admin diagnostic."""
        return {
            "started": self._poller is not None or self._child_proc is not None,
            "poller_alive": bool(self._poller and self._poller.is_alive()),
            "max_workers": self.max_workers,
            "free_slots": self._sem._value,
            "handler_types": sorted(self.handlers),
            "child_pid": None if self._child_proc is None else self._child_proc.pid,
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
        current = self.repo.get(job.id)
        if current is None or current.status != "running":
            return
        handler = self.handlers.get(job.type)
        if handler is None:
            self.repo.mark_failure(job.id, f"no handler for job type {job.type!r}")
            return
        ctx = self.app.app_context() if self.app is not None else nullcontext()
        try:
            with ctx:
                result_ref = handler(JobContext(job, self.repo)) or ""
            self.repo.mark_success(job.id, result_ref)
        except JobCancelled:
            log.info("job %s (%s) cancelled; skipping success", job.id, job.type)
        except Exception as exc:  # noqa: BLE001 - record failure, keep worker alive
            log.exception("job %s (%s) failed", job.id, job.type)
            self.repo.mark_failure(job.id, str(exc))

    # --- killable child (production worker process) ------------------------

    def run_forever(self, poll_interval: float = 1.0,
                    job_timeout: float | None = None) -> None:
        """Claim one job at a time, run it in a child, wait or kill on timeout."""
        timeout = JOB_TIMEOUT_SECONDS if job_timeout is None else job_timeout
        recovered = self.repo.recover_orphans()
        if recovered:
            log.info("recovered %d orphaned running job(s) on startup", recovered)
        self._stop.clear()
        self._install_stop_signals()
        self._beat_worker()
        last_beat = time.monotonic()
        log.info("job child loop entered (timeout=%ss, poll=%.1fs)", timeout, poll_interval)
        while not self._stop.is_set():
            now = time.monotonic()
            if now - last_beat >= WORKER_BEAT_EVERY_SECONDS:
                self._beat_worker()
                last_beat = now
            job = self.repo.claim_next()
            if job is None:
                self._stop.wait(poll_interval)
                continue
            log.info("job worker claimed %s (%s)", job.id, job.type)
            self._run_in_child(job, timeout)
        log.warning("job child loop exited (stop=%s)", self._stop.is_set())

    def process_next_child(self, timeout: float | None = None) -> str | None:
        """Claim one job and run it in a child (tests). Returns the job id or None."""
        job = self.repo.claim_next()
        if job is None:
            return None
        self._run_in_child(
            job, JOB_TIMEOUT_SECONDS if timeout is None else timeout,
        )
        return job.id

    def _run_in_child(self, job: Job, timeout: float) -> None:
        self._killed_by_parent = False
        proc = subprocess.Popen(
            [sys.executable, "-m", "web.jobs.child", job.id],
            start_new_session=True,
        )
        self._child_proc = proc
        try:
            rc = self._wait_child(proc, timeout)
            if rc is None:
                log.warning("job %s timed out after %ss; killing child pid=%s",
                            job.id, timeout, proc.pid)
                self._kill_child(proc)
                self.repo.cancel(job.id, error="Timed out (45 minute cap)")
                return
        finally:
            self._child_proc = None
        if rc not in (0, None):
            # SIGTERM/stop killed this child so the next worker can recover:
            # safe types requeue, schedule.run / report.deliver cancel.
            if self._stop.is_set() and self._killed_by_parent:
                log.info("job %s left running after worker stop (child rc=%s)",
                         job.id, rc)
                return
            current = self.repo.get(job.id)
            if current is not None and current.status == "running":
                self.repo.mark_failure(job.id, f"job child exited {rc}")

    def _wait_child(self, proc: subprocess.Popen, timeout: float) -> int | None:
        """Wait for the child; beat the worker heartbeat between wait chunks.

        Returns the exit code, or None when the job cap elapsed. A single
        proc.wait(timeout=cap) would skip beats for the whole run and make
        prod /readyz look dead after 90s of a healthy job.
        """
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            chunk = min(WORKER_BEAT_EVERY_SECONDS, remaining)
            try:
                return proc.wait(timeout=chunk)
            except subprocess.TimeoutExpired:
                self._beat_worker()

    def _kill_child(self, proc: subprocess.Popen) -> None:
        self._killed_by_parent = True
        try:
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass

    def _beat_worker(self) -> None:
        from web.data.repositories.app_settings import AppSettingsRepository

        try:
            AppSettingsRepository(self.repo.db).beat_worker(os.getpid())
        except Exception:  # noqa: BLE001 - heartbeat must not kill the loop
            log.exception("worker heartbeat failed")

    def _install_stop_signals(self) -> None:
        def _handle(signum, _frame):
            log.info("job worker received signal %s; stopping", signum)
            self._stop.set()
            if self._child_proc is not None:
                self._kill_child(self._child_proc)

        try:
            signal.signal(signal.SIGTERM, _handle)
            signal.signal(signal.SIGINT, _handle)
        except (ValueError, OSError):
            # Not the main thread (tests) — stop() still works.
            pass

    # --- background lifecycle (in-process threads; tests / local drain) ----

    def start(self, poll_interval: float = 1.0) -> None:
        if self._poller is not None:
            return
        recovered = self.repo.recover_orphans()
        if recovered:
            log.info("recovered %d orphaned running job(s) on startup", recovered)
        self._stop.clear()
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="job")
        self._poller = threading.Thread(target=self._loop, args=(poll_interval,), daemon=True)
        self._poller.start()

    def _loop(self, poll_interval: float) -> None:
        heartbeat_every = max(1, int(30 / poll_interval))
        iterations = 0
        log.info("job poller loop entered (max_workers=%d, poll=%.1fs)", self.max_workers, poll_interval)
        while not self._stop.is_set():
            iterations += 1
            if iterations % heartbeat_every == 0:
                log.info("job poller heartbeat: iterations=%d free_slots=%d", iterations, self._sem._value)
            if not self._sem.acquire(timeout=poll_interval):
                continue
            try:
                job = self.repo.claim_next()
                if job is None:
                    self._sem.release()
                    self._stop.wait(poll_interval)
                    continue
                log.info("job poller claimed %s (%s)", job.id, job.type)
                self._executor.submit(self._run_and_release, job)
            except Exception:  # noqa: BLE001 - infra error must not kill the poller
                log.exception("job poller iteration failed")
                self._sem.release()
                self._stop.wait(poll_interval)
        log.warning("job poller loop exited (stop=%s)", self._stop.is_set())

    def _run_and_release(self, job: Job) -> None:
        try:
            self._run(job)
        finally:
            self._sem.release()

    def stop(self, wait: bool = True) -> None:
        self._stop.set()
        if self._child_proc is not None:
            self._kill_child(self._child_proc)
        if self._poller is not None:
            self._poller.join(timeout=5)
            self._poller = None
        if self._executor is not None:
            self._executor.shutdown(wait=wait)
            self._executor = None
