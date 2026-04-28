"""Master schedules -- shared, visible to everyone; admin-only CRUD.

Routes:
  GET    /master-schedules                        -> list page (everyone)
  POST   /master-schedules/api                    -> create (admin)
  POST   /master-schedules/api/<id>               -> update (admin)
  DELETE /master-schedules/api/<id>               -> delete (admin)
  POST   /master-schedules/api/<id>/run           -> trigger manual run (admin)
  GET    /master-schedules/api/<id>/history       -> run history (JSON, everyone)
  GET    /master-schedules/<id>/history           -> run history (HTML, everyone)
  GET    /master-schedules/run/<run_id>           -> single-run detail (HTML)
"""

from __future__ import annotations

from flask import Blueprint, abort, jsonify, render_template, request

from test.config.reports import REPORTS
from test.webapp.auth import current_user, require_admin, require_login
from test.webapp.blueprints._schedule_common import (
    ScheduleValidationError,
    normalise_payload,
)
from test.webapp.db import (
    create_master_schedule,
    delete_master_schedule,
    get_master_schedule,
    get_schedule_run,
    get_schedule_runs,
    list_master_schedules,
    update_master_schedule,
)
from test.webapp.services.schedule_runner import run_schedule as _run_schedule

master_schedules_bp = Blueprint("master_schedules", __name__, url_prefix="/master-schedules")


def _current_email() -> str:
    u = current_user()
    if not u:
        abort(401)
    return (u.get("email") or "").lower()


# ---- Pages ----------------------------------------------------------------


@master_schedules_bp.route("/")
@require_login
def index():
    schedules = list_master_schedules()
    u = current_user() or {}
    return render_template(
        "master_schedules.html",
        active_tab="settings" if u.get("is_admin") else "schedules",
        schedules=schedules,
        is_admin=bool(u.get("is_admin")),
        reports=[{"key": k, "name": r.name} for k, r in REPORTS.items()],
    )


@master_schedules_bp.get("/<int:sched_id>/history")
@require_login
def history_page(sched_id: int):
    sched = get_master_schedule(sched_id)
    if not sched:
        abort(404)
    runs = get_schedule_runs("master", sched_id, limit=100)
    return render_template(
        "schedule_history.html",
        active_tab="settings",
        schedule=sched,
        schedule_type="master",
        runs=runs,
    )


@master_schedules_bp.get("/run/<int:run_id>")
@require_login
def run_detail(run_id: int):
    run = get_schedule_run(run_id)
    if not run or run.get("schedule_type") != "master":
        abort(404)
    sched = get_master_schedule(int(run["schedule_id"])) or {}
    return render_template(
        "schedule_run_detail.html",
        active_tab="settings",
        run=run,
        schedule=sched,
        schedule_type="master",
    )


# ---- API ------------------------------------------------------------------


@master_schedules_bp.post("/api")
@require_admin
def api_create():
    body = request.get_json(silent=True) or {}
    try:
        payload = normalise_payload(body)
    except ScheduleValidationError as e:
        return jsonify({"error": str(e)}), 400

    new_id = create_master_schedule(payload, created_by=_current_email())
    return jsonify({"ok": True, "id": new_id}), 201


@master_schedules_bp.post("/api/<int:sched_id>")
@require_admin
def api_update(sched_id: int):
    if not get_master_schedule(sched_id):
        return jsonify({"error": "Master schedule not found."}), 404
    body = request.get_json(silent=True) or {}
    try:
        payload = normalise_payload(body)
    except ScheduleValidationError as e:
        return jsonify({"error": str(e)}), 400
    update_master_schedule(sched_id, payload, updated_by=_current_email())
    return jsonify({"ok": True})


@master_schedules_bp.delete("/api/<int:sched_id>")
@require_admin
def api_delete(sched_id: int):
    if not get_master_schedule(sched_id):
        return jsonify({"error": "Master schedule not found."}), 404
    delete_master_schedule(sched_id)
    return jsonify({"ok": True})


@master_schedules_bp.post("/api/<int:sched_id>/run")
@require_admin
def api_run(sched_id: int):
    sched = get_master_schedule(sched_id)
    if not sched:
        return jsonify({"error": "Master schedule not found."}), 404
    email = _current_email()
    result = _run_schedule(
        schedule_type="master",
        schedule=sched,
        triggered_by=email,
        sender_email=email,
    )
    return jsonify(result), (200 if result.get("ok") else 500)


@master_schedules_bp.get("/api/<int:sched_id>/history")
@require_login
def api_history(sched_id: int):
    if not get_master_schedule(sched_id):
        return jsonify({"error": "Master schedule not found."}), 404
    try:
        limit = max(1, min(int(request.args.get("limit", "50")), 500))
    except ValueError:
        limit = 50
    return jsonify({"runs": get_schedule_runs("master", sched_id, limit=limit)})
