"""Schedules: personal recurring deliveries + admin master schedules.

Personal schedules are owner-scoped; master schedules are admin-only and shared.
Both store filter params + grid layout + cadence + delivery targets, run through
the same ScheduleRunner, and record into the shared run-history ledger. "Run now"
and the cron tick both enqueue a durable ``schedule.run`` job.
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, render_template, request

from report_engine import registry
from web.auth.decorators import require_login
from web.auth.session import current_principal
from web.delivery.email import split_recipients
from web.data.repositories.schedules import (
    MASTER,
    PERSONAL,
    MasterScheduleRepository,
    ScheduleRepository,
    ScheduleRunRepository,
)
from web.data.repositories.users import UserRepository
from web.scheduling import cadence as C
from web.scheduling.jobs import enqueue_schedule_run

schedules_bp = Blueprint("schedules", __name__)


# --- shared helpers --------------------------------------------------------

def _authz():
    return current_app.config["AUTHZ"]


def _db():
    return current_app.config["DB"]


def _principal():
    p = current_principal()
    if p is None:
        abort(401, description="Login required")
    return p


def _uid(email: str) -> int:
    user = UserRepository(_db()).get_by_email(email)
    if user is None:
        abort(403, description="Unknown user")
    return user.id


def _require_admin(p):
    if not _authz().is_privileged(p):
        abort(403, description="Admins only")


def _repo() -> ScheduleRepository:
    return ScheduleRepository(_db())


def _master() -> MasterScheduleRepository:
    return MasterScheduleRepository(_db())


def _runs() -> ScheduleRunRepository:
    return ScheduleRunRepository(_db())


def _validate_report(p, report_key: str):
    spec = registry.get(report_key)
    if spec is None or spec.status is not registry.ReportStatus.BUILT:
        abort(404, description="Unknown report")
    _authz().assert_report_runnable(p, report_key)
    return spec


def _parse_cadence(body: dict) -> dict:
    try:
        return C.normalize(body.get("cadence"))
    except ValueError as exc:
        abort(400, description=str(exc))


def _check_sharepoint(p, body: dict) -> str:
    path = (body.get("sharepoint_path") or "").strip()
    if path and not _authz().has_sharepoint_access(p):
        abort(403, description="You don't have SharePoint delivery access.")
    return path


def _clean_recipients(body: dict, *, sharepoint_path: str) -> str:
    """Validate recipients up front (same parser as delivery), so a schedule can't
    be saved with addresses that would silently drop at send time."""
    raw = (body.get("recipients") or "").strip()
    valid = split_recipients(raw)
    if raw and not valid:
        abort(400, description="No valid email recipients (use name@domain.com).")
    if not valid and not sharepoint_path:
        abort(400, description="A schedule needs recipients or a SharePoint folder.")
    return ", ".join(valid)


def _drain_if_dev():
    worker = current_app.config["JOB_WORKER"]
    if not worker.running and not current_app.config["APP_CONFIG"].is_prod:
        worker.drain()


# --- personal schedules ----------------------------------------------------

@schedules_bp.get("/schedules")
@require_login
def schedules_page():
    p = _principal()
    uid = _uid(p.email)
    items = []
    for s in _repo().list_for_user(uid):
        spec = registry.get(s.report_key)
        items.append({
            "id": s.id, "report_key": s.report_key,
            "report_title": spec.title if spec else s.report_key,
            "cadence": C.describe(s.cadence), "recipients": s.recipients,
            "sharepoint_path": s.sharepoint_path, "is_active": s.is_active,
            "last_run": _runs().last_run_at(s.id, PERSONAL),
        })
    return render_template("schedules.html", active_tab="schedules", schedules=items)


@schedules_bp.post("/api/schedules")
@require_login
def create_schedule():
    p = _principal()
    body = request.get_json(silent=True) or {}
    report_key = (body.get("report_key") or "").strip()
    _validate_report(p, report_key)
    cadence = _parse_cadence(body)
    sp = _check_sharepoint(p, body)
    recipients = _clean_recipients(body, sharepoint_path=sp)
    sid = _repo().create(
        _uid(p.email), report_key, params=body.get("params") or {},
        layout=body.get("layout") or {}, cadence=cadence,
        recipients=recipients, sharepoint_path=sp,
        start_date=body.get("start_date") or None, end_date=body.get("end_date") or None,
    )
    return jsonify({"id": sid}), 201


@schedules_bp.put("/api/schedules/<int:schedule_id>")
@require_login
def update_schedule(schedule_id: int):
    p = _principal()
    body = request.get_json(silent=True) or {}
    cadence = _parse_cadence(body)
    sp = _check_sharepoint(p, body)
    recipients = _clean_recipients(body, sharepoint_path=sp)
    ok = _repo().update(
        schedule_id, _uid(p.email), params=body.get("params") or {},
        layout=body.get("layout") or {}, cadence=cadence,
        recipients=recipients, sharepoint_path=sp,
        start_date=body.get("start_date") or None, end_date=body.get("end_date") or None,
    )
    if not ok:
        abort(404, description="Unknown schedule")
    return jsonify({"updated": True})


@schedules_bp.post("/api/schedules/<int:schedule_id>/toggle")
@require_login
def toggle_schedule(schedule_id: int):
    p = _principal()
    body = request.get_json(silent=True) or {}
    if not _repo().set_active(schedule_id, _uid(p.email), bool(body.get("active"))):
        abort(404, description="Unknown schedule")
    return jsonify({"active": bool(body.get("active"))})


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
                                  owner_user_id=uid)
    _drain_if_dev()
    return jsonify({"job_id": job_id}), 202


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
    return render_template("schedule_history.html", active_tab="schedules",
                           report_title=spec.title if spec else sched.report_key,
                           cadence=C.describe(sched.cadence), runs=runs)


# --- master schedules (admin) ----------------------------------------------

@schedules_bp.get("/master-schedules")
@require_login
def master_page():
    p = _principal()
    _require_admin(p)
    items = []
    for s in _master().list_all():
        spec = registry.get(s.report_key)
        items.append({
            "id": s.id, "name": s.name, "report_key": s.report_key,
            "report_title": spec.title if spec else s.report_key,
            "cadence": C.describe(s.cadence), "recipients": s.recipients,
            "sharepoint_path": s.sharepoint_path, "is_active": s.is_active,
            "last_run": _runs().last_run_at(s.id, MASTER),
        })
    built = [{"key": s.key, "title": s.title} for s in registry.built_reports()]
    return render_template("master_schedules.html", active_tab="settings",
                           schedules=items, built_reports=built)


@schedules_bp.post("/api/master-schedules")
@require_login
def create_master():
    p = _principal()
    _require_admin(p)
    body = request.get_json(silent=True) or {}
    report_key = (body.get("report_key") or "").strip()
    _validate_report(p, report_key)
    name = (body.get("name") or "").strip()
    if not name:
        abort(400, description="A master schedule needs a name.")
    cadence = _parse_cadence(body)
    sp = _check_sharepoint(p, body)
    recipients = _clean_recipients(body, sharepoint_path=sp)
    mid = _master().create(
        report_key, name, params=body.get("params") or {}, layout=body.get("layout") or {},
        cadence=cadence, recipients=recipients, sharepoint_path=sp,
    )
    return jsonify({"id": mid}), 201


@schedules_bp.put("/api/master-schedules/<int:schedule_id>")
@require_login
def update_master(schedule_id: int):
    p = _principal()
    _require_admin(p)
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        abort(400, description="A master schedule needs a name.")
    cadence = _parse_cadence(body)
    sp = _check_sharepoint(p, body)
    recipients = _clean_recipients(body, sharepoint_path=sp)
    if not _master().update(schedule_id, name=name, params=body.get("params") or {},
                            layout=body.get("layout") or {}, cadence=cadence,
                            recipients=recipients, sharepoint_path=sp):
        abort(404, description="Unknown master schedule")
    return jsonify({"updated": True})


@schedules_bp.post("/api/master-schedules/<int:schedule_id>/toggle")
@require_login
def toggle_master(schedule_id: int):
    p = _principal()
    _require_admin(p)
    body = request.get_json(silent=True) or {}
    if not _master().set_active(schedule_id, bool(body.get("active"))):
        abort(404, description="Unknown master schedule")
    return jsonify({"active": bool(body.get("active"))})


@schedules_bp.delete("/api/master-schedules/<int:schedule_id>")
@require_login
def delete_master(schedule_id: int):
    p = _principal()
    _require_admin(p)
    if not _master().delete(schedule_id):
        abort(404, description="Unknown master schedule")
    return jsonify({"deleted": True})


@schedules_bp.post("/api/master-schedules/<int:schedule_id>/run")
@require_login
def run_master(schedule_id: int):
    p = _principal()
    _require_admin(p)
    if _master().get(schedule_id) is None:
        abort(404, description="Unknown master schedule")
    job_id = enqueue_schedule_run(current_app.config["JOB_REPO"],
                                  schedule_id=schedule_id, schedule_type=MASTER)
    _drain_if_dev()
    return jsonify({"job_id": job_id}), 202
