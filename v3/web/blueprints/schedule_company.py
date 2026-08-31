"""Company (master) schedule routes. Helpers live in schedules.py."""
from __future__ import annotations

from flask import abort, current_app, jsonify, redirect, render_template, request, url_for

from report_engine import registry
from report_engine.lib import salesman_key
from web.auth.decorators import require_login
from web.blueprints.schedules import (
    _MASTER_REPORT_FILTERS, _as_bool, _as_str_list, _authz, _check_sharepoint,
    _clean_recipients, _db, _drain_if_dev, _has_salesman_delivery, _hold_if_due,
    _lookups, _master, _master_folder, _normalize_master_params, _note_saved_recipients,
    _params_label,
    _parse_cadence, _parse_is_shared, _parse_run_as, _principal, _require_admin,
    _history_extra, _require_company_viewer, _require_master_edit, _require_master_visible,
    _runs, _scoped_salesmen, _settings, _uid, _validate_report, schedules_bp,
)
from web.data.repositories.report_defaults import (
    view_and_layout_for_create,
    view_and_layout_for_update,
)
from web.data.repositories.salesmen import SalesmanRepository
from web.data.repositories.schedules import MASTER
from web.scheduling import cadence as C
from web.scheduling.jobs import enqueue_schedule_run

@schedules_bp.get("/master-schedules/<int:schedule_id>/history")
@require_login
def master_history(schedule_id: int):
    p = _principal()
    sched = _master().get(schedule_id)
    if sched is None:
        abort(404, description="Unknown master schedule")
    _require_master_visible(p, sched)
    spec = registry.get(sched.report_key)
    title = sched.name or (spec.title if spec else sched.report_key)
    runs = _runs().list_for_schedule(schedule_id, MASTER)
    extra = _history_extra(runs, p)
    return render_template(
        "schedule_history.html", active_tab="schedules",
        report_title=title, cadence=C.describe(sched.cadence),
        schedule_type=MASTER, schedule_id=schedule_id, runs=runs, **extra,
    )



@schedules_bp.get("/master-schedules")
@require_login
def master_page():
    p = _principal()
    _require_company_viewer(p)
    return redirect(url_for("schedules.schedules_page") + "#company")


@schedules_bp.get("/api/master-schedules/lookups/status")
@require_login
def master_lookup_status():
    """Warm-up progress for the customer_master-backed dropdowns."""
    _require_company_viewer(_principal())
    return jsonify(_lookups().status())


@schedules_bp.get("/api/master-schedules/lookups/salesmen")
@require_login
def master_lookup_salesmen():
    """Salesmen from customer_master (same source as report filter dropdowns)."""
    p = _principal()
    _require_company_viewer(p)
    return jsonify({"salesmen": _scoped_salesmen(p, _lookups().salesmen())})


@schedules_bp.get("/api/master-schedules/lookups/salesmen-emails")
@require_login
def master_lookup_salesmen_emails():
    """Raw SalesGroup values that also have an email in the salesmen table."""
    p = _principal()
    _require_company_viewer(p)
    salesmen = _scoped_salesmen(p, _lookups().salesmen())
    emails = SalesmanRepository(_db()).emails_by_keys([r["key"] for r in salesmen])
    return jsonify({"salesmen": [
        {"key": r["key"], "name": r["name"], "email": emails.get(r["key"], "")}
        for r in salesmen
        if emails.get(r["key"], "")
    ]})


@schedules_bp.get("/api/master-schedules/lookups/customers")
@require_login
def master_lookup_customers():
    """Customers from customer_master (optional ?salesman= filter)."""
    p = _principal()
    _require_company_viewer(p)
    salesman = (request.args.get("salesman") or "").strip() or None
    rows = _lookups().customers(salesman)
    keys = _authz().visible_salesman_keys(p)
    if keys is not None:
        rows = [c for c in rows if salesman_key(c.get("salesman")) in keys]
    return jsonify({"customers": rows})


@schedules_bp.post("/api/master-schedules")
@require_login
def create_master():
    p = _principal()
    _require_company_viewer(p)
    body = request.get_json(silent=True) or {}
    report_key = (body.get("report_key") or "").strip()
    _validate_report(p, report_key, allow_in_app=False)
    name = (body.get("name") or "").strip()
    if not name:
        abort(400, description="A master schedule needs a name.")
    cadence = _parse_cadence(body)
    params = _normalize_master_params(
        body.get("params") or {},
        allow_salesman_delivery="salesman" in _MASTER_REPORT_FILTERS.get(report_key, ()),
    )
    sp = _master_folder(p, body, params)
    recipients = _clean_recipients(
        body, sharepoint_path=sp, has_salesman_delivery=_has_salesman_delivery(params),
        folder_label="folder",
    )
    view_name, layout = view_and_layout_for_create(body)
    mid = _master().create(
        report_key, name, params=params, layout=layout,
        cadence=cadence, recipients=recipients, sharepoint_path=sp,
        filename_template=(body.get("filename_template") or "").strip(),
        owner_user_id=_uid(p.email),
        is_shared=_parse_is_shared(body),
        run_as_user_id=_parse_run_as(p, body),
        view_name=view_name,
    )
    _note_saved_recipients(recipients, _uid(p.email), params)
    _settings().unskip_seed_name(name)
    created = _master().get(mid)
    if created:
        _hold_if_due(_master(), created, MASTER)
    return jsonify({"id": mid}), 201


