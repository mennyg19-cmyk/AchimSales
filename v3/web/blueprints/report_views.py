"""Saved views, default view, company views."""
from __future__ import annotations

from flask import abort, current_app, jsonify, request

from web.auth.decorators import require_login
from web.blueprints.reports import (
    _authz, _built_spec_or_404, _company_view_dict, _company_views_repo,
    _default_dict, _defaults_repo, _preset_dict, _principal_or_401, _saved_repo,
    _user_id, reports_bp,
)

@reports_bp.get("/api/saved-reports")
@require_login
def saved_reports_list():
    """All of the current user's presets (across reports they can still view)."""
    p = _principal_or_401()
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    authz = _authz()
    items = [_preset_dict(s) for s in _saved_repo().list_for_user(uid)
             if authz.can_view_report(p, s.report_key)]
    return jsonify({"presets": items})


@reports_bp.get("/api/reports/<report_key>/presets")
@require_login
def report_presets(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    items = [_preset_dict(s) for s in _saved_repo().list_for_user(uid)
             if s.report_key == report_key]
    company = [_company_view_dict(v, p) for v in _company_views_repo().list_for_report(report_key)]
    return jsonify({
        "default": _default_dict(report_key, p, _defaults_repo().get(report_key)),
        "company": company,
        "presets": items,
    })


@reports_bp.post("/api/reports/<report_key>/presets")
@require_login
def create_preset(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        abort(400, description="A preset name is required")
    if name.lower() == "default":
        abort(400, description="Default is the company view. Edit it from Saved views.")
    pid = _saved_repo().create(uid, report_key, name,
                               body.get("params") or {}, body.get("layout") or {})
    return jsonify({"id": pid, "name": name}), 201


@reports_bp.get("/api/reports/presets/<int:preset_id>")
@require_login
def get_preset(preset_id: int):
    p = _principal_or_401()
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    s = _saved_repo().get(preset_id, uid)
    if s is None or not _authz().can_view_report(p, s.report_key):
        abort(404, description="Unknown preset")
    return jsonify(_preset_dict(s))


@reports_bp.patch("/api/reports/presets/<int:preset_id>")
@require_login
def update_preset(preset_id: int):
    p = _principal_or_401()
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    existing = _saved_repo().get(preset_id, uid)
    if existing is None or not _authz().can_view_report(p, existing.report_key):
        abort(404, description="Unknown preset")
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    if name is not None and not str(name).strip():
        abort(400, description="A preset name is required")
    if name is not None and str(name).strip().lower() == "default":
        abort(400, description="Default is the company view. Edit it from Saved views.")
    ok = _saved_repo().update(
        preset_id, uid,
        name=None if name is None else str(name).strip(),
        params=body["params"] if "params" in body else None,
        layout=body["layout"] if "layout" in body else None,
    )
    if not ok:
        abort(400, description="Could not save that view (the name may already be used)")
    updated = _saved_repo().get(preset_id, uid)
    return jsonify(_preset_dict(updated) if updated else {"id": preset_id})


@reports_bp.delete("/api/reports/presets/<int:preset_id>")
@require_login
def delete_preset(preset_id: int):
    p = _principal_or_401()
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    if not _saved_repo().delete(preset_id, uid):
        abort(404, description="Unknown preset")
    return jsonify({"deleted": True})


@reports_bp.get("/api/reports/<report_key>/default-view")
@require_login
def get_default_view(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    return jsonify(_default_dict(report_key, p, _defaults_repo().get(report_key)))


@reports_bp.put("/api/reports/<report_key>/default-view")
@require_login
def put_default_view(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    if not _authz().can_see_company_schedules(p):
        abort(403, description="Only managers and admins can change Default.")
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    body = request.get_json(silent=True) or {}
    row = _defaults_repo().upsert(
        report_key,
        params=body.get("params") if isinstance(body.get("params"), dict) else {},
        layout=body.get("layout") if isinstance(body.get("layout"), dict) else {},
        updated_by=uid,
    )
    return jsonify(_default_dict(report_key, p, row))


@reports_bp.get("/api/reports/<report_key>/company-views/<int:view_id>")
@require_login
def get_company_view(report_key: str, view_id: int):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    row = _company_views_repo().get(view_id)
    if row is None or row.report_key != report_key:
        abort(404, description="Unknown company view")
    return jsonify(_company_view_dict(row, p))


@reports_bp.put("/api/reports/<report_key>/company-views")
@require_login
def put_company_view(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    if not _authz().can_see_company_schedules(p):
        abort(403, description="Only managers and admins can change company views.")
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        abort(400, description="A view name is required")
    try:
        row = _company_views_repo().upsert(
            report_key, name,
            params=body.get("params") if isinstance(body.get("params"), dict) else {},
            layout=body.get("layout") if isinstance(body.get("layout"), dict) else {},
            updated_by=uid,
        )
    except ValueError as exc:
        abort(400, description=str(exc))
    return jsonify(_company_view_dict(row, p))


# --- delivery: email now + SharePoint picker -------------------------------- #
