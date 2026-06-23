"""The report pages and the run / status / result API the viewer calls."""

# === What's in this file ===
# The web side of running a report. Pages: a home list of reports and a viewer
# page per report. API (called by the viewer's JavaScript): start a run (drops a
# durable job and returns right away), poll a job's status, cancel a job, and
# read a finished result one tab at a time. Every data route resolves access in
# one place and reads cached results only through the ownership-checked path, so
# one person can never pull another person's rows.
#
# reports_home() / report_view() -- the two pages
# admin_audit() -- admin-only: recent report runs/exports from the audit log
# run_report() -- enqueue a run (or hand back an already-cached result)
# job_status() / cancel_job() -- poll / stop a run
# result_summary_route() / result_tab_route() -- the finished tabs
# export_tab() -- download one finished tab as CSV or Excel

from __future__ import annotations

import json
import re

from flask import Blueprint, Response, abort, jsonify, redirect, render_template, request, url_for

from ..app import get_config, get_db
from ..auth.decorators import require_login, require_privileged
from ..auth.session import current_principal
from ..data.repositories.jobs import JobRepository, QueueFull
from ..data.repositories.run_log import RunLogRepository
from ..data.repositories.user_scope import UserScopeRepository
from ..data.repositories.users import UsersRepository
from ..delivery.report_email import EmailService
from ..jobs.types import JOB_REPORT_RUN
from ..reporting.authz import resolve_access
from ..reports import export as export_file
from ..reports.cache import ResultCache, build_cache_key
from ..reports.config_loader import ConfigLoader, ReportNotFound, ReportNotRunnable
from ..reports.params import force_salesman_scope, translate
from ..reports.views import result_summary, result_tab

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

reporting_bp = Blueprint("reporting", __name__)


def _jobs() -> JobRepository:
    config = get_config()
    return JobRepository(get_db(), config.job_queue_max, config.job_stale_seconds)


def _owns_job(job) -> bool:
    principal = current_principal()
    if principal is None:
        return False
    if principal.is_privileged:
        return True
    return (job.requested_by or "").strip().lower() == principal.email.strip().lower()


@reporting_bp.get("/reports")
@require_login
def reports_home():
    reports = ConfigLoader(get_db()).list_active()
    return render_template("reports_home.html", reports=reports, principal=current_principal())


@reporting_bp.get("/reports/<report_key>")
@require_login
def report_view(report_key: str):
    try:
        report = ConfigLoader(get_db()).load(report_key)
    except ReportNotFound:
        abort(404)
    return render_template("report_view.html", report=report, principal=current_principal())


@reporting_bp.get("/admin/audit")
@require_privileged
def admin_audit():
    entries = RunLogRepository(get_db()).recent(200)
    return render_template("admin_audit.html", entries=entries, principal=current_principal())


@reporting_bp.get("/admin/scope")
@require_privileged
def admin_scope():
    db = get_db()
    assignments = UserScopeRepository(db).all_assignments()
    users = UsersRepository(db).list_all()
    for user in users:
        user["salesmen"] = assignments.get((user["email"] or "").strip().lower(), [])
    known = {(user["email"] or "").strip().lower() for user in users}
    # Someone an admin mapped who hasn't signed in yet still shows up, so the
    # mapping isn't invisible until their first login.
    orphans = [
        {"email": email, "name": "(not signed in yet)", "role": "", "salesmen": numbers}
        for email, numbers in assignments.items()
        if email not in known
    ]
    return render_template(
        "admin_scope.html", users=users + orphans, principal=current_principal()
    )


@reporting_bp.post("/admin/scope")
@require_privileged
def admin_scope_save():
    email = (request.form.get("email") or "").strip()
    numbers = [n for n in re.split(r"[,\s]+", request.form.get("salesmen") or "") if n]
    if email:
        UserScopeRepository(get_db()).set_salesmen(email, numbers)
    return redirect(url_for("reporting.admin_scope"))


