"""Runs one report end to end: call the SP, clean rows, build tabs, cache it."""

# === What's in this file ===
# This is the job handler the worker calls for a report run. It ties the pieces
# together: load the report's definition, translate the filters into SP
# parameters, call the Reporting API, clean the rows, build the tabs, and save
# the result to the cache under the job's cache key. The web side then reads
# that cache key to show the report.
#
# run_report_job() -- the report.run handler (returns the cache key it wrote)
# register() -- attach run_report_job to the worker's registry

from __future__ import annotations

import logging
import time

from ..data.connection import utc_now_iso
from ..data.repositories.run_log import RunLogRepository
from ..jobs.types import JOB_REPORT_RUN, HandlerRegistry, JobContext
from .adapter import normalize
from .api_client import ReportingApiClient
from .cache import ResultCache, build_cache_key
from .config_loader import ConfigLoader
from .engine import build_tabs
from .params import translate
from .transforms import TRANSFORMS

log = logging.getLogger("rebuild.reports.runner")


def run_report_job(ctx: JobContext) -> str | None:
    job = ctx.job
    config = ctx.config
    db = ctx.db
    started = time.monotonic()

    report_config = ConfigLoader(db).load_runnable(job.report_key)
    filters = (job.params or {}).get("filters") or {}
    sp_params = translate(job.report_key, filters)

    client = ReportingApiClient(
        config.reporting_api_base_url,
        config.reporting_api_key,
        timeout=config.reporting_api_timeout,
    )
    result = client.run_report(report_config.sp_name, sp_params)

    if ctx.cancelled():
        log.info("job %s cancelled after fetch; not building", job.id)
        return None

    if result.row_count > config.max_result_rows:
        raise ValueError(
            f"This report returned {result.row_count:,} rows, over the current "
            f"{config.max_result_rows:,}-row limit. Narrow the date range and run it again."
        )

    rows = normalize(job.report_key, result.rows)
    tabs = build_tabs(rows, report_config.tabs, transforms=TRANSFORMS, params={"filters": filters, "sp_params": sp_params})

    snapshot = {
        "report_key": job.report_key,
        "title": report_config.title,
        "generated_at": utc_now_iso(),
        "params": filters,
        "row_count": result.row_count,
        "provisional": True,
        "tabs": tabs,
    }

    cache_key = job.cache_key or build_cache_key(job.report_key, job.requested_by, job.scope_token, sp_params)
    ResultCache(db).store(cache_key, job.report_key, snapshot)

    RunLogRepository(db).record(
        "report.run",
        user_email=job.requested_by,
        report_key=job.report_key,
        job_id=job.id,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="done",
        message=f"{result.row_count} rows, {len(tabs)} tabs",
    )
    return cache_key


def register(registry: HandlerRegistry) -> None:
    registry.register(JOB_REPORT_RUN, run_report_job)
