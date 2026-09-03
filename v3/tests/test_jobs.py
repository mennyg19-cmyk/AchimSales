"""Durable job worker: dispatch, failure isolation, progress, bounded draining."""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from web import create_app, start_worker_services, stop_worker_services
from web.config import Config

from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.jobs import JobRepository, QueueAdmissionError
from web.data.repositories.users import UserRepository
from web.jobs.scheduler import Scheduler
from web.jobs.worker import JobContext, JobWorker
from web.jobs.worker_main import run_worker_app


_TESTS_DIR = Path(__file__).parent


def _echo_child_argv(db):
    return lambda job: [
        sys.executable, str(_TESTS_DIR / "job_child_echo.py"), job.id,
        str(db.precious_path), str(db.cache_path),
    ]


def _hang_child_argv(*, ignore_sigterm: bool = False):
    argv = [sys.executable, str(_TESTS_DIR / "job_child_hang.py")]
    if ignore_sigterm:
        argv.append("ignore-sigterm")
    return lambda job: argv


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


def test_worker_defaults_to_one_processing_slot(db):
    assert JobWorker(db).max_workers == 1


def test_background_worker_drains_queue(db):
    worker = JobWorker(db, max_workers=2)
    worker._child_argv_factory = _echo_child_argv(db)
    worker.register("bg", lambda ctx: "")
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


def test_standalone_worker_bootstraps_and_completes_enqueued_job(tmp_path, monkeypatch):
    class EmptyReportingApi(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.dumps({"rows": [], "columns": [], "row_count": 0}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), EmptyReportingApi)
    Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("REPORTING_API_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("REPORTING_API_KEY", "test-key")
    cfg = Config(
        app_env="dev", auth_mode="dev", flask_secret="test-secret",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url=os.environ["REPORTING_API_BASE_URL"],
        reporting_api_key=os.environ["REPORTING_API_KEY"], precious_db_path=tmp_path / "precious.db",
        cache_db_path=tmp_path / "cache.db", litestream_blob_url="", new_app_marker=True,
    )
    app = create_app(cfg)
    migrate(app.config["DB"])
    jobs = JobRepository(app.config["DB"])
    job_id = jobs.enqueue("dashboard.refresh")

    run_worker_app(app)
    try:
        from web import is_worker_process
        from web.jobs.status import snapshot
        assert is_worker_process() is True
        identity = snapshot(app.config["DB"])["process_identity"]
        assert identity["pid"] > 0 and identity["hostname"] and identity["started_at"]
        deadline = time.time() + 5
        while time.time() < deadline and jobs.get(job_id).status != "success":
            time.sleep(0.05)
    finally:
        stop_worker_services(app)
        server.shutdown()

    job = jobs.get(job_id)
    assert job.status == "success"
    assert job.result_ref.startswith("customers=")
    from web import is_worker_process
    assert is_worker_process() is False


def test_health_reports_started_and_free_slots(db):
    # The admin diagnostic relies on this snapshot to tell a never-started worker
    # from a wedged one. Before start(): not started, all slots free.
    worker = JobWorker(db, max_workers=2)
    worker.register("bg", lambda ctx: "")
    h = worker.health()
    assert h["started"] is False and h["poller_alive"] is False
    assert h["free_slots"] == 2 and h["handler_types"] == ["bg"]

    worker.start(poll_interval=0.05)
    try:
        assert worker.health()["started"] is True
        assert worker.health()["poller_alive"] is True
    finally:
        worker.stop()


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
    worker._child_argv_factory = _echo_child_argv(db)

    def busy(ctx):
        time.sleep(0.1)
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


def test_background_timeout_kills_child_and_frees_slot(db):
    jobs = JobRepository(db)
    worker = JobWorker(db, job_timeout_seconds=0.1)
    worker._child_argv_factory = _hang_child_argv()
    worker.register("hang", lambda ctx: "")
    job_id = jobs.enqueue("hang")

    worker.start(poll_interval=0.01)
    try:
        deadline = time.time() + 5
        while time.time() < deadline and jobs.get(job_id).status == "queued":
            time.sleep(0.02)
        while time.time() < deadline and jobs.get(job_id).status == "running":
            time.sleep(0.02)
        failed = jobs.get(job_id)
        assert failed.status == "failure"
        assert "timed out" in failed.error
        while time.time() < deadline and worker.health()["free_slots"] != 1:
            time.sleep(0.02)
        assert worker.health()["free_slots"] == 1
    finally:
        worker.stop()


def test_background_timeout_sigkills_child_ignoring_sigterm_and_frees_slot(db):
    jobs = JobRepository(db)
    worker = JobWorker(db, job_timeout_seconds=0.1)
    worker._child_argv_factory = _hang_child_argv(ignore_sigterm=True)
    worker.register("hang", lambda ctx: "")
    job_id = jobs.enqueue("hang")

    worker.start(poll_interval=0.01)
    try:
        deadline = time.time() + 8
        while time.time() < deadline and jobs.get(job_id).status != "failure":
            time.sleep(0.02)
        failed = jobs.get(job_id)
        assert failed.status == "failure"
        assert "timed out" in failed.error
        while time.time() < deadline and worker.health()["free_slots"] != 1:
            time.sleep(0.02)
        assert worker.health()["free_slots"] == 1
    finally:
        worker.stop()


def test_child_launch_failure_marks_job_failed_and_frees_slot(db):
    jobs = JobRepository(db)
    worker = JobWorker(db)
    worker._child_argv_factory = lambda job: ["/path/that/does/not/exist"]
    worker.register("missing-child", lambda ctx: "")
    job_id = jobs.enqueue("missing-child")

    worker.start(poll_interval=0.01)
    try:
        deadline = time.time() + 5
        while time.time() < deadline and jobs.get(job_id).status != "failure":
            time.sleep(0.02)
        failed = jobs.get(job_id)
        assert failed.status == "failure"
        assert "failed to start" in failed.error
        while time.time() < deadline and worker.health()["free_slots"] != 1:
            time.sleep(0.02)
        assert worker.health()["free_slots"] == 1
    finally:
        worker.stop()


def test_enqueue_refuses_queue_at_depth_limit(db):
    worker = JobWorker(db, queue_max_depth=1)
    job_id = worker.repo.enqueue("echo")

    with pytest.raises(QueueAdmissionError, match="queue is full.*max depth 1"):
        worker.repo.enqueue("echo")

    with db.precious() as conn:
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
    assert worker.repo.get(job_id).status == "queued"


def test_background_worker_drains_queue_over_depth_limit(db):
    jobs = JobRepository(db)
    worker = JobWorker(db, queue_max_depth=1)
    worker._child_argv_factory = _echo_child_argv(db)
    worker.register("echo", lambda ctx: "")
    first_id = worker.repo.enqueue("echo")
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO jobs(id, type, status, params_json) VALUES ('extra-queued', 'echo', 'queued', '{}')"
        )

    worker.start(poll_interval=0.01)
    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            if jobs.get(first_id).status == jobs.get("extra-queued").status == "success":
                break
            time.sleep(0.02)
    finally:
        worker.stop()

    assert jobs.get(first_id).status == jobs.get("extra-queued").status == "success"


