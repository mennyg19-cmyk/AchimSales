"""Registers every background job handler with the registry."""

# === What's in this file ===
# One place that wires job-type names to the functions that run them, so both
# the in-process worker and the separate worker process register the same set.
# The report-run handler is added in the report-engine milestone; for now this
# registers the housekeeping job that trims old cached results.
#
# register_all() -- attach all known handlers to the registry
# _cache_cleanup() -- delete cached report snapshots older than the retention window

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from .types import JOB_CACHE_CLEANUP, HandlerRegistry, JobContext

log = logging.getLogger("rebuild.worker")

_SNAPSHOT_RETENTION_DAYS = 7


def _cache_cleanup(ctx: JobContext) -> Optional[str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_SNAPSHOT_RETENTION_DAYS)).isoformat()
    with ctx.db.cache() as conn:
        conn.execute("DELETE FROM report_snapshots WHERE created_at < ?", (cutoff,))
    return None


def register_all(registry: HandlerRegistry) -> None:
    registry.register(JOB_CACHE_CLEANUP, _cache_cleanup)
    # report.run and report.export handlers are registered by the reports module.
