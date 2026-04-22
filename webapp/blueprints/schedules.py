"""
Schedules blueprint -- admin-only Azure Automation schedule management.

Routes: /schedules, /schedules/create, /schedules/<id>/update,
        /schedules/<id>/delete, /schedules/<id>/toggle, /schedules/sync
"""

import logging

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from webapp.helpers import get_current_user, require_login
from webapp.user_map import is_admin, REPORTS_CONFIG
from webapp.db import (
    get_all_schedules,
    get_schedule_by_id,
    upsert_schedule,
    update_schedule_fields,
    delete_schedule_db,
)

log = logging.getLogger(__name__)

schedules_bp = Blueprint("schedules", __name__)

PARAM_CAPS = {
    "ordered":           {"period": True, "salesman": True, "customer": True, "status": True, "email": False},
    "invoiced":          {"period": True, "salesman": True, "customer": True, "status": False, "email": False},
    "salesman":          {"period": False, "salesman": False, "customer": False, "status": False, "email": True},
    "number_4":          {"period": False, "salesman": False, "customer": False, "status": False, "email": False},
    "amazon_weekly":     {"period": False, "salesman": False, "customer": False, "status": False, "email": True},
    "customer_activity": {"period": False, "salesman": False, "customer": False, "status": False, "email": True},
}


def _require_admin():
    """Return (user, None) if admin, or (None, error_response) if not."""
    user = get_current_user()
    if not is_admin(user):
        return None, (jsonify({"success": False, "error": "Access denied"}), 403)
    return user, None


@schedules_bp.route("/schedules")
@require_login
def schedules_page():
    user = get_current_user()
    if not is_admin(user):
        flash("Access denied.", "error")
        return redirect(url_for("settings.settings_page"))

    schedules = get_all_schedules()
    report_keys = list(REPORTS_CONFIG.keys())
    report_names = {k: v["name"] for k, v in REPORTS_CONFIG.items()}

    valid_keys = set(report_keys) | {""}  # empty = not linked yet
    orphan_schedules = [
        s for s in schedules if (s.get("report_key") or "") and (s["report_key"] not in valid_keys)
    ]

    return render_template(
        "schedules.html",
        user=user,
        schedules=schedules,
        report_keys=report_keys,
        report_names=report_names,
        param_caps=PARAM_CAPS,
        orphan_schedules=orphan_schedules,
        active_tab="settings",
    )


@schedules_bp.route("/schedules/sync", methods=["POST"])
@require_login
def schedules_sync():
    user, err = _require_admin()
    if err:
        return err

    try:
        from webapp.services.azure_automation import sync_from_azure
        synced = sync_from_azure()
        return jsonify({"success": True, "count": len(synced)})
    except Exception as e:
        log.exception("Schedule sync failed")
        return jsonify({"success": False, "error": str(e)}), 500


@schedules_bp.route("/schedules/create", methods=["POST"])
@require_login
def schedules_create():
    user, err = _require_admin()
    if err:
        return err

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    report_key = (data.get("report_key") or "").strip()
    frequency = data.get("frequency", "Day")
    interval_val = int(data.get("interval", 1) or 1)
    start_time = (data.get("start_time") or "").strip()
    time_zone = data.get("time_zone", "America/New_York")
    days_of_week = (data.get("days_of_week") or "").strip()
    month_days_raw = (data.get("month_days") or "").strip()
    extra_args = (data.get("extra_args") or "").strip()
    description = (data.get("description") or "").strip()

    if not name or not report_key or not start_time:
        return jsonify({"success": False, "error": "Name, report, and start time are required."}), 400

    try:
        from webapp.services.azure_automation import (
            create_or_update_schedule,
            link_schedule_to_runbook,
        )

        dow_list = [d.strip() for d in days_of_week.split(",") if d.strip()] if days_of_week else None
        md_list = [int(d.strip()) for d in month_days_raw.split(",") if d.strip()] if month_days_raw else None

        az_sched = create_or_update_schedule(
            name=name,
            frequency=frequency,
            interval=interval_val,
            start_time=start_time,
            time_zone=time_zone,
            description=description,
            days_of_week=dow_list,
            month_days=md_list,
        )

        js = link_schedule_to_runbook(name, report_key, extra_args)

        row_id = upsert_schedule(
            name=name,
            report_key=report_key,
            extra_args=extra_args,
            frequency=frequency,
            interval_val=interval_val,
            start_time=start_time,
            time_zone=time_zone,
            days_of_week=days_of_week,
            month_days=month_days_raw,
            enabled=True,
            description=description,
            azure_schedule_name=name,
            azure_job_schedule_id=js.get("job_schedule_id", ""),
        )

        return jsonify({"success": True, "id": row_id})

    except Exception as e:
        log.exception("Failed to create schedule '%s'", name)
        return jsonify({"success": False, "error": str(e)}), 500


