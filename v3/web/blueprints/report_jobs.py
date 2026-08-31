"""Report run / poll / keep / export routes."""
from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

from flask import abort, current_app, jsonify, request, send_file

from report_engine import registry
from web.auth.decorators import require_login
from web.blueprints.reports import (
    _assert_scope_compatible, _authz, _built_spec_or_404, _cache, _exports,
    _job_repo, _lookups, _owned_job_or_404, _params_for_viewer, _principal_or_401,
    _selected_customer_accounts, _user_id, _visible_list, reports_bp,
)
from web.jobs.queue import enqueue_or_503
from web.reporting.export_jobs import EXPORT_JOB_TYPE, enqueue_export
from web.reporting.jobs import enqueue_report_run
from web.reporting.report_service import drop_commissions_tab
from web.data.repositories.jobs import kept_until_is_live

@reports_bp.post("/api/reports/<report_key>/run")
@require_login
def run_report(report_key: str):
    p = _principal_or_401()
    spec = _built_spec_or_404(report_key)
    authz = _authz()
    authz.assert_report_runnable(p, report_key)

    params = request.get_json(silent=True)
    if not isinstance(params, dict):
        params = request.form.to_dict()

    # Validate selected customers: resync if unknown, error if still missing.
    selected = _selected_customer_accounts(params)
    if selected:
        still_unknown = _lookups().ensure_customers(selected)
        if still_unknown:
            abort(400, description=f"Unknown customer(s): {', '.join(still_unknown)}")

    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    visible = authz.visible_salesman_keys(p)
    params = _params_for_viewer(p, report_key, params)
    try:
        from web.reporting.params import resolve_window
        resolve_window(params)
    except ValueError as exc:
        abort(400, description=str(exc))
    job_id = enqueue_or_503(lambda: enqueue_report_run(
        _job_repo(), report_key=report_key, identity=p.email,
        visible_salesman_keys=visible, builder_version=spec.builder_version,
        params=params, owner_user_id=uid,
    ))

    # In prod the background worker drains the queue; only in non-prod (no poller)
    # do we run it inline so a local dev poll resolves without a worker thread.
    worker = current_app.config["JOB_WORKER"]
    if not worker.running and not current_app.config["APP_CONFIG"].is_prod:
        worker.drain()

    return jsonify({"job_id": job_id}), 202


@reports_bp.get("/api/jobs/<job_id>")
@require_login
def job_status(job_id: str):
    p = _principal_or_401()
    job = _owned_job_or_404(job_id, _user_id(p.email))
    return jsonify({
        "job_id": job.id, "status": job.status, "progress": job.progress,
        "error": job.error, "result_ref": job.result_ref,
    })


@reports_bp.post("/api/jobs/<job_id>/cancel")
@require_login
def cancel_job(job_id: str):
    """Cancel a still-running (or queued) report run the user is watching.

    Owner-checked like the status route. Returns whether the job was active to
    cancel; if it already finished, we report its current status so the screen
    can show the result instead of an error.
    """
    p = _principal_or_401()
    job = _owned_job_or_404(job_id, _user_id(p.email))
    cancelled = _job_repo().cancel(job_id)
    return jsonify({"cancelled": cancelled,
                    "status": "cancelled" if cancelled else job.status})


@reports_bp.get("/api/reports/result/<job_id>")
@require_login
def report_result(job_id: str):
    p = _principal_or_401()
    job = _owned_job_or_404(job_id, _user_id(p.email))
    _authz().assert_report_runnable(p, job.params.get("report_key"))
    _assert_scope_compatible(p, job)
    if job.status != "success":
        return jsonify({"status": job.status, "error": job.error}), 409
    payload = None
    if kept_until_is_live(job.kept_until):
        payload = _job_repo().get_kept_payload(job_id)
    if payload is None:
        cached = _cache().get(job.result_ref)
        if cached is None:
            abort(404, description="Result expired; please re-run")
        payload = cached.payload
    if not _authz().may_see_commissions(p):
        payload = drop_commissions_tab(payload)
    return jsonify(payload)


