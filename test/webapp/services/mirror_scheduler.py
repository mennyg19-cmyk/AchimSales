"""APScheduler wiring for the offline mirror's daily refresh.

What this does
==============

1. Schedules a daily job at **00:00 America/New_York** that pulls the
   full unfiltered snapshot from each in-app report (customer_master,
   salesline_release) and upserts every row into the local SQLite
   mirror.

2. The jobstore lives in the same SQLite database the rest of the app
   uses (``APP_DB_PATH``), so scheduled jobs survive container
   restarts. APScheduler tracks the next-fire time itself.

3. Resilience for missed runs:

   * ``coalesce=True`` + ``misfire_grace_time=6 hours`` covers
     short outages around midnight (the job replays automatically).
   * For longer outages, ``catchup_if_stale()`` runs at app boot:
     if the most recent successful refresh is more than 24 hours
     old, we kick the refresh immediately so we never sit on a
     gigantic gap.
   * ``run_now()`` is also exposed for the admin diag page so an
     operator can manually re-trigger the refresh whenever they want.

Single-process safety
---------------------

If the test app ever scales beyond one gunicorn worker, only the
*first* worker that boots should own the scheduler -- otherwise N
workers will fire N concurrent refreshes at midnight. We guard with a
SQLite advisory row in ``feature_flags`` (``scheduler_owner_pid``)
that stores the owning PID + boot time. Other workers see the row
and skip starting the scheduler.

This is intentionally simple: if the owner process dies without
clearing the row, the next worker takes over after a TTL of 5
minutes. That's plenty for a single-instance App Service.
"""
from __future__ import annotations

import atexit
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from test.config.settings import APP_DB_PATH
from test.webapp.services import mirror, reporting_api

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Single-instance guard
# ---------------------------------------------------------------------------


_OWNER_KEY = "scheduler_owner"
_OWNER_TTL_S = 300  # 5 minutes


def _claim_owner() -> bool:
    """Try to claim ownership of the scheduler. True if we got it."""
    from test.webapp.db import connect

    pid = os.getpid()
    now = int(time.time())
    try:
        with connect() as conn:
            # Make sure the table can hold our marker.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduler_owner (
                    id           INTEGER PRIMARY KEY CHECK (id = 1),
                    owner_pid    INTEGER NOT NULL,
                    heartbeat_ts INTEGER NOT NULL
                )
                """
            )
            row = conn.execute(
                "SELECT owner_pid, heartbeat_ts FROM scheduler_owner WHERE id = 1"
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO scheduler_owner (id, owner_pid, heartbeat_ts) VALUES (1, ?, ?)",
                    (pid, now),
                )
                return True
            # Existing claim. Take it over if it's stale OR if we own it.
            if row["owner_pid"] == pid or (now - int(row["heartbeat_ts"])) > _OWNER_TTL_S:
                conn.execute(
                    "UPDATE scheduler_owner SET owner_pid = ?, heartbeat_ts = ? WHERE id = 1",
                    (pid, now),
                )
                return True
            return False
    except Exception:
        # If ANY of the above fails, default to "let it run" so we
        # never silently miss the daily refresh just because the SQLite
        # claim is broken.
        log.exception("scheduler owner claim failed; running anyway")
        return True


def _heartbeat() -> None:
    """Periodically update our heartbeat so we don't get evicted."""
    from test.webapp.db import connect

    pid = os.getpid()
    while True:
        try:
            with connect() as conn:
                conn.execute(
                    "UPDATE scheduler_owner SET heartbeat_ts = ? WHERE id = 1 AND owner_pid = ?",
                    (int(time.time()), pid),
                )
        except Exception:
            log.exception("scheduler heartbeat failed")
        time.sleep(60)


# ---------------------------------------------------------------------------
# Refresh job
# ---------------------------------------------------------------------------


def refresh_mirror_job(*, trigger: str = "cron",
                       triggered_by: str | None = None) -> dict[str, Any]:
    """The actual work the cron triggers.

    Pulls every wired report's full unfiltered snapshot and upserts
    into the mirror. Failures in one report don't stop the others.
    """
    log.info("mirror refresh: starting (trigger=%s)", trigger)
    started = time.monotonic()

    results: dict[str, Any] = {
        "trigger":      trigger,
        "started_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "customers":    None,
        "salesline":    None,
        "errors":       [],
    }

    if not reporting_api.is_configured():
        msg = ("mirror refresh skipped -- REPORTING_API_BASE_URL is "
               "not configured")
        log.warning(msg)
        results["errors"].append(msg)
        return results

    # 1) Customer master snapshot.
    try:
        rows = reporting_api.run("customer_master", {})
        stats = mirror.upsert_customers(
            rows, trigger=trigger, triggered_by=triggered_by,
        )
        results["customers"] = stats
        log.info("mirror refresh: customers %s", stats)
    except Exception as exc:
        msg = f"customer_master refresh failed: {exc}"
        log.exception(msg)
        results["errors"].append(msg)

    # 2) Salesline release snapshot for the rolling window.
    #
    # NOTE: an unfiltered salesline_release call returns months of
    # data and can be very slow. We intentionally pass no filters so
    # the SP returns its native default range (which the brother said
    # is appropriate for caching). The upsert helper drops anything
    # outside the rolling 60-day window before writing.
    try:
        rows = reporting_api.run("ordered", {"period": "all_time"})
        stats = mirror.upsert_salesline(
            rows, trigger=trigger, triggered_by=triggered_by,
        )
        results["salesline"] = stats
        log.info("mirror refresh: salesline %s", stats)
    except Exception as exc:
        msg = f"salesline_release refresh failed: {exc}"
        log.exception(msg)
        results["errors"].append(msg)

    elapsed = int((time.monotonic() - started) * 1000)
    results["elapsed_ms"] = elapsed
    log.info("mirror refresh: done in %d ms (errors=%d)", elapsed, len(results["errors"]))
    return results


