"""Durable job worker: dispatch, failure isolation, progress, bounded draining."""

import time

import pytest

from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.jobs import JobRepository
from web.jobs.scheduler import Scheduler
from web.jobs.worker import JobContext, JobWorker


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "precious.db", tmp_path / "cache.db")
    migrate(d)
    return d


def test_handler_success_records_result(db):
    worker = JobWorker(db)
    worker.register("echo", lambda ctx: f"result:{ctx.job.params.get('x')}")
    jobs = JobRepository(db)
    jid = jobs.enqueue("echo", params={"x": 7})

    assert worker.process_next() == jid
    done = jobs.get(jid)
    assert done.status == "success" and done.result_ref == "result:7" and done.progress == 100


def test_handler_failure_is_isolated(db):
    worker = JobWorker(db)

    def boom(ctx):
        raise RuntimeError("kaboom")

    worker.register("boom", boom)
    jobs = JobRepository(db)
    jid = jobs.enqueue("boom")

    worker.process_next()
    failed = jobs.get(jid)
    assert failed.status == "failure" and "kaboom" in failed.error


def test_unknown_job_type_fails_cleanly(db):
    worker = JobWorker(db)
    jobs = JobRepository(db)
    jid = jobs.enqueue("nope")
    worker.process_next()
    assert jobs.get(jid).status == "failure"
    assert "no handler" in jobs.get(jid).error


def test_progress_writes_through(db):
    jobs = JobRepository(db)
    worker = JobWorker(db)
    mid_progress = []

    def slow(ctx: JobContext):
        ctx.set_progress(40)
        mid_progress.append(jobs.get(ctx.job.id).progress)  # durable mid-run read
        return ""

    worker.register("slow", slow)
    jid = jobs.enqueue("slow")
    worker.process_next()
    assert mid_progress == [40]
    assert jobs.get(jid).progress == 100  # mark_success forces 100


def test_drain_processes_all_queued(db):
    worker = JobWorker(db)
    worker.register("echo", lambda ctx: "")
    jobs = JobRepository(db)
    for i in range(5):
        jobs.enqueue("echo", params={"i": i})
    assert worker.drain() == 5
    assert worker.process_next() is None  # empty now


def test_process_next_empty_returns_none(db):
    worker = JobWorker(db)
    assert worker.process_next() is None


def test_background_worker_drains_queue(db):
    processed = []
    worker = JobWorker(db, max_workers=2)
    worker.register("bg", lambda ctx: processed.append(ctx.job.id) or "")
    jobs = JobRepository(db)
    ids = {jobs.enqueue("bg", params={"i": i}) for i in range(6)}

    worker.start(poll_interval=0.05)
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            if all(jobs.get(j).status == "success" for j in ids):
                break
            time.sleep(0.05)
    finally:
        worker.stop()

    assert all(jobs.get(j).status == "success" for j in ids)
    assert sorted(processed) == sorted(ids)


def test_orphaned_running_job_is_recovered(db):
    """A job stuck in 'running' (crash) is requeued and can complete."""
    jobs = JobRepository(db)
    worker = JobWorker(db)
    worker.register("echo", lambda ctx: "ok")
    jid = jobs.enqueue("echo")
    claimed = jobs.claim_next()  # now 'running' (simulate crash before finish)
    assert claimed.id == jid and jobs.get(jid).status == "running"

    assert jobs.recover_orphans() == 1
    assert jobs.get(jid).status == "queued"
    worker.process_next()
    assert jobs.get(jid).status == "success"


def test_recovery_increments_attempts(db):
    """Each crash-recovery bumps the attempt counter so the cap can be enforced."""
    jobs = JobRepository(db)
    jid = jobs.enqueue("echo")
    assert jobs.get(jid).attempts == 0
    jobs.claim_next()        # -> running (simulate crash)
    jobs.recover_orphans()   # -> requeued, attempt counted
    assert jobs.get(jid).attempts == 1