# How long a finished run stays resumable without Keep.
_RECENT_DONE_SECONDS = 48 * 3600
_KEEP_SECONDS = 30 * 86400
_KEEP_CAP = 5


def _age_seconds(ts: str | None, now: datetime | None = None) -> int | None:
    """Seconds since a stored timestamp. Handles both the naive 'YYYY-MM-DD
    HH:MM:SS' that SQLite writes for created_at and the tz-aware ISO that the
    job repo writes for finished_at."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return int((now - dt).total_seconds())


def _kept_still_valid(kept_until: str | None, now: datetime) -> bool:
    return kept_until_is_live(kept_until, now)


@reports_bp.get("/api/reports/active")
@require_login
def active_report_runs():
    """The current user's report runs that are still going (queued/running) or
    finished recently / Kept. Drives the always-on status bar and the
    resume-on-return behaviour. Owner-scoped: only the caller's own jobs."""
    p = _principal_or_401()
    uid = _user_id(p.email)
    if uid is None:
        return jsonify({"jobs": []})
    titles = {s.key: s.title for s in registry.built_reports()}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    jobs = []
    for r in _job_repo().report_runs_for_user(uid, limit=30):
        status = r["status"]
        kept_until = r.get("kept_until")
        if status not in ("queued", "running"):
            if _kept_still_valid(kept_until, now):
                pass
            else:
                age = _age_seconds(r["finished_at"] or r["created_at"], now)
                if age is None or age > _RECENT_DONE_SECONDS:
                    continue
        rkey = json.loads(r["params_json"] or "{}").get("report_key")
        jobs.append({
            "job_id": r["id"], "report_key": rkey,
            "title": titles.get(rkey, rkey or "Report"),
            "status": status, "progress": r["progress"] or 0,
            "age_seconds": _age_seconds(r["created_at"], now),
            "created_at": r["created_at"],
            "finished_at": r["finished_at"],
            "kept_until": kept_until or None,
            "kept": _kept_still_valid(kept_until, now),
            "keep_name": (r["keep_name"] or "").strip() if "keep_name" in r.keys() else "",
        })
    return jsonify({"jobs": jobs})


@reports_bp.post("/api/reports/runs/<job_id>/keep")
@require_login
def keep_report_run(job_id: str):
    """Extend a finished run's resume window to 30 days (cap 5 Kept per user)."""
    p = _principal_or_401()
    uid = _user_id(p.email)
    job = _owned_job_or_404(job_id, uid)
    if job.status != "success":
        abort(409, description="Only a finished report can be kept")
    kept_until = (datetime.now(timezone.utc) + timedelta(seconds=_KEEP_SECONDS)).isoformat()
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "").strip()[:80]
    cached = _cache().get(job.result_ref)
    payload_json = None
    if cached is not None:
        payload_json = json.dumps(cached.payload, default=str)
    elif _job_repo().has_kept_payload(job_id):
        payload_json = None  # already snapshotted
    else:
        abort(409, description="Result expired; cannot keep")
    ok = _job_repo().keep_run(
        job_id, uid, kept_until=kept_until, name=name, cap=_KEEP_CAP,
        payload_json=payload_json,
    )
    if not ok:
        abort(404, description="Unknown job")
    return jsonify({"job_id": job_id, "kept_until": kept_until, "kept": True, "keep_name": name})


