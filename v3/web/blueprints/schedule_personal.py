"""Personal schedule routes. Helpers live in schedules.py."""
from __future__ import annotations

from flask import abort, current_app, jsonify, render_template, request

from report_engine import registry
from web.auth.decorators import require_login
from web.blueprints.schedules import (
    _MASTER_REPORT_FILTERS, _PERIOD_OPTIONS, _STATUS_OPTIONS, _authz,
    _check_personal_folder, _clean_recipients, _drain_if_dev, _hold_if_due,
    _history_extra, _manager_options, _master, _master_page_context, _note_saved_recipients,
    _parse_cadence, _principal,
    _repo, _runs, _uid, _validate_report, _viewer_run_log, schedules_bp,
)
from web.data.repositories.app_settings import AppSettingsRepository
from web.data.repositories.report_defaults import (
    normalize_view_name,
    view_and_layout_for_create,
    view_and_layout_for_update,
)
from web.data.repositories.schedules import MASTER, PERSONAL
from web.scheduling import cadence as C
from web.scheduling.jobs import enqueue_schedule_run


@schedules_bp.get("/schedules")
@require_login
def schedules_page():
    p = _principal()
    uid = _uid(p.email)
    authz = _authz()
    is_privileged = authz.is_privileged(p)
    can_see_company = authz.can_see_company_schedules(p)
    items = []
    for s in _repo().list_for_user(uid):
        spec = registry.get(s.report_key)
        items.append({
            "id": s.id, "report_key": s.report_key,
            "name": spec.title if spec else s.report_key,
            "report_title": spec.title if spec else s.report_key,
            "cadence": C.describe(s.cadence), "cadence_raw": s.cadence or {},
            "params": s.params or {}, "recipients": s.recipients,
            "sharepoint_path": s.sharepoint_path, "is_active": s.is_active,
            "last_run": _runs().last_run_at(s.id, PERSONAL),
            "filename_template": getattr(s, "filename_template", "") or "",
            "kind": "personal",
            "view_name": normalize_view_name(getattr(s, "view_name", None)),
        })
    for s in _master().list_private_for_user(uid):
        spec = registry.get(s.report_key)
        items.append({
            "id": s.id, "report_key": s.report_key, "name": s.name,
            "report_title": (s.name or (spec.title if spec else s.report_key)),
            "cadence": C.describe(s.cadence), "cadence_raw": s.cadence or {},
            "params": s.params or {}, "recipients": s.recipients,
            "sharepoint_path": s.sharepoint_path, "is_active": s.is_active,
            "last_run": _runs().last_run_at(s.id, MASTER),
            "filename_template": getattr(s, "filename_template", "") or "",
            "kind": "master", "run_as_user_id": s.run_as_user_id,
            "view_name": normalize_view_name(getattr(s, "view_name", None)),
        })
    personal_reports = [
        {"key": s.key, "title": s.title}
        for s in registry.built_reports()
        if (not s.in_app) and authz.can_view_report(p, s.key)
    ]
    from report_engine.dates import today_eastern
    year_now = today_eastern().year
    context = {
        "active_tab": "schedules", "schedules": items,
        "is_admin": is_privileged, "is_privileged": is_privileged,
        "can_see_company": can_see_company,
        "has_sharepoint": authz.has_sharepoint_access(p),
        "personal_reports": personal_reports,
        "built_reports": personal_reports,
        "personal_report_filters": {k: list(v) for k, v in _MASTER_REPORT_FILTERS.items()},
        "report_filters": _MASTER_REPORT_FILTERS,
        "period_options": _PERIOD_OPTIONS,
        "status_options": [(v, label) for v, label in _STATUS_OPTIONS if v],
        "year_options": list(range(year_now, year_now - 5, -1)),
        "managers": _manager_options() if is_privileged else [],
    }
    if can_see_company:
        context.update(_master_page_context(p, uid))
    else:
        context["master_schedules"] = []
    context["recent_runs"] = _viewer_run_log(p)
    test_settings = AppSettingsRepository(current_app.config["DB"])
    context["test_mode_on"] = can_see_company and test_settings.is_schedule_test_mode()
    context["test_emails"] = test_settings.test_emails() if context["test_mode_on"] else []
    from web.data.repositories.delivery_legs import DeliveryLegRepository
    from web.delivery.states import UNKNOWN
    context["can_reconcile"] = is_privileged
    context["unknown_status"] = UNKNOWN
    context["unattached_legs"] = (
        DeliveryLegRepository(current_app.config["DB"]).list_unattached_unknown()
        if is_privileged else []
    )
    return render_template("schedules.html", **context)


@schedules_bp.get("/api/schedules/recent-runs")
@require_login
def recent_runs():
    return jsonify({"runs": _viewer_run_log(_principal())})