@schedules_bp.route("/schedules/<int:schedule_id>/update", methods=["POST"])
@require_login
def schedules_update(schedule_id):
    user, err = _require_admin()
    if err:
        return err

    existing = get_schedule_by_id(schedule_id)
    if not existing:
        return jsonify({"success": False, "error": "Schedule not found"}), 404

    data = request.get_json() or {}
    name = (data.get("name") or "").strip() or existing["name"]
    report_key = (data.get("report_key") or "").strip() or existing["report_key"]
    frequency = data.get("frequency", existing["frequency"])
    interval_val = int(data.get("interval", existing["interval_val"]) or 1)
    start_time = (data.get("start_time") or "").strip() or existing["start_time"]
    time_zone = data.get("time_zone", existing["time_zone"])
    days_of_week = (data.get("days_of_week") or "").strip()
    month_days_raw = (data.get("month_days") or "").strip()
    extra_args = (data.get("extra_args") or "").strip()
    description = (data.get("description") or "").strip()

    try:
        from webapp.services.azure_automation import (
            create_or_update_schedule,
            link_schedule_to_runbook,
            unlink_schedule_from_runbook,
        )

        old_azure_name = existing.get("azure_schedule_name") or existing["name"]
        old_js_id = existing.get("azure_job_schedule_id")

        dow_list = [d.strip() for d in days_of_week.split(",") if d.strip()] if days_of_week else None
        md_list = [int(d.strip()) for d in month_days_raw.split(",") if d.strip()] if month_days_raw else None

        create_or_update_schedule(
            name=name,
            frequency=frequency,
            interval=interval_val,
            start_time=start_time,
            time_zone=time_zone,
            description=description,
            days_of_week=dow_list,
            month_days=md_list,
        )

        if old_js_id:
            unlink_schedule_from_runbook(old_js_id)
        js = link_schedule_to_runbook(name, report_key, extra_args)

        update_schedule_fields(
            schedule_id,
            name=name,
            report_key=report_key,
            extra_args=extra_args,
            frequency=frequency,
            interval_val=interval_val,
            start_time=start_time,
            time_zone=time_zone,
            days_of_week=days_of_week,
            month_days=month_days_raw,
            description=description,
            azure_schedule_name=name,
            azure_job_schedule_id=js.get("job_schedule_id", ""),
        )

        return jsonify({"success": True})

    except Exception as e:
        log.exception("Failed to update schedule id=%d", schedule_id)
        return jsonify({"success": False, "error": str(e)}), 500


@schedules_bp.route("/schedules/<int:schedule_id>/delete", methods=["POST"])
@require_login
def schedules_delete(schedule_id):
    user, err = _require_admin()
    if err:
        return err

    existing = get_schedule_by_id(schedule_id)
    if not existing:
        return jsonify({"success": False, "error": "Schedule not found"}), 404

    try:
        from webapp.services.azure_automation import (
            delete_schedule as az_delete,
            unlink_schedule_from_runbook,
        )

        js_id = existing.get("azure_job_schedule_id")
        if js_id:
            try:
                unlink_schedule_from_runbook(js_id)
            except Exception:
                log.warning("Could not unlink job schedule '%s' (may already be gone)", js_id)

        az_name = existing.get("azure_schedule_name") or existing["name"]
        try:
            az_delete(az_name)
        except Exception:
            log.warning("Could not delete Azure schedule '%s' (may already be gone)", az_name)

        delete_schedule_db(schedule_id)
        return jsonify({"success": True})

    except Exception as e:
        log.exception("Failed to delete schedule id=%d", schedule_id)
        return jsonify({"success": False, "error": str(e)}), 500


@schedules_bp.route("/schedules/<int:schedule_id>/toggle", methods=["POST"])
@require_login
def schedules_toggle(schedule_id):
    user, err = _require_admin()
    if err:
        return err

    existing = get_schedule_by_id(schedule_id)
    if not existing:
        return jsonify({"success": False, "error": "Schedule not found"}), 404

    new_enabled = not bool(existing["enabled"])

    try:
        from webapp.services.azure_automation import update_schedule_enabled

        az_name = existing.get("azure_schedule_name") or existing["name"]
        update_schedule_enabled(az_name, new_enabled)
        update_schedule_fields(schedule_id, enabled=int(new_enabled))
        return jsonify({"success": True, "enabled": new_enabled})

    except Exception as e:
        log.exception("Failed to toggle schedule id=%d", schedule_id)
        return jsonify({"success": False, "error": str(e)}), 500
