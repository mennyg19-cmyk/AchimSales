"""Durable job worker: dispatch, failure isolation, progress, bounded draining."""

import threading
import time

import pytest

from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.jobs import JobRepository, QueueAdmissionError
from web.data.repositories.users import UserRepository
from web.jobs.scheduler import Scheduler
from web.jobs.worker import JobContext, JobWorker


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "precious.db", tmp_path / "cache.db")
    migrate(d)
    return d


def test_app_worker_runs_handlers_with_flask_context(tmp_path):
    from web import create_app
    from web.config import Config
    from web.data.migrate import migrate

    app = create_app(Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="", is_beta=True,
    ))
    migrate(app.config["DB"])
    worker = app.config["JOB_WORKER"]
    seen = {}

    def handler(ctx):
        from flask import has_app_context
        seen["ctx"] = has_app_context()
        return "ok"

    worker.register("ctxprobe", handler)
    JobRepository(app.config["DB"]).enqueue("ctxprobe")
    worker.process_next()
    assert seen["ctx"] is True


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


def test_claim_next_prefers_schedule_run_over_export(db):
    jobs = JobRepository(db)
    export_id = jobs.enqueue("report.export")
    sched_id = jobs.enqueue("schedule.run")
    claimed = jobs.claim_next()
    assert claimed.id == sched_id
    assert jobs.claim_next().id == export_id


def test_admission_refuses_interactive_when_queue_is_deep(db, monkeypatch):
    monkeypatch.setattr("web.data.repositories.jobs.MAX_QUEUED_JOBS", 2)
    jobs = JobRepository(db)
    jobs.enqueue("report.run")
    jobs.enqueue("report.run")
    with pytest.raises(QueueAdmissionError):
        jobs.enqueue("report.export")
    # Clock runs still enqueue so exports cannot starve deliveries.
    sid = jobs.enqueue("schedule.run")
    assert jobs.get(sid).status == "queued"


def test_admission_allows_deduped_retry_when_queue_is_full(db, monkeypatch):
    monkeypatch.setattr("web.data.repositories.jobs.MAX_QUEUED_JOBS", 1)
    jobs = JobRepository(db)
    a = jobs.enqueue("report.run", dedup_key="same")
    b = jobs.enqueue("report.run", dedup_key="same")
    assert a == b


def test_fail_hung_cancels_old_running_jobs_not_requeued(db):
    jobs = JobRepository(db)
    old = jobs.enqueue("echo")
    fresh = jobs.enqueue("echo")
    assert jobs.claim_next().id == old
    assert jobs.claim_next().id == fresh
    with db.precious() as conn:
        conn.execute(
            "UPDATE jobs SET started_at=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", old),
        )
    assert jobs.fail_hung(45 * 60) == 1
    hung = jobs.get(old)
    assert hung.status == "cancelled" and "Timed out" in hung.error
    assert jobs.get(fresh).status == "running"
    jobs.mark_success(old, "late-result")
    assert jobs.get(old).status == "cancelled"


def test_keep_run_copies_payload_off_the_disposable_cache(db):
    uid = UserRepository(db).upsert("a@x.com", display_name="A", role="admin").id
    jobs = JobRepository(db)
    jid = jobs.enqueue("report.run", owner_user_id=uid, params={})
    jobs.claim_next()
    jobs.mark_success(jid, "cache-key")
    blob = '{"tabs": [{"key": "t", "rows": [{"n": 1}]}], "row_count": 1}'
    assert jobs.keep_run(jid, uid, kept_until="2099-01-01T00:00:00",
                         name="Kept", payload_json=blob)
    assert jobs.get_kept_payload(jid)["row_count"] == 1
    from web.reporting.cache import ReportCache
    ReportCache(db).prune(older_than_seconds=-1)
    assert jobs.get_kept_payload(jid)["tabs"][0]["rows"][0]["n"] == 1


def test_prune_expired_kept_drops_payload(db):
    uid = UserRepository(db).upsert("a@x.com", display_name="A", role="admin").id
    jobs = JobRepository(db)
    jid = jobs.enqueue("report.run", owner_user_id=uid, params={})
    jobs.claim_next()
    jobs.mark_success(jid, "cache-key")
    assert jobs.keep_run(
        jid, uid, kept_until="2000-01-01T00:00:00+00:00",
        name="Old", payload_json='{"row_count": 1}',
    )
    assert jobs.get_kept_payload(jid) is not None
    from datetime import datetime, timezone
    assert jobs.prune_expired_kept(now=datetime(2026, 8, 31, tzinfo=timezone.utc)) == 1
    assert jobs.get_kept_payload(jid) is None
    assert jobs.get(jid).kept_until is None


