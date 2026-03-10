"""
Reports blueprint.

Routes: /home, /reports, /report/<key>, /report/<key>/run,
        /report/progress/<run_id>, /report/<key>/download,
        /history, /history/download/<idx>, /history/view/<idx>
"""

import json
import logging
import os
import queue
import threading
import time as _time

from flask import (
    Blueprint, Response, flash, jsonify, redirect, render_template,
    request, send_file, session, url_for,
)

from webapp_v2.helpers import get_current_user, get_salesmen_list, require_login
from webapp_v2.user_map import (
    get_available_reports, get_salesman_key, is_admin, is_salesman,
)
from webapp_v2.report_api import run_report
from webapp_v2.history import add_record, update_record, get_history
from webapp_v2.db import (
    add_notification, get_all_users, get_saved_reports,
)

log = logging.getLogger(__name__)

reports_bp = Blueprint("reports", __name__)

_progress_queues: dict[str, queue.Queue] = {}
_sse_connected: dict[str, bool] = {}


@reports_bp.route("/home")
@require_login
def home():
    return redirect(url_for("reports.reports_list"))


@reports_bp.route("/reports")
@require_login
def reports_list():
    user = get_current_user()
    available = get_available_reports(user)
    presets = get_saved_reports(user.get("email", ""))
    return render_template("reports.html", user=user, reports=available,
                           presets=presets, active_tab="reports")


@reports_bp.route("/report/<report_key>")
@require_login
def report_form(report_key):
    user = get_current_user()
    available = get_available_reports(user)

    if report_key not in available:
        flash("You do not have access to this report.", "error")
        return redirect(url_for("reports.reports_list"))

    report_cfg = available[report_key]
    salesman_key = get_salesman_key(user)
    user_is_admin = is_admin(user)

    admin_default_salesman = None
    salesmen_list = []
    if user_is_admin and report_cfg.get("salesman_filter"):
        salesmen_list = get_salesmen_list(user.get("email"))
        admin_default_salesman = user.get("salesman_key") or None

    preset_params = {}
    if request.args.get("preset"):
        for k, v in request.args.items():
            if k != "preset":
                preset_params[k] = v
        preset_params["customers"] = request.args.getlist("customers")

    app_users = get_all_users() if user_is_admin else []

    return render_template(
        "report_form.html",
        user=user, report_key=report_key, report=report_cfg,
        salesman_key=salesman_key, is_admin=user_is_admin,
        salesmen_list=salesmen_list, active_tab="reports",
        preset_params=preset_params, app_users=app_users,
        admin_default_salesman=admin_default_salesman,
    )


@reports_bp.route("/report/<report_key>/run", methods=["POST"])
@require_login
def report_run(report_key):
    user = get_current_user()
    available = get_available_reports(user)

    if report_key not in available:
        return jsonify({"success": False, "error": "Access denied"}), 403

    params = request.get_json() or {}
    if is_salesman(user) and user.get("salesman_key"):
        report_cfg = available[report_key]
        if report_cfg.get("salesman_filter"):
            params["salesman"] = user["salesman_key"]

    report_cfg = available[report_key]
    email = user.get("email", "")

    record_id = add_record(
        email=email, report_key=report_key,
        report_name=report_cfg.get("name", report_key),
        params=params, status="running",
    )

    progress_q = queue.Queue()
    _progress_queues[record_id] = progress_q
    _sse_connected[record_id] = False

    def _run_in_background():
        try:
            progress_q.put({"step": "connecting", "pct": 10, "msg": "Connecting to D365..."})
            _time.sleep(0.3)
            progress_q.put({"step": "fetching", "pct": 25, "msg": "Fetching data from D365..."})

            result = run_report(report_key, params)

            if result.get("success"):
                progress_q.put({"step": "processing", "pct": 70, "msg": "Processing data..."})
                _time.sleep(0.2)
                progress_q.put({"step": "writing", "pct": 85, "msg": "Writing Excel file..."})
                _time.sleep(0.2)
                update_record(
                    email, record_id,
                    status="completed" if result.get("filepath") else "no_data",
                    filepath=result.get("filepath"),
                    filename=result.get("filename"),
                    summary=result.get("summary", {}),
                )
                result.pop("traceback", None)
                progress_q.put({"step": "done", "pct": 100, "msg": "Report complete!", "result": result})
            else:
                err = result.get("error", "Unknown error")
                update_record(email, record_id, status="failed", error=err)
                result.pop("traceback", None)
                progress_q.put({"step": "error", "pct": 100, "msg": f"Failed: {err}", "result": result})
        except Exception as e:
            update_record(email, record_id, status="failed", error=str(e))
            progress_q.put({"step": "error", "pct": 100, "msg": f"Failed: {e}",
                            "result": {"success": False, "error": str(e)}})
        finally:
            progress_q.put(None)
            _time.sleep(1)
            if not _sse_connected.get(record_id, False):
                report_name = report_cfg.get("name", report_key)
                add_notification(
                    user_email=email, ntype="report_ready",
                    title=f"{report_name} is ready",
                    message="Your report has finished. Tap to view.",
                    data={"record_id": record_id, "report_key": report_key},
                )
            _sse_connected.pop(record_id, None)

    threading.Thread(target=_run_in_background, daemon=True).start()
    log.info("Running report %s (run_id=%s) with params: %s (user: %s)",
             report_key, record_id, params, email)
    return jsonify({"run_id": record_id})


