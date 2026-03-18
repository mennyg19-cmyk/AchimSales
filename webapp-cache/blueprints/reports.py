"""
Reports blueprint (Azure Automation dispatch version).

Reports are dispatched to Azure Automation runbooks instead of running
in-process.  Progress is tracked by polling the Azure Automation job
status, and the finished Excel file is downloaded from a SharePoint
pickup folder.
"""

import json
import logging
import os

from flask import (
    Blueprint, flash, jsonify, redirect, render_template,
    request, send_file, session, url_for,
)

from webapp.helpers import get_current_user, get_salesmen_list, require_login
from webapp.user_map import (
    get_available_reports, get_salesman_key, is_admin, is_salesman,
)
from webapp.history import add_record, delete_record, update_record, get_history
from webapp.db import (
    add_notification, get_all_users, get_saved_reports,
    log_report_start, log_report_end, get_report_runs,
    update_record_job_id, get_record_job_id,
)

log = logging.getLogger(__name__)

reports_bp = Blueprint("reports", __name__)


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
            if k not in ("preset",):
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
    preset_name = params.pop("preset_name", None)
    display_name = (
        f"{preset_name} ({report_cfg.get('name', report_key)})"
        if preset_name
        else report_cfg.get("name", report_key)
    )

    record_id = add_record(
        email=email, report_key=report_key,
        report_name=display_name,
        params=params, status="running",
    )

    log_report_start(record_id, email, report_key, display_name, params)

    # Build the extra_args string for the runbook
    extra_args_parts = []
    if params.get("salesman"):
        extra_args_parts.append(f"--salesman {params['salesman']}")
    if params.get("period"):
        extra_args_parts.append(f"--period {params['period']}")
    if params.get("from_date"):
        extra_args_parts.append(f"--from {params['from_date']}")
    if params.get("to_date"):
        extra_args_parts.append(f"--to {params['to_date']}")
    if params.get("status"):
        extra_args_parts.append(f"--status {params['status']}")
    if params.get("customers"):
        for c in params["customers"]:
            extra_args_parts.append(f"--customer {c}")
    if params.get("report_variant"):
        extra_args_parts.append(f"--report-variant {params['report_variant']}")
    extra_args = " ".join(extra_args_parts)

    try:
        from webapp.services.azure_automation import start_job
        job_name = start_job(
            report_name=report_key,
            extra_args=extra_args,
            webapp_record_id=record_id,
        )
        update_record_job_id(email, record_id, job_name)
        log.info("Dispatched report %s to Azure Automation job %s (record=%s, user=%s)",
                 report_key, job_name, record_id, email)
    except Exception as e:
        log.exception("Failed to dispatch report to Azure Automation")
        update_record(email, record_id, status="failed", error=str(e))
        log_report_end(record_id, "failed", str(e))
        return jsonify({"success": False, "error": f"Failed to start job: {e}"}), 500

    return jsonify({"run_id": record_id})


@reports_bp.route("/report/progress/<run_id>")
@require_login
def report_progress(run_id):
    user = get_current_user()
    email = user.get("email", "")

    # Check if the DB record already has a terminal status (completed/failed)
    records = get_history(email)
    rec = None
    for r in records:
        if r.get("record_id") == run_id:
            rec = r
            break

    if rec:
        status = rec.get("status", "")
        if status in ("completed", "no_data"):
            return jsonify({"step": "done", "pct": 100,
                            "msg": "Report complete!",
                            "result": {"success": True,
                                       "summary": rec.get("summary", {}),
                                       "filename": rec.get("filename")}})
        if status == "failed":
            return jsonify({"step": "error", "pct": 100,
                            "msg": rec.get("error") or "Report failed.",
                            "result": {"success": False,
                                       "error": rec.get("error") or "Report failed."}})

    # Still running — poll Azure Automation for live status
    job_name = get_record_job_id(run_id)
    if not job_name:
        return jsonify({"step": "starting", "pct": 5, "msg": "Waiting for job to start..."})

    try:
        from webapp.services.azure_automation import get_job_status
        job_info = get_job_status(job_name)
        az_status = job_info.get("status", "Unknown")

        if az_status in ("New", "Activating"):
            return jsonify({"step": "starting", "pct": 10, "msg": "Job queued in Azure..."})
        elif az_status == "Running":
            return jsonify({"step": "fetching", "pct": 40, "msg": "Report running in Azure..."})
        elif az_status == "Completed":
            filepath = _download_pickup_file(run_id)
            if filepath:
                update_record(email, run_id, status="completed",
                              filepath=filepath, filename=os.path.basename(filepath))
                log_report_end(run_id, "completed", None)
                report_name = rec.get("report_name", "Report") if rec else "Report"
                add_notification(
                    user_email=email, ntype="report_ready",
                    title=f"{report_name} is ready",
                    message="Your report has finished. Tap to view.",
                    data={"record_id": run_id},
                )
                return jsonify({"step": "done", "pct": 100, "msg": "Report complete!",
                                "result": {"success": True, "filename": os.path.basename(filepath)}})
            else:
                update_record(email, run_id, status="no_data", error="No output file found")
                log_report_end(run_id, "no_data", "No output file")
                return jsonify({"step": "done", "pct": 100, "msg": "Report complete (no data).",
                                "result": {"success": True, "filename": None}})
        elif az_status in ("Failed", "Stopped", "Suspended"):
            err = job_info.get("exception") or f"Azure job {az_status}"
            update_record(email, run_id, status="failed", error=err)
            log_report_end(run_id, "failed", err)
            return jsonify({"step": "error", "pct": 100, "msg": err,
                            "result": {"success": False, "error": err}})
        else:
            return jsonify({"step": "fetching", "pct": 25,
                            "msg": f"Job status: {az_status}"})
    except Exception as e:
        log.exception("Failed to poll Azure Automation job %s", job_name)
        return jsonify({"step": "fetching", "pct": 25,
                        "msg": "Checking job status..."})