def test_job_prune_skips_queued_and_live_kept(db):
    uid = UserRepository(db).upsert("a@x.com", display_name="A", role="admin").id
    jobs = JobRepository(db)
    old = jobs.enqueue("report.run", owner_user_id=uid)
    kept = jobs.enqueue("report.run", owner_user_id=uid)
    queued = jobs.enqueue("report.run", owner_user_id=uid)
    assert jobs.claim_next().id == old
    jobs.mark_success(old, "x")
    assert jobs.claim_next().id == kept
    jobs.mark_success(kept, "y")
    jobs.keep_run(
        kept, uid, kept_until="2099-01-01T00:00:00+00:00",
        name="Keep", payload_json='{"row_count": 1}',
    )
    with db.precious() as conn:
        conn.execute(
            "UPDATE jobs SET created_at=datetime('now', '-100 days') WHERE id IN (?, ?)",
            (old, kept),
        )
    assert jobs.prune() == 1
    assert jobs.get(queued) is not None
    assert jobs.get(old) is None
    assert jobs.get(kept) is not None
    assert jobs.get_kept_payload(kept)["row_count"] == 1


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


def test_recover_orphans_cancels_delivery_not_requeued(db):
    jobs = JobRepository(db)
    jid = jobs.enqueue("report.deliver")
    assert jobs.claim_next().id == jid
    assert jobs.recover_orphans() == 0
    row = jobs.get(jid)
    assert row.status == "cancelled"
    assert "not retried" in row.error
    jobs.mark_success(jid, "late-send")
    assert jobs.get(jid).status == "cancelled"


def test_recover_orphans_cancels_schedule_run_not_requeued(db):
    jobs = JobRepository(db)
    jid = jobs.enqueue("schedule.run")
    assert jobs.claim_next().id == jid
    assert jobs.recover_orphans() == 0
    row = jobs.get(jid)
    assert row.status == "cancelled"
    assert "not retried" in row.error
    jobs.mark_success(jid, "late-send")
    assert jobs.get(jid).status == "cancelled"


def test_recover_orphans_cancels_delivery_at_retry_cap(db):
    jobs = JobRepository(db)
    jid = jobs.enqueue("report.deliver")
    jobs.claim_next()
    with db.precious() as conn:
        conn.execute("UPDATE jobs SET attempts=1 WHERE id=?", (jid,))
    assert jobs.recover_orphans() == 0
    row = jobs.get(jid)
    assert row.status == "cancelled"
    assert "not retried" in row.error
    assert "ran out of memory" not in row.error
    jobs.mark_success(jid, "late-send")
    assert jobs.get(jid).status == "cancelled"


def test_recover_orphans_cancels_schedule_run_at_retry_cap(db):
    jobs = JobRepository(db)
    jid = jobs.enqueue("schedule.run")
    jobs.claim_next()
    with db.precious() as conn:
        conn.execute("UPDATE jobs SET attempts=1 WHERE id=?", (jid,))
    assert jobs.recover_orphans() == 0
    row = jobs.get(jid)
    assert row.status == "cancelled"
    assert "not retried" in row.error
    assert "ran out of memory" not in row.error
    jobs.mark_success(jid, "late-send")
    assert jobs.get(jid).status == "cancelled"


def test_child_timeout_cancels_and_kills(db, monkeypatch):
    import subprocess as sp

    class FakeProc:
        def __init__(self, *a, **k):
            self.pid = 4242

        def wait(self, timeout=None):
            raise sp.TimeoutExpired("python -m web.jobs.child", timeout)

        def kill(self):
            return None

    killed = []
    monkeypatch.setattr("web.jobs.worker.subprocess.Popen", FakeProc)
    monkeypatch.setattr("web.jobs.worker.os.killpg", lambda pid, sig: killed.append((pid, sig)))
    worker = JobWorker(db)
    worker.register("echo", lambda ctx: "ok")
    jid = JobRepository(db).enqueue("echo")
    assert worker.process_next_child(timeout=0.05) == jid
    done = JobRepository(db).get(jid)
    assert done.status == "cancelled" and "Timed out" in done.error
    assert killed and killed[0][0] == 4242


