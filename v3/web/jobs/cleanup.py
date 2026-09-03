"""Worker-owned cleanup for disposable report data."""

from __future__ import annotations

import logging

from web.data.connection import Database
from web.data.repositories.exports import ExportRepository
from web.jobs import status
from web.reporting.cache import ReportCache

log = logging.getLogger(__name__)

CACHE_MAX_AGE_SECONDS = 7 * 86400


def run_cleanup(db: Database) -> dict[str, int]:
    cache_rows = ReportCache(db).prune(older_than_seconds=CACHE_MAX_AGE_SECONDS)
    export_rows = ExportRepository(db).prune()
    status.mark_cleanup(db)
    counts = {"cache_rows": cache_rows, "export_rows": export_rows}
    log.info("worker cleanup removed %(cache_rows)d cache rows and %(export_rows)d exports", counts)
    return counts