def _download_pickup_file(record_id: str) -> str | None:
    """Download the report Excel file from SharePoint pickup folder.

    Returns the local filepath on success, or None if the file isn't there.
    """
    from webapp.config import WEBAPP_PICKUP_FOLDER, REPORT_OUTPUT_DIR
    try:
        from config.settings import get_client_id, get_client_secret, get_tenant_id
        from core.auth import get_graph_token

        token = get_graph_token(get_tenant_id(), get_client_id(), get_client_secret())
        if not token:
            log.error("Could not get Graph token for pickup download")
            return None

        import requests
        site_name = os.environ.get("SHAREPOINT_SITE_NAME", "AchimImportingCoInc")
        drive_path = f"https://graph.microsoft.com/v1.0/sites/{site_name}/drive"

        sp_path = f"{WEBAPP_PICKUP_FOLDER}/{record_id}.xlsx"
        url = f"{drive_path}/root:/{sp_path}:/content"

        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        if resp.status_code == 404:
            log.info("Pickup file not found at %s", sp_path)
            return None
        resp.raise_for_status()

        local_path = os.path.join(REPORT_OUTPUT_DIR, f"{record_id}.xlsx")
        with open(local_path, "wb") as f:
            f.write(resp.content)
        log.info("Downloaded pickup file to %s (%d bytes)", local_path, len(resp.content))
        return local_path
    except Exception:
        log.exception("Failed to download pickup file for %s", record_id)
        return None


@reports_bp.route("/report/cancel/<run_id>", methods=["POST"])
@require_login
def report_cancel(run_id):
    """Cancel a running report by stopping the Azure Automation job."""
    user = get_current_user()
    email = user.get("email", "")

    job_name = get_record_job_id(run_id)
    if job_name:
        try:
            from webapp.services.azure_automation import stop_job
            stop_job(job_name)
        except Exception:
            log.exception("Failed to stop Azure job %s", job_name)

    update_record(email, run_id, status="failed", error="Cancelled by user")
    log_report_end(run_id, "failed", error="Cancelled by user")
    return jsonify({"success": True, "message": "Report cancelled"})


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
        from webapp.report_api import _read_excel_sheets
        sheets = _read_excel_sheets(filepath)

    return render_template("history_view.html", user=user, record=rec,
                           record_idx=record_idx, sheets=sheets, active_tab="reports")


@reports_bp.route("/history/delete/<record_id>", methods=["POST"])
@require_login
def history_delete(record_id):
    """Delete a single history record for the current user."""
    user = get_current_user()
    deleted = delete_record(user.get("email", ""), record_id)
    if deleted:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Record not found"}), 404


# -- Report audit log (admin / developer only) ----------------------------

@reports_bp.route("/report-log")
@require_login
def report_log():
    user = get_current_user()
    if not is_admin(user):
        flash("Access denied.", "error")
        return redirect(url_for("reports.reports_list"))
    runs = get_report_runs(limit=500)
    return render_template("report_log.html", user=user, runs=runs,
                           active_tab="settings")
