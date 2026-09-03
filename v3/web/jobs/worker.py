"""Durable job worker with killable production child processes.

The synchronous helpers run in-process for focused unit tests. The production
poller runs every claimed handler in a child process so a timeout stops the work,
then records the outcome and releases its capacity slot.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from time import monotonic
from pathlib import Path
from typing import Callable

from web.data.connection import Database
from web.data.repositories.jobs import (
    DEFAULT_QUEUE_MAX_AGE_SECONDS,
    DEFAULT_QUEUE_MAX_DEPTH,
    Job,
    JobRepository,
)

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
_CHILD_STOP_TIMEOUT_SECONDS = 2


class JobWorker:
    def __init__(
        self,
        db: Database,
        max_workers: int = DEFAULT_MAX_WORKERS,
        *,
        job_timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS,
        queue_max_depth: int = DEFAULT_QUEUE_MAX_DEPTH,
        queue_max_age_seconds: float = DEFAULT_QUEUE_MAX_AGE_SECONDS,
        is_beta: bool = False,
        app_env: str | None = None,
        auth_mode: str | None = None,
    ):
        self.db = db
        self.repo = JobRepository(
            db,
            queue_max_depth=queue_max_depth,
            queue_max_age_seconds=queue_max_age_seconds,
        )
        self.max_workers = max(1, max_workers)
        self.job_timeout_seconds = max(1, job_timeout_seconds)
        self.queue_max_depth = max(1, queue_max_depth)
        self.queue_max_age_seconds = max(1, queue_max_age_seconds)
        self.is_beta = is_beta
        self.app_env = app_env
        self.auth_mode = auth_mode
        self._child_argv_factory: Callable[[Job], list[str]] | None = None
        self.handlers: dict[str, Handler] = {}
        self._sem = threading.BoundedSemaphore(self.max_workers)
        self._stop = threading.Event()
        self._poller: threading.Thread | None = None
        self._processes: dict[str, subprocess.Popen] = {}
        self._processes_lock = threading.Lock()

    def register(self, job_type: str, handler: Handler) -> None:
        self.handlers[job_type] = handler

    @property
    def running(self) -> bool:
        """True once the background poller thread is started (see start())."""
        return self._poller is not None

    def health(self) -> dict:
        """Live snapshot of this sibling worker's poller for the admin diagnostic.

        It distinguishes a worker that never started, a dead poller, and a
        poller whose capacity is held by hung handlers.
        """
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
                expired = self.repo.expire_queued_older_than()
                if expired:
                    log.warning("expired %d queued job(s) that waited too long", expired)
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
        process: subprocess.Popen | None = None
        try:
            process = subprocess.Popen(self._child_argv(job), env=self._child_env())
            with self._processes_lock:
                self._processes[job.id] = process
            threading.Thread(
                target=self._await_child,
                args=(job, process),
                name=f"job-monitor-{job.id[:8]}",
                daemon=True,
            ).start()
        except Exception as exc:  # noqa: BLE001 - a claimed job must become terminal
            log.exception("job %s (%s) child failed to start", job.id, job.type)
            if process is not None:
                with self._processes_lock:
                    self._processes.pop(job.id, None)
                try:
                    self._stop_child(process)
                except Exception:  # noqa: BLE001 - launch failure still frees capacity
                    log.exception("job %s child cleanup failed", job.id)
            self.repo.mark_failure(job.id, f"job child failed to start: {exc}")
            self._sem.release()

    def _child_argv(self, job: Job) -> list[str]:
        if self._child_argv_factory is not None:
            return self._child_argv_factory(job)
        return [sys.executable, "-m", "web.jobs.run_one", job.id]

    def _child_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.app_env is not None:
            if "APP_ENV" not in os.environ:
                log.warning("parent process has no APP_ENV; child will use %s from config", self.app_env)
            env["APP_ENV"] = self.app_env
        if self.auth_mode is not None:
            if "AUTH_MODE" not in os.environ:
                log.warning("parent process has no AUTH_MODE; child will use %s from config", self.auth_mode)
            env["AUTH_MODE"] = self.auth_mode
        if self.is_beta:
            env["BETA_PRECIOUS_DB_PATH"] = str(self.db.precious_path)
            env["BETA_CACHE_DB_PATH"] = str(self.db.cache_path)
            env["V3_RUN_ONE_BETA"] = "1"
        else:
            env["PRECIOUS_DB_PATH"] = str(self.db.precious_path)
            env["CACHE_DB_PATH"] = str(self.db.cache_path)
        v3_path = str(Path(__file__).resolve().parents[2])
        current_path = env.get("PYTHONPATH", "")
        if v3_path not in current_path.split(os.pathsep):
            env["PYTHONPATH"] = os.pathsep.join(filter(None, (v3_path, current_path)))
        return env

    def _await_child(self, job: Job, process: subprocess.Popen) -> None:
        timed_out = False
        try:
            deadline = monotonic() + self.job_timeout_seconds
            while process.poll() is None and not self._stop.is_set():
                if self._is_cancelled(job.id):
                    process.terminate()
                    break
                remaining = deadline - monotonic()
                if remaining <= 0:
                    timed_out = True
                    process.terminate()
                    break
                try:
                    process.wait(timeout=min(0.1, remaining))
                except subprocess.TimeoutExpired:
                    pass
            if process.poll() is None:
                self._stop_child(process)
            if timed_out:
                current = self.repo.get(job.id)
                if current is not None and current.status == "running":
                    self.repo.mark_failure(
                        job.id,
                        f"job timed out after {self.job_timeout_seconds:g} seconds; child was terminated",
                    )
                return
            if self._is_cancelled(job.id):
                return
            current = self.repo.get(job.id)
            if current is not None and current.status == "running":
                self.repo.mark_failure(job.id, "job child exited without reporting an outcome")
        finally:
            with self._processes_lock:
                self._processes.pop(job.id, None)
            self._sem.release()

    @staticmethod
    def _stop_child(process: subprocess.Popen) -> None:
        process.terminate()
        try:
            process.wait(timeout=_CHILD_STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=_CHILD_STOP_TIMEOUT_SECONDS)

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
            if process.poll() is None:
                self._stop_child(process)
        if wait:
            for process in processes:
                try:
                    process.wait(timeout=_CHILD_STOP_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    pass
