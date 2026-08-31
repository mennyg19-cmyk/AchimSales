"""Background worker ownership: lock, scheduler, migrate+seed on boot."""
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

def bootstrap_background(app: Flask) -> None:
    """Prod-only side effects: migrate, seed admins/salesmen, start the worker.

    Kept OUT of create_app so tests can build an app without spawning threads or
    touching schema. The wsgi entrypoint calls this once per process. Seeding is
    individually guarded so a bad data file can never stop the app from booting.
    """
    from web.data.migrate import migrate

    db = app.config["DB"]
    migrate(db)
    _seed_feature_flags(app, db)      # default flags so nav gating is deterministic
    _seed_report_config(app, db)
    _seed_admins(app, db)             # explicit env admins
    _seed_developers(app, db)         # explicit env developers win last (outrank admin)
    cfg = app.config["APP_CONFIG"]
    if getattr(cfg, "is_beta", False):
        _seed_master_schedules(app, db, _LIVE_RUNBOOK_SCHEDULES, inactive=True)
    else:
        _seed_master_schedules(app, db, _AZURE_SCHEDULES)
    _seed_company_views(app, db)

    # Background OWNERSHIP (the job worker + the cron scheduler + orphan recovery)
    # must run in exactly ONE process. Under gunicorn we have multiple workers, so
    # we elect a single owner with an exclusive OS file lock (see
    # _is_background_leader). Without this, every worker's recover_orphans() would
    # requeue jobs another worker is actively running -> duplicate report
    # deliveries + schedule fires.
    if _is_background_leader(app):
        app.logger.info("v3 background ownership acquired by this worker (pid=%s)", os.getpid())
        worker = app.config.get("JOB_WORKER")
        if worker is not None:
            worker.start()
        if not app.config["APP_CONFIG"].dashboard_refresh_enabled:
            _cancel_pending_dashboard_refreshes(app, db)
        # Schedule cron on Live and Beta (each mount has its own precious DB).
        _start_scheduler(app, db)
    else:
        app.logger.info("v3 background ownership held by another worker; skipping (pid=%s)", os.getpid())


# Held open for the whole process lifetime so the advisory lock below stays held.
_BG_LOCK_FH = None


def is_background_leader_process() -> bool:
    """True in the one gunicorn worker that won the background lock (and therefore
    actually runs the job poller + scheduler). Lets the admin diagnostic say
    whether it's talking to the leader or a follower."""
    return _BG_LOCK_FH is not None


def _is_background_leader(app: Flask) -> bool:
    """Elect exactly ONE process to own v3 background work (job worker + cron).

    Uses a real OS advisory lock instead of the gunicorn env signal. That signal
    depends on post_fork setting the env BEFORE the worker imports the app, which
    is unreliable in our dispatcher: the live app is imported during the worker's
    synchronous load while v3 bootstraps in a later daemon thread, so the two read
    different env values (observed in prod). An exclusive, non-blocking flock is
    immune to that ordering - the one worker that grabs it wins and holds it until
    the process dies.

    Fail-open to leader=True when fcntl is unavailable (Windows/local dev) or the
    lock can't be taken for an unexpected reason, so single-process/dev still runs
    background work.
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
        return False  # another worker already holds the lock
    except Exception:  # noqa: BLE001 - never block boot on an unexpected lock error
        app.logger.exception("v3 background lock errored; assuming leader")
        return True
    _BG_LOCK_FH = fh  # keep the handle alive so GC can't drop the lock
    return True


def _cancel_pending_dashboard_refreshes(app: Flask, db) -> None:
    """With the dashboard off, cancel any queued/running dashboard.refresh jobs so
    orphan-recovery doesn't resurrect one that's stuck on a slow Reporting API and
    keep tying up a worker slot."""
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
    except Exception:  # noqa: BLE001 - cleanup is best-effort; never block boot
        app.logger.exception("dashboard refresh cleanup failed")


def _start_scheduler(app: Flask, db) -> None:
    """Start the once-a-minute cron tick that enqueues due schedules.

    Best-effort: if APScheduler isn't installed (e.g. some local envs) the tick
    simply doesn't run - schedules can still be triggered with "Send now" - and
    boot is never blocked.
    """
    from web.dashboard.jobs import enqueue_refresh
    from web.jobs.scheduler import Scheduler
    from web.scheduling.tick import make_tick

    job_repo = app.config["JOB_REPO"]
    dashboard_on = app.config["APP_CONFIG"].dashboard_refresh_enabled

    def _tick_mirror():
        try:
            enqueue_refresh(job_repo)
        except Exception:  # noqa: BLE001 - a tick failure must not kill the scheduler
            app.logger.exception("dashboard mirror tick failed")

    try:
        scheduler = Scheduler()
        scheduler.add_cron("schedule-tick", make_tick(db, job_repo), minute="*")
        # Dashboard customer mirror: rebuild every 4 hours (LIVE cadence). Skipped
        # entirely when the dashboard refresh is turned off.
        if dashboard_on:
            scheduler.add_cron("dashboard-mirror", _tick_mirror, hour="*/4", minute=5)
        scheduler.start()
        app.config["SCHEDULER"] = scheduler
        app.logger.info("schedule cron started (dashboard mirror %s)",
                        "on" if dashboard_on else "OFF")
    except Exception:  # noqa: BLE001 - scheduler is optional; never block boot
        app.logger.exception("scheduler start failed (schedules will only run via Send now)")

    # Prime the mirror on boot if it's empty so the dashboard isn't blank on a
    # cold container (LIVE does an immediate refresh when the cache is empty).
    if not dashboard_on:
        return
    try:
        if app.config["DASHBOARD_REPO"].count() == 0:
            enqueue_refresh(job_repo)
    except Exception:  # noqa: BLE001 - best-effort prime
        app.logger.exception("dashboard mirror prime failed")
