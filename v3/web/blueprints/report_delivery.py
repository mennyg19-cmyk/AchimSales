"""Email-now and SharePoint/OneDrive folder listing."""
from __future__ import annotations

from flask import abort, current_app, jsonify, request

from web.auth.decorators import require_login
from web.blueprints.reports import (
    _assert_scope_compatible, _authz, _built_spec_or_404, _job_repo,
    _owned_job_or_404, _params_for_viewer, _principal_or_401, _sharepoint,
    _user_id, _visible_list, reports_bp,
)
from web.delivery.email import split_recipients
from web.data.repositories.external_recipients import (
    APPROVAL_NEEDED, ExternalRecipientRepository,
)
from web.delivery.graph_errors import graph_error_message
from web.delivery.jobs import enqueue_delivery
from web.jobs.queue import enqueue_or_503

@reports_bp.post("/api/reports/<report_key>/email-now")
@require_login
def email_now(report_key: str):
    p = _principal_or_401()
    spec = _built_spec_or_404(report_key)
    authz = _authz()
    authz.assert_report_runnable(p, report_key)
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")

    body = request.get_json(silent=True) or {}
    recipients = (body.get("recipients") or "").strip()
    sharepoint_path = (body.get("sharepoint_path") or "").strip()
    # Validate up front so the user gets immediate feedback (the actual send is
    # off-thread). At least one delivery target is required.
    valid = split_recipients(recipients)
    if not valid and not sharepoint_path:
        abort(400, description="Enter at least one valid recipient or a SharePoint folder.")
    if sharepoint_path and not authz.has_sharepoint_access(p):
        abort(403, description="You don't have SharePoint delivery access.")
    if valid:
        repo = ExternalRecipientRepository(current_app.config["DB"])
        repo.note_addresses(valid, requested_by_user_id=uid)
        if not repo.sendable(valid) and not sharepoint_path:
            abort(400, description=APPROVAL_NEEDED)

    job_id = enqueue_or_503(lambda: enqueue_delivery(_job_repo(), owner_user_id=uid, payload={
        "report_key": report_key, "identity": p.email,
        "visible_keys": _visible_list(authz.visible_salesman_keys(p)),
        "builder_version": spec.builder_version,
        "params": _params_for_viewer(p, report_key, body.get("params") or {}),
        "layout": body.get("layout") or {}, "recipients": recipients,
        "subject": (body.get("subject") or "").strip(), "report_name": spec.title,
        "sharepoint_path": sharepoint_path,
    }))
    worker = current_app.config["JOB_WORKER"]
    if not worker.running and not current_app.config["APP_CONFIG"].is_prod:
        worker.drain()
    return jsonify({"job_id": job_id}), 202


@reports_bp.get("/api/sharepoint/status")
@require_login
def sharepoint_status():
    p = _principal_or_401()
    sp = _sharepoint()
    return jsonify({
        "enabled": _authz().has_sharepoint_access(p),
        "configured": sp.is_configured(),
        "root": sp.root_path(),
    })


@reports_bp.get("/api/sharepoint/folders")
@require_login
def sharepoint_folders():
    p = _principal_or_401()
    if not _authz().has_sharepoint_access(p):
        abort(403, description="You don't have SharePoint access.")
    path = (request.args.get("path") or "").strip()
    try:
        return jsonify({"path": path, "folders": _sharepoint().list_folders(path)})
    except Exception as exc:  # noqa: BLE001 - surface as a clean error, never 500 the picker
        return jsonify({"path": path, "folders": [], "error": graph_error_message(exc, what="SharePoint")}), 502


@reports_bp.get("/api/onedrive/status")
@require_login
def onedrive_status():
    od = current_app.config.get("ONEDRIVE_SERVICE")
    return jsonify({
        "enabled": True,
        "configured": bool(od and od.is_configured()),
        "root": "OneDrive",
    })


@reports_bp.get("/api/onedrive/folders")
@require_login
def onedrive_folders():
    p = _principal_or_401()
    od = current_app.config.get("ONEDRIVE_SERVICE")
    if od is None:
        abort(503, description="OneDrive is not available.")
    path = (request.args.get("path") or "").strip()
    try:
        return jsonify({"path": path, "folders": od.list_folders(p.email, path)})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"path": path, "folders": [], "error": graph_error_message(exc, what="OneDrive")}), 502
