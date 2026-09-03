"""Worker-owned cleanup for disposable report data."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from web.data.connection import Database
from web.data.repositories.delivery_legs import DeliveryLegRepository
from web.data.repositories.exports import ExportRepository
from web.jobs import status
from web.jobs.keep import _kept_still_valid
from web.reporting.cache import ReportCache

log = logging.getLogger(__name__)

CACHE_MAX_AGE_SECONDS = 7 * 86400


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
    status.mark_cleanup(db)
    counts = {
        "cache_rows": cache_rows,
        "export_rows": export_rows,
        "delivery_leg_rows": delivery_leg_rows,
    }
    log.info(
        "worker cleanup removed %(cache_rows)d cache rows, %(export_rows)d exports,"
        " and %(delivery_leg_rows)d delivery legs",
        counts,
    )
    return counts
