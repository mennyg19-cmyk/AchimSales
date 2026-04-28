"""Personal schedules -- list page + save API + run history.

A schedule is a user-saved run-plan: report + params + layout + cadence +
recipients (+ optional SharePoint folder).

Routes:
  GET    /schedules                       -> list page
  POST   /schedules/api                   -> create
  DELETE /schedules/api/<id>              -> delete
  POST   /schedules/api/<id>/run          -> trigger a manual run
  GET    /schedules/api/<id>/history      -> run history (JSON)
  GET    /schedules/<id>/history          -> run history (HTML)
"""

from __future__ import annotations

import json
import sqlite3

from flask import Blueprint, abort, jsonify, render_template, request

from test.webapp.auth import current_user, has_sharepoint_access, require_login
from test.webapp.blueprints._schedule_common import (
    ScheduleValidationError,
    normalise_payload,
)
from test.webapp.db import (
    connect,
    get_schedule_run,
    get_schedule_runs,
)
from test.webapp.services.schedule_runner import run_schedule as _run_schedule

schedules_bp = Blueprint("schedules", __name__, url_prefix="/schedules")


def _current_email() -> str:
    u = current_user()
    if not u:
        abort(401)
    return (u.get("email") or "").lower()


def _row_to_dict(row: sqlite3.Row) -> dict:
    try:
        params = json.loads(row["params_json"] or "{}")
    except json.JSONDecodeError:
        params = {}
    try:
        layouts = json.loads(row["layouts_json"] or "{}")
    except json.JSONDecodeError:
        layouts = {}
    return {
        "id":              row["id"],
        "name":            row["name"],
        "report_key":      row["report_key"],
        "report_name":     row["report_name"],
        "params":          params,
        "layouts":         layouts,
        "cadence":         row["cadence"],
        "weekdays":        row["weekdays"] or "",
        "monthdays":       row["monthdays"] or "",
        "time_hhmm":       row["time_hhmm"],
        "start_date":      row["start_date"],
        "end_date":        row["end_date"],
        "recipients":      row["recipients"],
        "sharepoint_path": row["sharepoint_path"] if "sharepoint_path" in row.keys() else None,
        "active":          bool(row["active"]),
        "created_utc":     row["created_utc"],
        "last_run_utc":    row["last_run_utc"],
        "next_run_utc":    row["next_run_utc"],
    }


def _fetch_schedule(email: str, sched_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM schedules WHERE id = ? AND user_email = ?",
            (sched_id, email),
        ).fetchone()
    return dict(row) if row else None


# ---- Routes ---------------------------------------------------------------


@schedules_bp.route("/")
@require_login
def index():
    email = _current_email()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM schedules
             WHERE user_email = ?
             ORDER BY created_utc DESC
            """,
            (email,),
        ).fetchall()
    return render_template(
        "schedules.html",
        schedules=[_row_to_dict(r) for r in rows],
        active_tab="schedules",
    )


@schedules_bp.post("/api")
@require_login
def create_schedule():
    email = _current_email()
    body = request.get_json(silent=True) or {}

    try:
        payload = normalise_payload(body)
    except ScheduleValidationError as e:
        return jsonify({"error": str(e)}), 400

    if payload["sharepoint_path"] and not has_sharepoint_access():
        return jsonify({"error": "SharePoint access is not enabled for your account."}), 403

    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO schedules
                (user_email, name, report_key, report_name,
                 params_json, layouts_json,
                 cadence, weekdays, monthdays, time_hhmm,
                 start_date, end_date, recipients, sharepoint_path,
                 active, created_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            """,
            (
                email,
                payload["name"], payload["report_key"], payload["report_name"],
                payload["params_json"], payload["layouts_json"],
                payload["cadence"], payload["weekdays"], payload["monthdays"],
                payload["time_hhmm"], payload["start_date"], payload["end_date"],
                payload["recipients"], payload["sharepoint_path"], payload["active"],
            ),
        )
        new_id = cur.lastrowid

    return jsonify({"id": new_id, **{k: payload[k] for k in
                                      ("name", "report_key", "report_name",
                                       "cadence", "weekdays", "monthdays",
                                       "time_hhmm", "start_date", "end_date",
                                       "recipients", "sharepoint_path")}}), 201


@schedules_bp.delete("/api/<int:sched_id>")
@require_login
def delete_schedule(sched_id: int):
    email = _current_email()
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM schedules WHERE id = ? AND user_email = ?",
            (sched_id, email),
        )
        if cur.rowcount == 0:
            return jsonify({"error": "Schedule not found."}), 404
    return jsonify({"ok": True})


@schedules_bp.post("/api/<int:sched_id>/run")
@require_login
def run_now(sched_id: int):
    email = _current_email()
    sched = _fetch_schedule(email, sched_id)
    if not sched:
        return jsonify({"error": "Schedule not found."}), 404
    result = _run_schedule(
        schedule_type="personal",
        schedule=sched,
        triggered_by=email,
        sender_email=email,
    )
    return jsonify(result), (200 if result.get("ok") else 500)


@schedules_bp.get("/api/<int:sched_id>/history")
@require_login
def history_json(sched_id: int):
    email = _current_email()
    if not _fetch_schedule(email, sched_id):
        return jsonify({"error": "Schedule not found."}), 404
    try:
        limit = max(1, min(int(request.args.get("limit", "50")), 500))
    except ValueError:
        limit = 50
    return jsonify({"runs": get_schedule_runs("personal", sched_id, limit=limit)})


@schedules_bp.get("/<int:sched_id>/history")
@require_login
def history_page(sched_id: int):
    email = _current_email()
    sched = _fetch_schedule(email, sched_id)
    if not sched:
        abort(404)
    runs = get_schedule_runs("personal", sched_id, limit=100)
    return render_template(
        "schedule_history.html",
        active_tab="schedules",
        schedule=sched,
        schedule_type="personal",
        runs=runs,
    )


@schedules_bp.get("/run/<int:run_id>")
@require_login
def run_detail(run_id: int):
    run = get_schedule_run(run_id)
    if not run:
        abort(404)
    # Personal runs must be owned by the caller; master runs are admin-only
    # but we'll check that in the master blueprint. Here: only personal.
    if run.get("schedule_type") != "personal":
        abort(403)
    email = _current_email()
    sched = _fetch_schedule(email, int(run["schedule_id"]))
    if not sched:
        abort(403)
    return render_template(
        "schedule_run_detail.html",
        active_tab="schedules",
        run=run,
        schedule=sched,
        schedule_type="personal",
    )
