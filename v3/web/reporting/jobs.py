"""Wires report runs onto the durable job worker (rule 7).

Routes call `enqueue_report_run(...)` and poll the job; they never run a report
synchronously in the request thread. The handler runs the (gated) builder via a
resolver and stores the result as the cache key.
"""

from __future__ import annotations

from typing import Callable, Iterable

from web.data.repositories.jobs import JobRepository
from web.jobs.worker import Handler, JobContext
from web.reporting.cache import build_cache_key, canonical_scope_token
from web.reporting.runner import Builder, ReportRunner

JOB_TYPE = "report.run"

# Resolves a report_key to its (gated) pure builder. Raises if not yet built.
BuilderResolver = Callable[[str], Builder]


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


def make_report_run_handler(runner: ReportRunner, builder_resolver: BuilderResolver) -> Handler:
    def handler(ctx: JobContext) -> str:
        p = ctx.job.params
        builder = builder_resolver(p["report_key"])
        outcome = runner.run(
            report_key=p["report_key"],
            identity=p["identity"],
            visible_salesman_keys=p.get("visible_keys"),
            builder_version=p["builder_version"],
            params=p["params"],
            builder=builder,
            force_refresh=True,  # a queued run always recomputes; the cache serves reads
        )
        return outcome.cache_key  # stored as the job's result_ref

    return handler