@reports_bp.post("/api/reports/<report_key>/export/<job_id>")
@require_login
def export_report(report_key: str, job_id: str):
    """Kick off a BACKGROUND export of an already-run report and return the export
    job id. Big workbooks took minutes and timed out the request; now the worker
    builds the .xlsx off-thread (streaming) and the user downloads it after,
    without losing it if they navigate away. Body is the viewer's serialized
    layout so the file mirrors the screen."""
    p = _principal_or_401()
    spec = _built_spec_or_404(report_key)
    uid = _user_id(p.email)
    job = _owned_job_or_404(job_id, uid)
    if job.params.get("report_key") != report_key:
        abort(404, description="Unknown job")
    _authz().assert_report_runnable(p, report_key)
    _assert_scope_compatible(p, job)
    if job.status != "success":
        abort(409, description="Report is not ready to export")
    now = datetime.now(timezone.utc)
    kept_ok = kept_until_is_live(job.kept_until, now) and _job_repo().has_kept_payload(job_id)
    if not kept_ok and not _cache().exists(job.result_ref):
        abort(404, description="Result expired; please re-run")
    layout = request.get_json(silent=True)
    if not isinstance(layout, dict):  # ignore missing/malformed bodies (e.g. a JSON array)
        layout = {}
    export_id = enqueue_or_503(lambda: enqueue_export(
        _job_repo(), owner_user_id=uid, source_job_id=job_id, report_key=report_key,
        report_name=spec.title, layout=layout,
    ))
    # Non-prod has no background poller; drain inline so a local export resolves.
    worker = current_app.config["JOB_WORKER"]
    if not worker.running and not current_app.config["APP_CONFIG"].is_prod:
        worker.drain()
    return jsonify({"export_id": export_id}), 202


@reports_bp.get("/api/reports/exports/<export_id>/download")
@require_login
def download_export(export_id: str):
    """Stream a finished background export. Owner-checked via the job row; the
    blob lives in cache.db keyed by the export id.

    The .xlsx is already baked, so a demotion cannot be patched in the file.
    Re-check the source run's scope and commission stamp against live access.
    """
    p = _principal_or_401()
    uid = _user_id(p.email)
    job = _owned_job_or_404(export_id, uid)
    if job.type != EXPORT_JOB_TYPE:
        abort(404, description="Unknown export")
    _authz().assert_report_runnable(p, job.params.get("report_key"))
    source_id = str(job.params.get("source_job_id") or "")
    source = _job_repo().get(source_id) if source_id else None
    if source is None or source.owner_user_id != uid:
        abort(404, description="Unknown export")
    _assert_scope_compatible(p, source)
    if (
        job.params.get("report_key") == "invoiced"
        and not _authz().may_see_commissions(p)
    ):
        nested = source.params.get("params") if isinstance(source.params, dict) else {}
        if not (nested or {}).get("_skip_commissions"):
            abort(403, description="Result scope exceeds your current access; please re-run")
    if job.status != "success":
        abort(409, description="Export is not ready yet")
    found = _exports().content(export_id)
    if found is None:
        abort(404, description="Export expired; please export again")
    filename, data = found
    return send_file(
        io.BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name=filename,
    )


@reports_bp.get("/api/reports/exports")
@require_login
def list_exports():
    """The current user's recent background exports (for the 'Recent exports'
    panel): newest first, with status + size so finished files are re-downloadable
    in seconds."""
    p = _principal_or_401()
    uid = _user_id(p.email)
    if uid is None:
        return jsonify({"exports": []})
    authz = _authz()
    # Re-check live report access so a revoked user can't even see old export
    # metadata/titles (download is already owner+authz gated separately).
    jobs = [j for j in _job_repo().list_for_user(uid, limit=100)
            if j.type == EXPORT_JOB_TYPE
            and authz.can_view_report(p, j.params.get("report_key", ""))][:15]
    metas = _exports().metas_for([j.id for j in jobs if j.status == "success"])
    titles = {s.key: s.title for s in registry.built_reports()}
    out = []
    for j in jobs:
        rk = j.params.get("report_key", "")
        m = metas.get(j.id)
        out.append({
            "export_id": j.id, "status": j.status, "progress": j.progress,
            "report_key": rk, "report_title": titles.get(rk, rk),
            "error": j.error or "",
            "filename": m.filename if m else "",
            "size_bytes": m.size_bytes if m else 0,
            "built_at": m.built_at if m else "",
            "ready": bool(m),
        })
    return jsonify({"exports": out})