@schedules_bp.post("/api/master-schedules/<int:schedule_id>/copy")
@require_login
def copy_master(schedule_id: int):
    """Duplicate a company schedule so the user can tweak one field."""
    p = _principal()
    _require_company_viewer(p)
    src = _master().get(schedule_id)
    if src is None:
        abort(404, description="Unknown master schedule")
    _require_master_edit(p, src)
    mid = _master().copy(src, owner_user_id=_uid(p.email))
    _note_saved_recipients(src.recipients, _uid(p.email), src.params)
    return jsonify({"id": mid}), 201


@schedules_bp.put("/api/master-schedules/<int:schedule_id>")
@require_login
def update_master(schedule_id: int):
    p = _principal()
    _require_company_viewer(p)
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        abort(400, description="A master schedule needs a name.")
    report_key = (body.get("report_key") or "").strip()
    if report_key:
        _validate_report(p, report_key, allow_in_app=False)
    existing = _master().get(schedule_id)
    if existing is None:
        abort(404, description="Unknown master schedule")
    _require_master_edit(p, existing)
    cadence = _parse_cadence(body)
    effective_report_key = report_key or existing.report_key
    params = _normalize_master_params(
        body.get("params") or {},
        allow_salesman_delivery="salesman" in _MASTER_REPORT_FILTERS.get(effective_report_key, ()),
    )
    sp = _master_folder(p, body, params)
    recipients = _clean_recipients(
        body, sharepoint_path=sp, has_salesman_delivery=_has_salesman_delivery(params),
        folder_label="folder",
    )
    view_name, layout = view_and_layout_for_update(
        body, getattr(existing, "view_name", None), existing.layout)
    kwargs = dict(
        name=name, params=params, layout=layout,
        cadence=cadence, recipients=recipients, sharepoint_path=sp,
        filename_template=(body.get("filename_template") or "").strip(),
        is_shared=_parse_is_shared(body),
        run_as_user_id=_parse_run_as(p, body) if _authz().is_privileged(p) else existing.run_as_user_id,
        view_name=view_name,
    )
    if report_key:
        kwargs["report_key"] = report_key
    if not _master().update(schedule_id, **kwargs):
        abort(404, description="Unknown master schedule")
    _note_saved_recipients(recipients, _uid(p.email), params)
    if existing.name != name:
        _settings().skip_seed_name(existing.name)
        _settings().unskip_seed_name(name)
    updated = _master().get(schedule_id)
    if updated:
        _hold_if_due(_master(), updated, MASTER)
    return jsonify({"updated": True})


@schedules_bp.post("/api/master-schedules/<int:schedule_id>/toggle")
@require_login
def toggle_master(schedule_id: int):
    p = _principal()
    sched = _master().get(schedule_id)
    if sched is None:
        abort(404, description="Unknown master schedule")
    _require_master_edit(p, sched)
    body = request.get_json(silent=True) or {}
    active = bool(body.get("active"))
    if not _master().set_active(schedule_id, active):
        abort(404, description="Unknown master schedule")
    if active:
        row = _master().get(schedule_id)
        if row:
            _hold_if_due(_master(), row, MASTER)
    return jsonify({"active": active})


@schedules_bp.delete("/api/master-schedules/<int:schedule_id>")
@require_login
def delete_master(schedule_id: int):
    p = _principal()
    sched = _master().get(schedule_id)
    if sched is None:
        abort(404, description="Unknown master schedule")
    _require_master_edit(p, sched)
    name = sched.name
    if not _master().delete(schedule_id):
        abort(404, description="Unknown master schedule")
    _settings().skip_seed_name(name)
    return jsonify({"deleted": True})


@schedules_bp.post("/api/master-schedules/<int:schedule_id>/run")
@require_login
def run_master(schedule_id: int):
    p = _principal()
    sched = _master().get(schedule_id)
    if sched is None:
        abort(404, description="Unknown master schedule")
    _require_master_visible(p, sched)
    job_id = enqueue_schedule_run(current_app.config["JOB_REPO"],
                                  schedule_id=schedule_id, schedule_type=MASTER,
                                  ignore_sabbath=True, trigger="manual")
    _drain_if_dev()
    return jsonify({"job_id": job_id}), 202