# ---------------------------------------------------------------------------
# Catch-up at boot
# ---------------------------------------------------------------------------


def catchup_if_stale(*, max_age_hours: int = 24) -> bool:
    """If we haven't had a successful daily refresh recently, run one
    now in a worker thread. Returns True iff a catchup was kicked.
    """
    try:
        from test.webapp.db import connect

        with connect() as conn:
            row = conn.execute(
                "SELECT MAX(finished_utc) AS last_success "
                "FROM mirror_refresh_runs "
                "WHERE status = 'success' AND scope = 'customers'"
            ).fetchone()
        last = row["last_success"] if row else None
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                age_h = (datetime.now(timezone.utc)
                         - last_dt.astimezone(timezone.utc)).total_seconds() / 3600
                if age_h < max_age_hours:
                    log.info(
                        "mirror catchup: last success %.1fh ago -- skipping",
                        age_h,
                    )
                    return False
            except Exception:
                pass

        log.info("mirror catchup: kicking refresh in background thread")
        t = threading.Thread(
            target=refresh_mirror_job,
            kwargs={"trigger": "catchup"},
            name="mirror-catchup",
            daemon=True,
        )
        t.start()
        return True
    except Exception:
        log.exception("catchup_if_stale failed")
        return False


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


_scheduler = None
_started_lock = threading.Lock()


def start_scheduler() -> None:
    """Start the APScheduler if we own the lease.

    Safe to call multiple times -- subsequent calls are no-ops.
    """
    global _scheduler

    with _started_lock:
        if _scheduler is not None:
            return

        if not _claim_owner():
            log.info("mirror scheduler: another worker owns it -- not starting here")
            return

        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("America/New_York")
        except Exception:
            log.warning("mirror scheduler: zoneinfo missing -- using UTC")
            tz = timezone.utc

        # APScheduler can store its job state in the same SQLite file
        # the rest of the app uses (different table prefix). That way
        # the next-fire time survives container restarts. If SQLAlchemy
        # isn't installed (dev shell), fall back to the in-memory
        # jobstore -- the cron still fires while the process lives,
        # just no cross-restart replay.
        jobstores: dict = {}
        try:
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
            jobstores["default"] = SQLAlchemyJobStore(url=f"sqlite:///{APP_DB_PATH}")
            log.info("mirror scheduler: using persistent SQLAlchemyJobStore")
        except Exception as exc:
            log.warning(
                "mirror scheduler: SQLAlchemyJobStore unavailable (%s) -- "
                "falling back to in-memory jobstore (no cross-restart replay)",
                exc,
            )

        if jobstores:
            sched = BackgroundScheduler(jobstores=jobstores, timezone=tz)
        else:
            sched = BackgroundScheduler(timezone=tz)
        sched.add_job(
            refresh_mirror_job,
            trigger=CronTrigger(hour=0, minute=0, timezone=tz),
            id="mirror_daily_refresh",
            name="Mirror daily refresh (00:00 ET)",
            replace_existing=True,
            coalesce=True,                # collapse missed runs into one
            max_instances=1,              # never fire concurrently
            misfire_grace_time=6 * 3600,  # tolerate <=6h late starts
        )
        sched.start()
        _scheduler = sched

        # Heartbeat so other workers know we're still here.
        threading.Thread(target=_heartbeat, name="mirror-scheduler-hb",
                         daemon=True).start()

        # If we missed any cron windows while the app was down, catch up.
        catchup_if_stale()

        log.info("mirror scheduler: daily 00:00 America/New_York job armed")
        atexit.register(stop_scheduler)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            log.exception("mirror scheduler shutdown failed")
        _scheduler = None


def run_now(*, triggered_by: str | None = None) -> dict[str, Any]:
    """Manual refresh entry point used by the admin diag page."""
    return refresh_mirror_job(trigger="manual", triggered_by=triggered_by)


def next_run_at() -> str | None:
    """When is the next scheduled refresh? (None if scheduler isn't ours.)"""
    if _scheduler is None:
        return None
    job = _scheduler.get_job("mirror_daily_refresh")
    if job is None or job.next_run_time is None:
        return None
    return job.next_run_time.isoformat()
