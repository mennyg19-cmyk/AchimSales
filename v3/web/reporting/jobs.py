"""Wires report runs onto the durable job worker (rule 7).

Routes call `enqueue_report_run(...)` and poll the job; they never run a report
synchronously in the request thread. The handler runs the (gated) builder via a
resolver and stores the result as the cache key.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable

from web.data.repositories.jobs import JobRepository
from web.data.repositories.run_log import ReportRunLogRepository
from web.jobs.worker import Handler, JobCancelled, JobContext
from web.reporting.cache import build_cache_key, canonical_scope_token
from web.reporting.runner import Builder, ReportRunner

JOB_TYPE = "report.run"

# Resolves a report_key to its (gated) pure builder. Raises if not yet built.
BuilderResolver = Callable[[str], Builder]


def _count_rows(payload: dict) -> int:
    facts = payload.get("row_count")
    if isinstance(facts, int):
        return facts
    return sum(len(tab.get("rows") or []) for tab in (payload.get("tabs") or []))


def enqueue_report_run(job_repo: JobRepository, *, report_key: str, identity: str,
                       visible_salesman_keys: Iterable[str] | None, builder_version: int,
                       params: dict, owner_user_id: int | None = None) -> str:
    """Enqueue a report run. Dedups identical (report, scope, params) requests."""
    scope_token = canonical_scope_token(visible_salesman_keys)
    # The cache key doubles as the dedup key: the same request collapses to one job.
    dedup_key = build_cache_key(
        report_key=report_key, identity=identity, scope_token=scope_token,
        builder_version=builder_version, params=params,
    )
    visible_list = None if visible_salesman_keys is None else sorted(set(visible_salesman_keys))
    return job_repo.enqueue(
        JOB_TYPE,
        owner_user_id=owner_user_id,
        dedup_key=dedup_key,
        params={
            "report_key": report_key,
            "identity": identity,
            "visible_keys": visible_list,
            "builder_version": builder_version,
            "params": params,
        },
    )


def make_report_run_handler(runner: ReportRunner, builder_resolver: BuilderResolver,
                            run_log: ReportRunLogRepository | None = None) -> Handler:
    def handler(ctx: JobContext) -> str:
        p = ctx.job.params
        builder = builder_resolver(p["report_key"])
        started = time.monotonic()
        try:
            ctx.abort_if_cancelled()
            outcome = runner.run(
                report_key=p["report_key"],
                identity=p["identity"],
                visible_salesman_keys=p.get("visible_keys"),
                builder_version=p["builder_version"],
                params=p["params"],
                builder=builder,
                force_refresh=True,  # a queued run always recomputes; the cache serves reads
                cancel_check=ctx.is_cancelled,
            )
            ctx.abort_if_cancelled()
        except JobCancelled:
            raise
        except Exception:
            _log(run_log, ctx, p, "failure", None, started)
            raise
        _log(run_log, ctx, p, "success", _count_rows(outcome.payload), started)
        return outcome.cache_key  # stored as the job's result_ref

    return handler


def _log(run_log: ReportRunLogRepository | None, ctx: JobContext, p: dict,
         status: str, rows: int | None, started: float) -> None:
    """Best-effort audit write; an audit failure must never fail the run."""
    if run_log is None:
        return
    try:
        run_log.record(
            user_id=ctx.job.owner_user_id, report_key=p.get("report_key", ""),
            status=status, rows=rows,
            duration_ms=int((time.monotonic() - started) * 1000), source="queue",
        )
    except Exception:  # noqa: BLE001 - audit is non-critical
        pass