@schedules_bp.post("/api/schedules")
@require_login
def create_schedule():
    p = _principal()
    body = request.get_json(silent=True) or {}
    report_key = (body.get("report_key") or "").strip()
    _validate_report(p, report_key)
    cadence = _parse_cadence(body)
    folder = _check_personal_folder(body)
    recipients = _clean_recipients(body, sharepoint_path=folder, folder_label="OneDrive folder")
    view_name, layout = view_and_layout_for_create(body)
    sid = _repo().create(
        _uid(p.email), report_key, params=body.get("params") or {},
        layout=layout, cadence=cadence,
        recipients=recipients, sharepoint_path=folder,
        start_date=body.get("start_date") or None, end_date=body.get("end_date") or None,
        filename_template=(body.get("filename_template") or "").strip(),
        view_name=view_name,
    )
    _note_saved_recipients(recipients, _uid(p.email))
    created = _repo().get(sid, _uid(p.email))
    if created:
        _hold_if_due(_repo(), created, PERSONAL)
    return jsonify({"id": sid}), 201


@schedules_bp.put("/api/schedules/<int:schedule_id>")
@require_login
def update_schedule(schedule_id: int):
    p = _principal()
    body = request.get_json(silent=True) or {}
    cadence = _parse_cadence(body)
    folder = _check_personal_folder(body)
    recipients = _clean_recipients(body, sharepoint_path=folder, folder_label="OneDrive folder")
    existing = _repo().get(schedule_id, _uid(p.email))
    if existing is None:
        abort(404, description="Unknown schedule")
    view_name, layout = view_and_layout_for_update(
        body, getattr(existing, "view_name", None), existing.layout)
    ok = _repo().update(
        schedule_id, _uid(p.email), params=body.get("params") or {},
        layout=layout, cadence=cadence,
        recipients=recipients, sharepoint_path=folder,
        start_date=body.get("start_date") or None, end_date=body.get("end_date") or None,
        filename_template=(body.get("filename_template") or "").strip(),
        view_name=view_name,
    )
    if not ok:
        abort(404, description="Unknown schedule")
    _note_saved_recipients(recipients, _uid(p.email))
    updated = _repo().get(schedule_id, _uid(p.email))
    if updated:
        _hold_if_due(_repo(), updated, PERSONAL)
    return jsonify({"updated": True})


@schedules_bp.post("/api/schedules/<int:schedule_id>/toggle")
@require_login
def toggle_schedule(schedule_id: int):
    p = _principal()
    body = request.get_json(silent=True) or {}
    uid = _uid(p.email)
    active = bool(body.get("active"))
    if not _repo().set_active(schedule_id, uid, active):
        abort(404, description="Unknown schedule")
    if active:
        sched = _repo().get(schedule_id, uid)
        if sched:
            _hold_if_due(_repo(), sched, PERSONAL)
    return jsonify({"active": active})


@schedules_bp.delete("/api/schedules/<int:schedule_id>")
@require_login
def delete_schedule(schedule_id: int):
    p = _principal()
    if not _repo().delete(schedule_id, _uid(p.email)):
        abort(404, description="Unknown schedule")
    return jsonify({"deleted": True})


@schedules_bp.post("/api/schedules/<int:schedule_id>/run")
@require_login
def run_schedule(schedule_id: int):
    p = _principal()
    uid = _uid(p.email)
    if _repo().get(schedule_id, uid) is None:
        abort(404, description="Unknown schedule")
    job_id = enqueue_schedule_run(current_app.config["JOB_REPO"],
                                  schedule_id=schedule_id, schedule_type=PERSONAL,
                                  owner_user_id=uid, ignore_sabbath=True,
                                  trigger="manual")
    _drain_if_dev()
    return jsonify({"job_id": job_id}), 202


@schedules_bp.post("/api/schedules/<int:schedule_id>/copy")
@require_login
def copy_schedule(schedule_id: int):
    """Duplicate a personal schedule so the user can tweak one field."""
    p = _principal()
    uid = _uid(p.email)
    src = _repo().get(schedule_id, uid)
    if src is None:
        abort(404, description="Unknown schedule")
    sid = _repo().create(
        uid, src.report_key, params=dict(src.params or {}),
        layout=dict(src.layout or {}), cadence=dict(src.cadence or {}),
        recipients=src.recipients, sharepoint_path=src.sharepoint_path,
        start_date=src.start_date, end_date=src.end_date,
        filename_template=getattr(src, "filename_template", "") or "",
        view_name=normalize_view_name(getattr(src, "view_name", None)),
    )
    # Leave the copy inactive so it doesn't double-fire until edited.
    _repo().set_active(sid, uid, False)
    _note_saved_recipients(src.recipients, uid)
    return jsonify({"id": sid}), 201


@schedules_bp.get("/schedules/<int:schedule_id>/history")
@require_login
def schedule_history(schedule_id: int):
    p = _principal()
    uid = _uid(p.email)
    sched = _repo().get(schedule_id, uid)
    if sched is None:
        abort(404, description="Unknown schedule")
    spec = registry.get(sched.report_key)
    runs = _runs().list_for_schedule(schedule_id, PERSONAL)
    extra = _history_extra(runs, p)
    return render_template(
        "schedule_history.html", active_tab="schedules",
        report_title=spec.title if spec else sched.report_key,
        cadence=C.describe(sched.cadence), schedule_type=PERSONAL,
        schedule_id=schedule_id, runs=runs, **extra,
    )
