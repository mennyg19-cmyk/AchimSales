"""Worker-owned cleanup for disposable report data."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from web.data.connection import Database
from web.data.repositories.delivery_legs import DeliveryLegRepository
from web.data.repositories.exports import ExportRepository
from web.data.repositories.jobs import JobRepository
from web.data.repositories.run_log import ReportRunLogRepository
from web.jobs import status
from web.jobs.keep import _kept_still_valid
from web.reporting.cache import ReportCache

log = logging.getLogger(__name__)

CACHE_MAX_AGE_SECONDS = 7 * 86400
RETENTION_DAYS = 90


def _kept_cache_keys(db: Database) -> tuple[set[str], set[str]]:
    protected_keys: set[str] = set()
    expired_keys: set[str] = set()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with db.precious() as conn:
        rows = conn.execute(
            "SELECT result_ref, kept_until FROM jobs"
            " WHERE type='report.run' AND status='success'"
            " AND kept_until IS NOT NULL AND kept_until != ''"
            " AND result_ref IS NOT NULL AND result_ref != ''"
        ).fetchall()
    for row in rows:
        if _kept_still_valid(row["kept_until"], now):
            protected_keys.add(row["result_ref"])
        else:
            expired_keys.add(row["result_ref"])
    return protected_keys, expired_keys


def run_cleanup(db: Database) -> dict[str, int]:
    protected_keys, expired_kept_keys = _kept_cache_keys(db)
    cache_rows = ReportCache(db).prune(
        older_than_seconds=CACHE_MAX_AGE_SECONDS,
        protected_keys=protected_keys,
        expired_kept_keys=expired_kept_keys,
    )
    export_rows = ExportRepository(db).prune()
    delivery_leg_rows = DeliveryLegRepository(db).prune()
    job_rows = JobRepository(db).prune_terminal_older_than(
        older_than_days=RETENTION_DAYS,
        kept_still_valid=_kept_still_valid,
    )
    run_log_rows = ReportRunLogRepository(db).prune(older_than_days=RETENTION_DAYS)
    with db.precious() as conn:
        magic_link_token_rows = conn.execute(
            "DELETE FROM magic_link_tokens WHERE julianday(created_at) < julianday(?)",
            ((datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat(),),
        ).rowcount
    status.mark_cleanup(db)
    counts = {
        "cache_rows": cache_rows,
        "export_rows": export_rows,
        "delivery_leg_rows": delivery_leg_rows,
        "job_rows": job_rows,
        "run_log_rows": run_log_rows,
        "magic_link_token_rows": magic_link_token_rows,
    }
    log.info(
        "worker cleanup removed %(cache_rows)d cache rows, %(export_rows)d exports,"
        " %(delivery_leg_rows)d delivery legs, %(job_rows)d jobs,"
        " %(run_log_rows)d run-log rows, and %(magic_link_token_rows)d magic-link tokens",
        counts,
    )
    return counts
