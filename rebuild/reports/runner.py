"""Runs one report end to end: call the SP, clean rows, build tabs, cache it."""

# === What's in this file ===
# This is the job handler the worker calls for a report run. It ties the pieces
# together: load the report's definition, translate the filters into SP
# parameters, call the Reporting API, clean the rows, build the tabs, and save
# the result to the cache under the job's cache key. The web side then reads
# that cache key to show the report.
#
# build_report_snapshot() -- run the SP, clean/scope rows, build tabs (shared core)
# run_report_job() -- the report.run handler (returns the cache key it wrote)
# register() -- attach run_report_job to the worker's registry

from __future__ import annotations

import logging
import time

from ..data.connection import utc_now_iso
from ..data.repositories.jobs import STATUS_RUNNING
from ..data.repositories.run_log import RunLogRepository
from ..jobs.types import JOB_REPORT_RUN, HandlerRegistry, JobContext
from ..reporting.authz import allowed_salesmen
from .adapter import normalize
from .api_client import ReportingApiClient, ReportingApiError
from .cache import ResultCache, build_cache_key
from .config_loader import ConfigLoader
from .engine import build_tabs
from .params import force_salesman_scope, translate
from .transforms import TRANSFORMS

log = logging.getLogger("rebuild.reports.runner")

# The API call gets a deadline a little under the worker's hard job cap, so a
# wedged endpoint makes the handler return on its own instead of leaving an
# orphaned thread behind the timeout. Never let that deadline drop below a few
# seconds even if the job cap is tiny.
_MIN_API_TIMEOUT_SECONDS = 5
_JOB_TIMEOUT_BUFFER_SECONDS = 15


def build_report_snapshot(
    db,
    config,
    report_key: str,
    filters: dict,
    scope_token: str | None,
    *,
    requested_by: str | None = None,
    api_timeout: float | None = None,
    cancelled=None,
) -> dict | None:
    """Run one report and return its snapshot (tabs + meta), scoped to the token.

    Shared by the web run job and the scheduler so report math and scoping live
    in ONE place. Raises ReportingApiError if the data server fails (the caller
    decides whether to fall back to a saved copy) and ValueError if the result
    is over the row limit. ``cancelled`` is an optional check called right after
    the fetch (before the heavier normalize/build step); if it returns True the
    snapshot is abandoned and None is returned.
    """
    report_config = ConfigLoader(db).load_runnable(report_key)
    scoped_salesmen = allowed_salesmen(scope_token)
    sp_params = force_salesman_scope(report_key, translate(report_key, filters), scoped_salesmen)

    timeout = api_timeout if api_timeout is not None else config.reporting_api_timeout
    client = ReportingApiClient(config.reporting_api_base_url, config.reporting_api_key, timeout=timeout)
    api_result = client.run_report(report_config.sp_name, sp_params)

    if cancelled is not None and cancelled():
        return None

    # Trust the larger of what the API claims and what it actually sent, so an
    # under-reported row_count can't slip a huge result past the guard.
    actual_count = max(int(api_result.row_count or 0), len(api_result.rows))
    if actual_count > config.max_result_rows:
        raise ValueError(
            f"This report returned {actual_count:,} rows, over the current "
            f"{config.max_result_rows:,}-row limit. Narrow the date range and run it again."
        )

    rows = normalize(report_key, api_result.rows)
    # Backstop: even if the data server ignored the salesman filter, never let a
    # scoped person's snapshot contain another salesman's rows.
    if scoped_salesmen is not None:
        allowed = set(scoped_salesmen)
        rows = [row for row in rows if str(row.get("Salesman", "")).strip() in allowed]
    # Count what the person actually sees (after scoping), not what the server
    # fetched -- otherwise a scoped user's summary could leak the full total.
    visible_count = len(rows)
    tabs = build_tabs(rows, report_config.tabs, transforms=TRANSFORMS, params={"filters": filters, "sp_params": sp_params})

    return {
        "report_key": report_key,
        "title": report_config.title,
        "generated_at": utc_now_iso(),
        "params": filters,
        "row_count": visible_count,
        "provisional": True,
        "stale": False,
        "identity": (requested_by or "").strip().lower(),
        "scope": scope_token or "",
        "tabs": tabs,
    }


def run_report_job(ctx: JobContext) -> str | None:
    job = ctx.job
    config = ctx.config
    db = ctx.db
    started = time.monotonic()

    filters = (job.params or {}).get("filters") or {}
    sp_params = force_salesman_scope(job.report_key, translate(job.report_key, filters), allowed_salesmen(job.scope_token))
    cache_key = job.cache_key or build_cache_key(job.report_key, job.requested_by, job.scope_token, sp_params)

    api_timeout = min(
        config.reporting_api_timeout,
        max(_MIN_API_TIMEOUT_SECONDS, config.max_job_seconds - _JOB_TIMEOUT_BUFFER_SECONDS),
    )
    try:
        snapshot = build_report_snapshot(
            db, config, job.report_key, filters, job.scope_token,
            requested_by=job.requested_by, api_timeout=api_timeout,
            cancelled=ctx.cancelled,
        )
    except ReportingApiError:
        served = _serve_stale_fallback(db, job, cache_key)
        if served is not None:
            return served
        raise

    if snapshot is None:
        log.info("job %s cancelled after fetch; not building", job.id)
        return None

    actual_count = snapshot["row_count"]

    # If the job was cancelled or failed (timeout backstop) while we were
    # building, drop the result instead of writing a stale snapshot/log entry.
    current = ctx.jobs.get(job.id)
    if current is None or current.status != STATUS_RUNNING:
        log.info("job %s no longer running (%s); discarding result", job.id, current.status if current else "gone")
        return None

    ResultCache(db).store(cache_key, job.report_key, snapshot)

    RunLogRepository(db).record(
        "report.run",
        user_email=job.requested_by,
        report_key=job.report_key,
        job_id=job.id,
        duration_ms=int((time.monotonic() - started) * 1000),
        status="done",
        message=f"{actual_count} rows, {len(snapshot['tabs'])} tabs",
    )
    return cache_key


def _serve_stale_fallback(db, job, cache_key: str) -> str | None:
    """When the data server is unreachable, fall back to the last saved copy of
    this exact report (same person + filters) if there is one. Returns the cache
    key (job done, serving stale) or None when there's nothing to fall back to."""
    previous = ResultCache(db).read(cache_key)
    if previous is None:
        return None
    previous.pop("_cached_at", None)
    previous["stale"] = True
    previous["stale_reason"] = "The data server was unreachable, so this is the last saved copy."
    ResultCache(db).store(cache_key, job.report_key, previous)
    RunLogRepository(db).record(
        "report.run",
        user_email=job.requested_by,
        report_key=job.report_key,
        job_id=job.id,
        status="stale",
        message="data server unreachable; served last saved copy",
    )
    log.warning("job %s: API unreachable, served stale snapshot", job.id)
    return cache_key


def register(registry: HandlerRegistry) -> None:
    registry.register(JOB_REPORT_RUN, run_report_job)
