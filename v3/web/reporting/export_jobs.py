"""Wires background Excel exports onto the durable job worker.

The viewer enqueues a ``report.export`` job pointing at an already-run report
(the source run job) plus the on-screen layout. The worker reads that run's
cached payload, replays the layout, builds the styled workbook (streaming), and
stores the .xlsx as a blob keyed by the export job id. The user can navigate
away; when the job finishes they download the file in seconds from the blob.

Like deliveries, the owner is RE-AUTHORIZED live at execution time (a revoked
grant must not be exportable), and the build never runs in the request thread.
"""

from __future__ import annotations

import hashlib
import json
import re

from web.auth.authorization import Authorization
from web.data.repositories.exports import ExportRepository
from web.data.repositories.jobs import JobRepository
from web.delivery.layout import apply_layout, expand_clones
from web.jobs.worker import Handler, JobContext
from web.reporting.cache import ReportCache
from web.reporting.export import build_workbook

EXPORT_JOB_TYPE = "report.export"

_BAD_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    base = _BAD_FILENAME.sub("_", (name or "report").strip()).strip("._") or "report"
    return f"{base[:80]}.xlsx"


def enqueue_export(job_repo: JobRepository, *, owner_user_id: int | None, source_job_id: str,
                   report_key: str, report_name: str, layout: dict | None) -> str:
    """Enqueue a background export.

    Deduped on (source run, exact layout): re-clicking Export on the same view
    collapses to the one in-flight job instead of stacking heavy builds on the
    2-slot worker (a different view still gets its own job). Dedup only blocks
    while a job is queued/running, so a finished export rebuilds on the next click.
    """
    layout = layout if isinstance(layout, dict) else {}
    fingerprint = json.dumps(layout, sort_keys=True, default=str)
    dedup_key = "export:" + hashlib.sha256(
        f"{owner_user_id}|{source_job_id}|{fingerprint}".encode()
    ).hexdigest()
    return job_repo.enqueue(
        EXPORT_JOB_TYPE,
        owner_user_id=owner_user_id,
        dedup_key=dedup_key,
        params={
            "source_job_id": source_job_id,
            "report_key": report_key,
            "report_name": report_name,
            "layout": layout,
        },
    )


def make_export_handler(cache: ReportCache, exports: ExportRepository,
                        job_repo: JobRepository, authz: Authorization) -> Handler:
    def handler(ctx: JobContext) -> str:
        p = ctx.job.params
        # Re-resolve + re-authorize the owner live (defense-in-depth, like delivery):
        # a role change/disable since enqueue must not produce an exportable file.
        principal = authz.principal_for_user_id(ctx.job.owner_user_id)
        if principal is None:
            raise RuntimeError("Export owner is unknown or inactive")
        authz.assert_report_runnable(principal, p["report_key"])

        source = job_repo.get(p["source_job_id"])
        if source is None or source.owner_user_id != ctx.job.owner_user_id:
            raise RuntimeError("Source report not found")
        cached = cache.get(source.result_ref)
        if cached is None:
            raise RuntimeError("Report result expired; re-run the report, then export")
        ctx.set_progress(25)

        layout = p.get("layout") if isinstance(p.get("layout"), dict) else None
        payload = cached.payload
        if layout:
            payload = apply_layout(expand_clones(payload, layout), layout)
        ctx.set_progress(55)

        data = build_workbook(payload, layout)
        exports.put(ctx.job.id, p["report_key"], _safe_filename(p.get("report_name")), data)
        ctx.set_progress(100)
        return ctx.job.id  # result_ref == export id == download key

    return handler