def test_two_hung_children_do_not_stop_the_queue(db, monkeypatch):
    import subprocess as sp

    class FakeProc:
        def __init__(self, *a, **k):
            self.pid = 99

        def wait(self, timeout=None):
            raise sp.TimeoutExpired("child", timeout)

        def kill(self):
            return None

    monkeypatch.setattr("web.jobs.worker.subprocess.Popen", FakeProc)
    monkeypatch.setattr("web.jobs.worker.os.killpg", lambda pid, sig: None)
    jobs = JobRepository(db)
    worker = JobWorker(db)
    worker.register("echo", lambda ctx: "ok")
    a = jobs.enqueue("echo")
    b = jobs.enqueue("echo")
    c = jobs.enqueue("echo")
    worker.process_next_child(timeout=0.05)
    worker.process_next_child(timeout=0.05)
    assert jobs.get(a).status == "cancelled"
    assert jobs.get(b).status == "cancelled"
    worker.process_next()
    assert jobs.get(c).status == "success"


def test_worker_heartbeat_stays_fresh_while_child_wait_blocks(db, monkeypatch):
    """A long child wait must still write worker_heartbeat (Loop A F2)."""
    import subprocess as sp

    from web.data.repositories.app_settings import AppSettingsRepository

    class SlowProc:
        def __init__(self, *a, **k):
            self.pid = 7
            self.elapsed = 0.0

        def wait(self, timeout=None):
            chunk = 0.05 if timeout is None else min(float(timeout), 0.05)
            time.sleep(chunk)
            self.elapsed += chunk
            if self.elapsed >= 0.2:
                return 0
            raise sp.TimeoutExpired("child", timeout)

        def kill(self):
            return None

    monkeypatch.setattr("web.jobs.worker.subprocess.Popen", SlowProc)
    jobs = JobRepository(db)
    settings = AppSettingsRepository(db)
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO app_settings(key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("worker_heartbeat", "2000-01-01T00:00:00+00:00"),
        )
    worker = JobWorker(db)
    worker.register("echo", lambda ctx: "ok")
    jid = jobs.enqueue("echo")
    assert worker.process_next_child(timeout=5) == jid
    age = settings.heartbeat_age_seconds("worker_heartbeat")
    assert age is not None and age < 5
    assert jobs.get(jid).status == "running"  # fake child never ran the handler


def test_worker_stop_leaves_safe_job_running_for_recovery(db, monkeypatch):
    """SIGTERM/stop must not fail a safe job the next worker can requeue (Loop A R1)."""
    import subprocess as sp

    killed = threading.Event()

    class FakeProc:
        def __init__(self, *a, **k):
            self.pid = 11

        def wait(self, timeout=None):
            if killed.wait(timeout if timeout else 30):
                return -9
            raise sp.TimeoutExpired("child", timeout)

        def kill(self):
            killed.set()

    monkeypatch.setattr("web.jobs.worker.subprocess.Popen", FakeProc)
    monkeypatch.setattr("web.jobs.worker.os.killpg", lambda pid, sig: killed.set())
    jobs = JobRepository(db)
    worker = JobWorker(db)
    jid = jobs.enqueue("report.run")
    thread = threading.Thread(target=lambda: worker.process_next_child(timeout=5))
    thread.start()
    deadline = time.time() + 2
    while worker._child_proc is None and time.time() < deadline:
        time.sleep(0.01)
    assert worker._child_proc is not None
    worker.stop()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert jobs.get(jid).status == "running"
    assert jobs.recover_orphans() == 1
    assert jobs.get(jid).status == "queued"


def test_worker_stop_lets_recover_cancel_in_flight_delivery(db, monkeypatch):
    import subprocess as sp

    killed = threading.Event()

    class FakeProc:
        def __init__(self, *a, **k):
            self.pid = 12

        def wait(self, timeout=None):
            if killed.wait(timeout if timeout else 30):
                return -9
            raise sp.TimeoutExpired("child", timeout)

        def kill(self):
            killed.set()

    monkeypatch.setattr("web.jobs.worker.subprocess.Popen", FakeProc)
    monkeypatch.setattr("web.jobs.worker.os.killpg", lambda pid, sig: killed.set())
    jobs = JobRepository(db)
    worker = JobWorker(db)
    jid = jobs.enqueue("report.deliver")
    thread = threading.Thread(target=lambda: worker.process_next_child(timeout=5))
    thread.start()
    deadline = time.time() + 2
    while worker._child_proc is None and time.time() < deadline:
        time.sleep(0.01)
    assert worker._child_proc is not None
    worker.stop()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert jobs.get(jid).status == "running"
    assert jobs.recover_orphans() == 0
    assert jobs.get(jid).status == "cancelled"