def test_background_worker_expires_over_age_job_and_drains_younger_job(db):
    jobs = JobRepository(db)
    worker = JobWorker(db, queue_max_age_seconds=1)
    worker._child_argv_factory = _echo_child_argv(db)
    worker.register("echo", lambda ctx: "")
    expired_id = jobs.enqueue("echo")
    younger_id = jobs.enqueue("echo")
    with db.precious() as conn:
        conn.execute("UPDATE jobs SET created_at=datetime('now', '-2 minutes') WHERE id=?", (expired_id,))

    worker.start(poll_interval=0.01)
    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            if jobs.get(expired_id).status == "failure" and jobs.get(younger_id).status == "success":
                break
            time.sleep(0.02)
    finally:
        worker.stop()

    expired = jobs.get(expired_id)
    assert expired.status == "failure"
    assert "sat in the queue too long" in expired.error
    assert jobs.get(younger_id).status == "success"


def test_claim_next_prioritizes_schedules_and_delivery_over_exports(db):
    jobs = JobRepository(db)
    export = jobs.enqueue("report.export")
    delivery = jobs.enqueue("report.deliver")
    schedule = jobs.enqueue("schedule.run")

    assert jobs.claim_next().id == schedule
    assert jobs.claim_next().id == delivery
    assert jobs.claim_next().id == export