@reporting_bp.post("/api/reports/<report_key>/run")
@require_login
def run_report(report_key: str):
    db = get_db()
    principal = current_principal()
    access = resolve_access(principal, report_key, UserScopeRepository(db))
    if not access.allowed:
        abort(403)

    try:
        ConfigLoader(db).load_runnable(report_key)
    except ReportNotFound:
        abort(404)
    except ReportNotRunnable:
        return jsonify({"error": "This report isn't available to run right now."}), 409

    # Filters are arbitrary client JSON. Python's JSON reader accepts NaN/Infinity,
    # which aren't valid JSON and would later poison the cached snapshot and the
    # API response. Re-serialize strictly to reject them up front, and ignore a
    # non-object body.
    raw_filters = request.get_json(silent=True)
    try:
        json.dumps(raw_filters, allow_nan=False)
    except (ValueError, TypeError):
        return jsonify({"error": "Those filter values can't be read. Please try again."}), 400
    filters = raw_filters if isinstance(raw_filters, dict) else {}
    try:
        sp_params = translate(report_key, filters)
        scoped = list(access.salesmen) if access.salesmen is not None else None
        sp_params = force_salesman_scope(report_key, sp_params, scoped)
    except KeyError:
        abort(404)

    # Run always re-fetches fresh data. The cached snapshot is only used as a
    # fallback inside the worker if the data server is unreachable, never to skip
    # a run the user explicitly asked for.
    cache_key = build_cache_key(report_key, principal.email, access.scope_token, sp_params)

    try:
        job = _jobs().enqueue(
            JOB_REPORT_RUN,
            report_key=report_key,
            cache_key=cache_key,
            params={"filters": filters},
            requested_by=principal.email,
            scope_token=access.scope_token,
        )
    except QueueFull:
        return jsonify({"error": "The server is busy running reports. Please try again in a moment."}), 503

    return jsonify({"status": job.status, "job_id": job.id, "cache_key": cache_key}), 202


@reporting_bp.get("/api/jobs/<job_id>")
@require_login
def job_status(job_id: str):
    job = _jobs().get(job_id)
    if job is None:
        abort(404)
    if not _owns_job(job):
        abort(403)
    return jsonify({
        "job_id": job.id,
        "status": job.status,
        "error": job.error,
        "cache_key": job.cache_key,
        "result_ref": job.result_ref,
    })


@reporting_bp.post("/api/jobs/<job_id>/cancel")
@require_login
def cancel_job(job_id: str):
    jobs = _jobs()
    job = jobs.get(job_id)
    if job is None:
        abort(404)
    if not _owns_job(job):
        abort(403)
    return jsonify({"cancelled": jobs.cancel(job_id)})


@reporting_bp.get("/api/reports/<report_key>/result")
@require_login
def result_summary_route(report_key: str):
    snapshot = _read_result(report_key)
    return jsonify(result_summary(snapshot))


@reporting_bp.get("/api/reports/<report_key>/result/<tab_key>")
@require_login
def result_tab_route(report_key: str, tab_key: str):
    snapshot = _read_result(report_key)
    tab = result_tab(snapshot, tab_key)
    if tab is None:
        abort(404)
    return jsonify(tab)


@reporting_bp.get("/api/reports/<report_key>/export/<tab_key>")
@require_login
def export_tab(report_key: str, tab_key: str):
    snapshot = _read_result(report_key)
    tab = result_tab(snapshot, tab_key)
    if tab is None:
        abort(404)
    fmt = (request.args.get("fmt") or "xlsx").lower()
    if fmt == "csv":
        download_bytes, mime, ext = export_file.to_csv(tab), "text/csv; charset=utf-8", "csv"
    else:
        download_bytes, mime, ext = export_file.to_xlsx(tab), _XLSX_MIME, "xlsx"

    principal = current_principal()
    RunLogRepository(get_db()).record(
        "report.export",
        user_email=principal.email if principal else None,
        report_key=report_key,
        status="done",
        message=f"{tab_key} as {ext}",
    )
    filename = export_file.filename_for(report_key, tab_key, ext)
    return Response(
        download_bytes,
        mimetype=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@reporting_bp.post("/api/reports/<report_key>/email/<tab_key>")
@require_login
def email_tab(report_key: str, tab_key: str):
    # Emails the finished tab to the signed-in person only (to themselves, with
    # Reply-To themselves). Scheduled sends to other recipients come later; this
    # is the safe, self-only path for verifying email works.
    snapshot = _read_result(report_key)
    tab = result_tab(snapshot, tab_key)
    if tab is None:
        abort(404)
    principal = current_principal()
    service = EmailService(get_config(), RunLogRepository(get_db()))
    send_result = service.send_report(
        to=[principal.email],
        report_key=report_key,
        report_title=snapshot.get("title") or report_key,
        subtitle=tab.get("label") or "",
        xlsx_bytes=export_file.to_xlsx(tab),
        xlsx_filename=export_file.filename_for(report_key, tab_key, "xlsx"),
        reply_to=principal.email,
        requested_by=principal.email,
    )
    if not send_result.ok:
        return jsonify({"error": send_result.error or "Couldn't send the email."}), 502
    return jsonify({"ok": True, "to": principal.email, "attached": send_result.attached})


def _read_result(report_key: str) -> dict:
    principal = current_principal()
    access = resolve_access(principal, report_key, UserScopeRepository(get_db()))
    if not access.allowed:
        abort(403)
    cache_key = request.args.get("cache_key", "")
    snapshot = ResultCache(get_db()).read_for_identity(cache_key, principal.email, access.scope_token)
    if snapshot is None:
        abort(404)
    # Defense in depth: the cache key already folds in the report, but make sure
    # a snapshot can't be served under a different report's URL.
    if snapshot.get("report_key") != report_key:
        abort(404)
    return snapshot