def test_nonzero_child_exit_still_fails_when_worker_is_not_stopping(db, monkeypatch):
    class FakeProc:
        def __init__(self, *a, **k):
            self.pid = 13

        def wait(self, timeout=None):
            return 1

        def kill(self):
            return None

    monkeypatch.setattr("web.jobs.worker.subprocess.Popen", FakeProc)
    jobs = JobRepository(db)
    worker = JobWorker(db)
    jid = jobs.enqueue("echo")
    assert worker.process_next_child(timeout=5) == jid
    done = jobs.get(jid)
    assert done.status == "failure"
    assert "exited 1" in done.error


def test_nonzero_child_exit_cancels_delivery_not_failed(db, monkeypatch):
    class FakeProc:
        def __init__(self, *a, **k):
            self.pid = 14

        def wait(self, timeout=None):
            return -9

        def kill(self):
            return None

    monkeypatch.setattr("web.jobs.worker.subprocess.Popen", FakeProc)
    jobs = JobRepository(db)
    worker = JobWorker(db)
    for job_type in ("report.deliver", "schedule.run"):
        jid = jobs.enqueue(job_type)
        assert worker.process_next_child(timeout=5) == jid
        row = jobs.get(jid)
        assert row.status == "cancelled", job_type
        assert "not retried" in row.error
        assert "ran out of memory" not in row.error
        jobs.mark_success(jid, "late-send")
        assert jobs.get(jid).status == "cancelled"


def test_child_timeout_settles_sending_email_unknown(db, monkeypatch):
    import subprocess as sp

    from web.data.repositories.delivery_legs import DeliveryLegRepository, attempt_key
    from web.delivery.states import UNKNOWN

    class FakeProc:
        def __init__(self, *a, **k):
            self.pid = 88

        def wait(self, timeout=None):
            raise sp.TimeoutExpired("python -m web.jobs.child", timeout)

        def kill(self):
            return None

    monkeypatch.setattr("web.jobs.worker.subprocess.Popen", FakeProc)
    monkeypatch.setattr("web.jobs.worker.os.killpg", lambda pid, sig: None)
    jobs = JobRepository(db)
    worker = JobWorker(db)
    worker.register("schedule.run", lambda ctx: "ok")
    jid = jobs.enqueue("schedule.run")
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="email", target="a@x.com")
    legs.prepare(key, run_id=1, kind="email", target="a@x.com", job_id=jid, slot_id="s1")
    legs.mark_sending(key)
    assert worker.process_next_child(timeout=0.05) == jid
    assert jobs.get(jid).status == "cancelled"
    assert legs.get(key).status == UNKNOWN


def test_nonzero_child_exit_settles_sending_email_unknown(db, monkeypatch):
    from web.data.repositories.delivery_legs import DeliveryLegRepository, attempt_key
    from web.delivery.states import UNKNOWN

    class FakeProc:
        def __init__(self, *a, **k):
            self.pid = 14

        def wait(self, timeout=None):
            return -9

        def kill(self):
            return None

    monkeypatch.setattr("web.jobs.worker.subprocess.Popen", FakeProc)
    jobs = JobRepository(db)
    worker = JobWorker(db)
    jid = jobs.enqueue("schedule.run")
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="email", target="a@x.com")
    legs.prepare(key, run_id=1, kind="email", target="a@x.com", job_id=jid, slot_id="s1")
    legs.mark_sending(key)
    assert worker.process_next_child(timeout=5) == jid
    assert jobs.get(jid).status == "cancelled"
    assert legs.get(key).status == UNKNOWN


def test_kill_child_terminates_a_real_process(db):
    import subprocess as sp
    import sys

    worker = JobWorker(db)
    proc = sp.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    worker._kill_child(proc)
    assert proc.poll() is not None
