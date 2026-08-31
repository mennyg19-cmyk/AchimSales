"""Phase 4: HTTP process does not own jobs; bootstrap and worker are separate."""

from __future__ import annotations

import inspect
import threading
from pathlib import Path

from web import create_app
from web.background import bootstrap_background, run_bootstrap, run_worker
from web.config import Config
from web.data.migrate import migrate
from web.data.repositories.jobs import JobRepository


def _cfg(tmp_path, *, is_prod=False) -> Config:
    kwargs = dict(
        app_env="prod" if is_prod else "dev",
        auth_mode="msal" if is_prod else "dev",
        flask_secret="test-secret",
        tenant_id="t" if is_prod else "",
        client_id="c" if is_prod else "",
        client_secret="s" if is_prod else "",
        reporting_api_base_url="https://api.example" if is_prod else "",
        reporting_api_key="k" if is_prod else "",
        precious_db_path=tmp_path / "precious.db",
        cache_db_path=tmp_path / "cache.db",
        litestream_blob_url="",
        is_beta=True,
    )
    if is_prod:
        kwargs.update(
            litestream_azure_account_name="acct",
            litestream_azure_account_key="key",
            litestream_azure_container="container",
        )
    return Config(**kwargs)


def test_create_app_starts_no_job_poller_or_lookup_thread(tmp_path):
    before = {id(t): t.name for t in threading.enumerate()}
    app = create_app(_cfg(tmp_path))
    new_names = [t.name for t in threading.enumerate() if id(t) not in before]
    assert app.config["JOB_WORKER"].running is False
    assert app.config.get("SCHEDULER") is None
    assert not any(
        n.startswith("job") or n.startswith("v3-") or "APScheduler" in n
        for n in new_names
    )


def test_wsgi_source_does_not_start_threads():
    src = (Path(__file__).resolve().parents[2] / "wsgi.py").read_text(encoding="utf-8")
    assert "threading" not in src
    assert "bootstrap_background" not in src
    assert "_bootstrap_async" not in src


def test_lookup_status_does_not_start_a_thread(tmp_path):
    app = create_app(_cfg(tmp_path))
    before = {id(t) for t in threading.enumerate()}
    status = app.config["LOOKUP_SERVICE"].status()
    new = [t.name for t in threading.enumerate() if id(t) not in before]
    assert status["status"] in ("idle", "ready")
    assert "v3-lookups" not in new


def test_bootstrap_cli_migrates_and_does_not_start_worker(tmp_path):
    app = create_app(_cfg(tmp_path))
    result = app.test_cli_runner().invoke(args=["bootstrap"])
    assert result.exit_code == 0, result.output
    with app.config["DB"].precious() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "users" in tables
    assert app.config["JOB_WORKER"].running is False


def test_run_bootstrap_is_migrate_and_seed_only():
    src = inspect.getsource(run_bootstrap)
    assert "worker.start" not in src
    assert "run_forever" not in src
    assert "_start_scheduler" not in src
    src_alias = inspect.getsource(bootstrap_background)
    assert "seed_users_from_live" not in src_alias


def test_worker_claims_a_job_separate_from_create_app(tmp_path):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    worker = app.config["JOB_WORKER"]
    seen = []
    worker.register("probe", lambda ctx: seen.append(ctx.job.id) or "ok")
    jid = JobRepository(app.config["DB"]).enqueue("probe")
    assert worker.process_next() == jid
    assert seen == [jid]
    assert JobRepository(app.config["DB"]).get(jid).status == "success"


def test_child_entry_runs_already_claimed_job(tmp_path, monkeypatch):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    monkeypatch.setattr("web.background.home_app", lambda: app)
    jobs = JobRepository(app.config["DB"])
    jid = jobs.enqueue("missing-handler")
    jobs.claim_next()
    from web.jobs.child import main

    assert main([jid]) == 0
    assert jobs.get(jid).status == "failure"
    assert "no handler" in jobs.get(jid).error


def test_scheduler_start_failure_stops_the_worker(tmp_path, monkeypatch):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])

    def boom(self):
        raise RuntimeError("apscheduler missing")

    monkeypatch.setattr("web.jobs.scheduler.Scheduler.start", boom)
    try:
        run_worker(app)
        raise AssertionError("run_worker should have raised")
    except RuntimeError as exc:
        assert "apscheduler missing" in str(exc)
    assert app.config["JOB_WORKER"].running is False