@reports_bp.route("/report/progress/<run_id>")
@require_login
def report_progress(run_id):
    progress_q = _progress_queues.get(run_id)
    _sse_connected[run_id] = True

    def generate():
        if not progress_q:
            yield f"data: {json.dumps({'step': 'error', 'pct': 100, 'msg': 'Run not found', 'result': {'success': False, 'error': 'Run not found'}})}\n\n"
            return
        try:
            while True:
                try:
                    msg = progress_q.get(timeout=120)
                except queue.Empty:
                    yield f"data: {json.dumps({'step': 'error', 'pct': 100, 'msg': 'Timeout', 'result': {'success': False, 'error': 'Report timed out'}})}\n\n"
                    break
                if msg is None:
                    _progress_queues.pop(run_id, None)
                    break
                yield f"data: {json.dumps(msg, default=str)}\n\n"
                if msg.get("step") in ("done", "error"):
                    _progress_queues.pop(run_id, None)
                    _sse_connected[run_id] = True
                    break
        except GeneratorExit:
            _sse_connected[run_id] = False

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@reports_bp.route("/report/<report_key>/download")
@require_login
def report_download(report_key):
    user = get_current_user()
    filepath = session.get(f"download_{report_key}")

    if not filepath or not os.path.isfile(filepath):
        records = get_history(user.get("email", ""))
        for rec in records:
            if rec.get("report_key") == report_key and rec.get("file_available"):
                filepath = rec["filepath"]
                break

    if not filepath or not os.path.isfile(filepath):
        flash("No report file available for download. Please run the report first.", "error")
        return redirect(url_for("reports.report_form", report_key=report_key))

    return send_file(filepath, as_attachment=True, download_name=os.path.basename(filepath))


# -- History ---------------------------------------------------------------

@reports_bp.route("/history")
@require_login
def history():
    user = get_current_user()
    records = get_history(user.get("email", ""))
    return render_template("history.html", user=user, records=records, active_tab="reports")


@reports_bp.route("/history/download/<int:record_idx>")
@require_login
def history_download(record_idx):
    user = get_current_user()
    records = get_history(user.get("email", ""))
    if record_idx < 0 or record_idx >= len(records):
        flash("Report not found in history.", "error")
        return redirect(url_for("reports.history"))

    rec = records[record_idx]
    filepath = rec.get("filepath")
    if not filepath or not os.path.isfile(filepath):
        flash("The file for this report is no longer available.", "error")
        return redirect(url_for("reports.history"))

    return send_file(filepath, as_attachment=True,
                     download_name=rec.get("filename", os.path.basename(filepath)))


@reports_bp.route("/history/view/<int:record_idx>")
@require_login
def history_view(record_idx):
    user = get_current_user()
    records = get_history(user.get("email", ""))
    if record_idx < 0 or record_idx >= len(records):
        flash("Report not found in history.", "error")
        return redirect(url_for("reports.history"))

    rec = records[record_idx]
    filepath = rec.get("filepath")
    sheets = {}
    if filepath and os.path.isfile(filepath):
        from webapp_v2.report_api import _read_excel_sheets
        sheets = _read_excel_sheets(filepath)

    return render_template("history_view.html", user=user, record=rec,
                           record_idx=record_idx, sheets=sheets, active_tab="reports")