def test_repeatedly_crashing_job_is_failed_not_looped(db):
    """A job that keeps dying mid-run (e.g. OOM) is failed once retries run out,
    instead of being requeued forever (the crash loop that took the site down)."""
    jobs = JobRepository(db)
    jid = jobs.enqueue("echo")

    # 1st crash: orphaned -> requeued (one retry used).
    jobs.claim_next()
    assert jobs.recover_orphans() == 1
    assert jobs.get(jid).status == "queued"

    # 2nd crash: retries exhausted -> failed, NOT requeued.
    jobs.claim_next()
    assert jobs.recover_orphans() == 0
    failed = jobs.get(jid)
    assert failed.status == "failure"
    assert "ran out of memory" in failed.error


def test_recover_orphans_unblocks_dedup(db):
    jobs = JobRepository(db)
    a = jobs.enqueue("echo", dedup_key="k")
    jobs.claim_next()  # a -> running (orphaned)
    jobs.recover_orphans()
    # Same dedup key now reuses the recovered (re-queued) job, not a new one.
    b = jobs.enqueue("echo", dedup_key="k")
    assert b == a


def test_cancel_works_for_queued_and_running(db):
    """A user can cancel a run whether it's still queued or already running
    (e.g. stuck on a slow Reporting API call). A finished job can't be cancelled."""
    jobs = JobRepository(db)
    queued = jobs.enqueue("echo")
    assert jobs.cancel(queued) is True
    assert jobs.get(queued).status == "cancelled"

    running = jobs.enqueue("echo")
    jobs.claim_next()  # -> running
    assert jobs.get(running).status == "running"
    assert jobs.cancel(running) is True
    assert jobs.get(running).status == "cancelled"
    assert jobs.cancel(running) is False  # already terminal


def test_mark_success_does_not_resurrect_cancelled(db):
    jobs = JobRepository(db)
    jid = jobs.enqueue("echo")
    assert jobs.cancel(jid) is True  # queued -> cancelled
    jobs.mark_success(jid, "x")      # guarded to 'running' -> no-op
    assert jobs.get(jid).status == "cancelled"


def test_cancelled_running_job_not_overwritten_when_call_returns(db):
    """Cancelling a running job sticks: when the slow upstream call finally
    finishes, mark_success/mark_failure are guarded to 'running' so they can't
    flip a cancelled job back to success."""
    jobs = JobRepository(db)
    jid = jobs.enqueue("echo")
    jobs.claim_next()  # -> running
    assert jobs.cancel(jid) is True
    jobs.mark_success(jid, "late-result")
    assert jobs.get(jid).status == "cancelled"


def test_status_summary_counts_and_active(db):
    jobs = JobRepository(db)
    done = jobs.enqueue("echo")
    jobs.cancel(done)                 # -> cancelled
    jobs.enqueue("echo")              # stays queued
    jobs.enqueue("echo")
    jobs.claim_next()                 # one -> running
    summary = jobs.status_summary()
    assert summary["by_status"].get("cancelled") == 1
    assert summary["by_status"].get("running") == 1
    assert summary["by_status"].get("queued") == 1
    # Active = queued + running (the cancelled one is terminal, excluded).
    assert summary["active_count"] == 2
    assert {a["status"] for a in summary["active"]} == {"queued", "running"}


def test_background_concurrency_is_bounded(db):
    jobs = JobRepository(db)
    worker = JobWorker(db, max_workers=2)
    live = {"now": 0, "max": 0}
    lock = __import__("threading").Lock()

    def busy(ctx):
        with lock:
            live["now"] += 1
            live["max"] = max(live["max"], live["now"])
        time.sleep(0.1)
        with lock:
            live["now"] -= 1
        return ""

    worker.register("busy", busy)
    ids = {jobs.enqueue("busy", params={"i": i}) for i in range(8)}
    worker.start(poll_interval=0.02)
    try:
        deadline = time.time() + 10
        while time.time() < deadline and not all(jobs.get(j).status == "success" for j in ids):
            time.sleep(0.05)
    finally:
        worker.stop()
    assert all(jobs.get(j).status == "success" for j in ids)
    assert live["max"] <= 2  # never exceeded max_workers


def test_scheduler_queues_jobs_before_start():
    sched = Scheduler()
    sched.add_cron("noop", lambda: None, hour=3)
    assert len(sched._pending) == 1
    # start/shutdown should not raise and should register the pending job
    sched.start()
    try:
        assert sched._scheduler.get_job("noop") is not None
    finally:
        sched.shutdown()