def test_scheduler_start_failure_keeps_readiness_red(tmp_path, monkeypatch):
    class BrokenScheduler:
        def add_cron(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("scheduler unavailable")

        def shutdown(self):
            pass

    from web.jobs import scheduler as scheduler_module
    from web.jobs import status

    cfg = Config(
        app_env="dev", auth_mode="dev", flask_secret="test-secret",
        tenant_id="", client_id="", client_secret="", reporting_api_base_url="",
        reporting_api_key="", precious_db_path=tmp_path / "precious.db",
        cache_db_path=tmp_path / "cache.db", litestream_blob_url="", new_app_marker=True,
    )
    app = create_app(cfg)
    migrate(app.config["DB"])
    monkeypatch.setattr(scheduler_module, "Scheduler", BrokenScheduler)
    with pytest.raises(RuntimeError, match="scheduler unavailable"):
        start_worker_services(app)
    assert app.config["JOB_WORKER"].running is False
    assert status.is_ready(app.config["DB"]) is False


def test_schedule_tick_beats_scheduler_when_enqueue_fails(tmp_path, monkeypatch):
    class FakeScheduler:
        def __init__(self):
            self.jobs = {}

        def add_cron(self, job_id, func, **kwargs):
            self.jobs[job_id] = func

        def start(self):
            pass

        def shutdown(self):
            pass

    from web.jobs import scheduler as scheduler_module
    from web.jobs import status
    from web.scheduling import tick

    cfg = Config(
        app_env="dev", auth_mode="dev", flask_secret="test-secret",
        tenant_id="", client_id="", client_secret="", reporting_api_base_url="",
        reporting_api_key="", precious_db_path=tmp_path / "precious.db",
        cache_db_path=tmp_path / "cache.db", litestream_blob_url="", new_app_marker=True,
    )
    app = create_app(cfg)
    migrate(app.config["DB"])
    monkeypatch.setattr(scheduler_module, "Scheduler", FakeScheduler)
    monkeypatch.setattr(tick, "make_tick", lambda *args: lambda: (_ for _ in ()).throw(RuntimeError("enqueue failed")))
    from web import _start_scheduler
    _start_scheduler(app, app.config["DB"])
    with pytest.raises(RuntimeError, match="enqueue failed"):
        app.config["SCHEDULER"].jobs["schedule-tick"]()
    assert status.snapshot(app.config["DB"])["scheduler_heartbeat_fresh"] is True


def test_cleanup_prunes_expired_cache_and_exports_then_marks_success(db):
    from web.jobs.cleanup import run_cleanup
    from web.jobs.status import snapshot

    with db.cache() as conn:
        conn.execute(
            "INSERT INTO report_payload_cache(cache_key, report_key, payload_json, built_at)"
            " VALUES ('old-cache', 'ordered', '{}', datetime('now', '-8 days'))"
        )
        conn.execute(
            "INSERT INTO report_exports(job_id, report_key, filename, content, size_bytes, built_at)"
            " VALUES ('old-export', 'ordered', 'old.xlsx', X'00', 1, datetime('now', '-8 days'))"
        )
    assert run_cleanup(db) == {"cache_rows": 1, "export_rows": 1}
    assert snapshot(db)["last_cleanup"] is not None


def test_cleanup_failure_does_not_mark_success(db, monkeypatch):
    from web.jobs import cleanup
    from web.jobs.status import snapshot

    class BrokenCache:
        def __init__(self, db):
            pass

        def prune(self, **kwargs):
            raise RuntimeError("cache unavailable")

    monkeypatch.setattr(cleanup, "ReportCache", BrokenCache)
    with pytest.raises(RuntimeError, match="cache unavailable"):
        cleanup.run_cleanup(db)
    assert snapshot(db)["last_cleanup"] is None


def test_worker_main_stays_alive_after_service_start_failure(monkeypatch):
    from web.jobs import worker_main

    def fail_to_start(app):
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(worker_main, "enabled_apps", lambda: [object()])
    monkeypatch.setattr(worker_main, "run_worker_app", fail_to_start)
    monkeypatch.setattr(worker_main, "stop_worker_services", lambda app: None)
    worker_main._stopping.set()
    try:
        assert worker_main.run() == 0
    finally:
        worker_main._stopping.clear()


def test_keep_run_stores_name_and_drops_oldest_over_cap(db):
    uid = UserRepository(db).upsert("a@x.com", display_name="A", role="admin").id
    jobs = JobRepository(db)
    ids = []
    for i in range(3):
        jid = jobs.enqueue("report.run", owner_user_id=uid, params={"i": i})
        jobs.claim_next()
        jobs.mark_success(jid, "ref")
        ids.append(jid)
    assert jobs.keep_run(ids[0], uid, kept_until="2099-01-01T00:00:00", name="Alpha", cap=2)
    assert jobs.keep_run(ids[1], uid, kept_until="2099-01-02T00:00:00", name="Beta", cap=2)
    assert jobs.keep_run(ids[2], uid, kept_until="2099-01-03T00:00:00", name="Gamma", cap=2)
    dropped = jobs.get(ids[0])
    assert dropped.kept_until is None and dropped.keep_name == ""
    assert jobs.get(ids[2]).keep_name == "Gamma"


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
