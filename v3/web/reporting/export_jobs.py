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

_MONTH_NAMES = {
    "1": "Jan", "2": "Feb", "3": "Mar", "4": "Apr", "5": "May", "6": "Jun",
    "7": "Jul", "8": "Aug", "9": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}


def _describe_params(run_params: dict) -> str:
    """Build a short, human-readable suffix from the report run's filter params.

    Examples: "May_2026", "Q2_2026", "2026-05-01_to_2026-05-31", "All_Time_2026".
    """
    parts: list[str] = []
    period = str(run_params.get("period", "")).strip()
    year = str(run_params.get("year", "")).strip()
    if period == "custom":
        sd = str(run_params.get("start_date", "")).strip()
        ed = str(run_params.get("end_date", "")).strip()
        if sd and ed:
            parts.append(f"{sd}_to_{ed}")
        elif sd:
            parts.append(f"from_{sd}")
        elif ed:
            parts.append(f"to_{ed}")
    elif period:
        readable = period.replace("_", " ").title().replace(" ", "_")
        # "month" → look up the month name if a month param is present
        month_val = str(run_params.get("month", "")).strip()
        month_name = _MONTH_NAMES.get(month_val)
        if period == "month" and month_name:
            readable = month_name
        parts.append(readable)
    if year and year not in ("", "None"):
        parts.append(year)
    return "_".join(parts) if parts else ""


def _safe_filename(report_name: str, run_params: dict | None = None) -> str:
    """Ordered_Report_May_2026.xlsx — descriptive, filesystem-safe."""
    title = _BAD_FILENAME.sub("_", (report_name or "Report").strip()).strip("._") or "Report"
    suffix = _describe_params(run_params or {})
    base = f"{title}_Report" if not title.lower().endswith("report") else title
    if suffix:
        base = f"{base}_{suffix}"
    return f"{base[:100]}.xlsx"


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
        run_params = (source.params.get("params") or {}) if isinstance(source.params, dict) else {}
        ctx.set_progress(25)

        layout = p.get("layout") if isinstance(p.get("layout"), dict) else None
        payload = cached.payload
        if layout:
            payload = apply_layout(expand_clones(payload, layout), layout)
        ctx.set_progress(55)

        data = build_workbook(payload, layout)
        export_type = p.get("export_type", "one_time")
        owner = principal.email if principal else ""
        exports.put(ctx.job.id, p["report_key"],
                    _safe_filename(p.get("report_name"), run_params), data,
                    export_type=export_type, owner_email=owner)
        ctx.set_progress(100)
        return ctx.job.id  # result_ref == export id == download key

    return handler
