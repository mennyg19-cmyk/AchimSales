"""Process ownership: bootstrap (migrate+seed) vs worker (jobs+scheduler).

Flask/Gunicorn must not call either. The supervisor runs bootstrap, then
starts Gunicorn and ``python -m web.worker_main`` as siblings.
"""
from __future__ import annotations

import os

from flask import Flask

from web.seeds import (
    _AZURE_SCHEDULES,
    _LIVE_RUNBOOK_SCHEDULES,
    _seed_admins,
    _seed_company_views,
    _seed_developers,
    _seed_feature_flags,
    _seed_master_schedules,
    _seed_report_config,
)


def home_app() -> Flask:
    """Same home-site app Azure Gunicorn serves (is_beta=True)."""
    from web import create_app
    from web.config import load_config

    return create_app(load_config(is_beta=True))


def run_bootstrap(app: Flask) -> None:
    """Migrations and one-time seeds. No worker, scheduler, or threads."""
    from web.data.migrate import migrate

    db = app.config["DB"]
    migrate(db)
    _seed_feature_flags(app, db)
    _seed_report_config(app, db)
    _seed_admins(app, db)
    _seed_developers(app, db)
    cfg = app.config["APP_CONFIG"]
    if getattr(cfg, "is_beta", False):
        _seed_master_schedules(app, db, _LIVE_RUNBOOK_SCHEDULES, inactive=True)
    else:
        _seed_master_schedules(app, db, _AZURE_SCHEDULES)
    _seed_company_views(app, db)


def run_bootstrap_cli(app: Flask) -> None:
    """run_bootstrap, and write/clear the readiness marker."""
    from web.blueprints.health import bootstrap_failed_marker

    marker = bootstrap_failed_marker(app.config["APP_CONFIG"])
    try:
        run_bootstrap(app)
        marker.unlink(missing_ok=True)
    except Exception:
        try:
            marker.write_text("bootstrap failed\n", encoding="utf-8")
        except Exception:  # noqa: BLE001 - readiness still has other signals
            pass
        raise


# Tests inspect this name; it must stay migrate+seed only (no Live DB copy).
bootstrap_background = run_bootstrap


def run_worker(app: Flask) -> None:
    """Own jobs, scheduler, lookup mirror, and heartbeats until SIGTERM."""
    if not _is_background_leader(app):
        raise SystemExit("v3 worker: background lock is held by another process")
    app.logger.info("v3 worker ownership acquired (pid=%s)", os.getpid())
    db = app.config["DB"]
    if not app.config["APP_CONFIG"].dashboard_refresh_enabled:
        _cancel_pending_dashboard_refreshes(app, db)
    _start_scheduler(app, db)
    worker = app.config.get("JOB_WORKER")
    if worker is None:
        raise RuntimeError("JOB_WORKER is not registered on the app")
    worker.run_forever()


# Held open for the whole process lifetime so the advisory lock below stays held.
_BG_LOCK_FH = None


def is_background_leader_process() -> bool:
    """True in the one process that won the background lock (the job worker)."""
    return _BG_LOCK_FH is not None


def _is_background_leader(app: Flask) -> bool:
    """Elect exactly ONE process to own jobs + cron.

    Fail-open to leader=True when fcntl is unavailable (Windows/local dev).
    """
    global _BG_LOCK_FH
    try:
        import fcntl
    except Exception:  # noqa: BLE001 - non-POSIX (local dev): single process owns it
        return True
    cfg = app.config["APP_CONFIG"]
    lock_path = cfg.precious_db_path.parent / f".v3-background.{cfg.precious_db_path.stem}.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock_path, "w")  # noqa: SIM115 - intentionally kept open
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    except Exception:  # noqa: BLE001 - unexpected lock error: do not start a second worker
        app.logger.exception("v3 background lock errored; refusing worker start")
        return False
    _BG_LOCK_FH = fh
    return True


def _cancel_pending_dashboard_refreshes(app: Flask, db) -> None:
    """Dashboard UI off: cancel leftover dashboard.refresh jobs (not lookups.refresh)."""
    from web.dashboard.jobs import DASHBOARD_REFRESH_JOB_TYPE

    try:
        with db.precious() as conn:
            n = conn.execute(
                "UPDATE jobs SET status='cancelled', finished_at=datetime('now')"
                " WHERE type=? AND status IN ('queued','running')",
                (DASHBOARD_REFRESH_JOB_TYPE,),
            ).rowcount
        if n:
            app.logger.info("dashboard refresh off: cancelled %d pending refresh job(s)", n)
    except Exception:  # noqa: BLE001 - cleanup is best-effort; never block worker start
        app.logger.exception("dashboard refresh cleanup failed")


def _start_scheduler(app: Flask, db) -> None:
    """Start the once-a-minute cron. Failure must propagate (readiness depends on it)."""
    from web.dashboard.jobs import enqueue_lookups_refresh, enqueue_refresh
    from web.jobs.scheduler import Scheduler
    from web.scheduling.tick import make_tick

    job_repo = app.config["JOB_REPO"]
    dashboard_on = app.config["APP_CONFIG"].dashboard_refresh_enabled

    def _tick_mirror():
        try:
            enqueue_refresh(job_repo)
        except Exception:  # noqa: BLE001 - a tick failure must not kill the scheduler
            app.logger.exception("dashboard mirror tick failed")

    def _tick_lookups():
        try:
            enqueue_lookups_refresh(job_repo)
        except Exception:  # noqa: BLE001 - a tick failure must not kill the scheduler
            app.logger.exception("lookups mirror tick failed")

    scheduler = Scheduler()
    scheduler.add_cron("schedule-tick", make_tick(db, job_repo), minute="*")
    if dashboard_on:
        scheduler.add_cron("dashboard-mirror", _tick_mirror, hour="*/4", minute=5)
    else:
        # Home site: dashboard UI is off, but salesman/customer dropdowns still
        # need customer_master in sqlite. HTTP must not start a populate thread.
        scheduler.add_cron("lookups-mirror", _tick_lookups, hour="*/4", minute=5)
    scheduler.start()
    app.config["SCHEDULER"] = scheduler
    from web.data.repositories.app_settings import AppSettingsRepository
    try:
        AppSettingsRepository(db).beat_scheduler()
    except Exception:  # noqa: BLE001 - first beat must not hide a started scheduler
        app.logger.exception("initial scheduler heartbeat failed")
    app.logger.info("schedule cron started (dashboard mirror %s)",
                    "on" if dashboard_on else "OFF; lookups mirror on")

    try:
        empty = app.config["DASHBOARD_REPO"].count() == 0
    except Exception:  # noqa: BLE001 - prime is best-effort
        app.logger.exception("dashboard mirror count failed")
        return
    if not empty:
        return
    try:
        if dashboard_on:
            enqueue_refresh(job_repo)
        else:
            enqueue_lookups_refresh(job_repo)
    except Exception:  # noqa: BLE001 - best-effort prime
        app.logger.exception("mirror prime failed")
