"""
Email Distributions blueprint -- admin-only management of automated report emails.

Routes: /email-distributions, API endpoints for CRUD, toggle, send-now, log.
"""

import logging

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from webapp.helpers import get_current_user, require_login
from webapp.user_map import is_admin, REPORTS_CONFIG
from webapp.db import (
    get_all_distributions,
    get_distribution_by_id,
    upsert_distribution,
    delete_distribution,
    toggle_distribution_enabled,
    get_distribution_log,
)
from webapp.services.email_distributions import DEFAULT_PATH_TEMPLATES

log = logging.getLogger(__name__)

email_dist_bp = Blueprint("email_distributions", __name__)


def _require_admin():
    user = get_current_user()
    if not is_admin(user):
        return None, (jsonify({"success": False, "error": "Access denied"}), 403)
    return user, None


@email_dist_bp.route("/email-distributions")
@require_login
def distributions_page():
    user = get_current_user()
    if not is_admin(user):
        return redirect(url_for("settings.settings_page"))

    distributions = get_all_distributions()
    report_options = {k: v["name"] for k, v in REPORTS_CONFIG.items()}
    recent_log = get_distribution_log(limit=50)

    return render_template(
        "email_distributions.html",
        user=user,
        distributions=distributions,
        report_options=report_options,
        default_path_templates=DEFAULT_PATH_TEMPLATES,
        recent_log=recent_log,
        active_tab="settings",
    )


@email_dist_bp.route("/api/email-distributions", methods=["POST"])
@require_login
def api_create_distribution():
    _, err = _require_admin()
    if err:
        return err

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    recipients = data.get("recipients", [])
    cc = data.get("cc", [])
    report_keys = data.get("report_keys", [])
    subject_template = (data.get("subject_template") or "Daily Reports - {date}").strip()
    body_template = (data.get("body_template") or "").strip()
    enabled = data.get("enabled", True)
    trigger_mode = data.get("trigger_mode", "after_reports")
    frequency = data.get("frequency", "daily")
    days_of_week = data.get("days_of_week", "")
    month_days = data.get("month_days", "")
    send_time = data.get("send_time", "")

    if not name:
        return jsonify({"success": False, "error": "Name is required"}), 400
    if not recipients:
        return jsonify({"success": False, "error": "At least one recipient is required"}), 400
    if not report_keys:
        return jsonify({"success": False, "error": "At least one report must be selected"}), 400

    rk_list = []
    for rk in report_keys:
        if isinstance(rk, str):
            rk_list.append({"report_key": rk, "file_path_template": ""})
        else:
            rk_list.append({
                "report_key": rk.get("report_key", rk) if isinstance(rk, dict) else rk,
                "file_path_template": rk.get("file_path_template", "") if isinstance(rk, dict) else "",
            })

    try:
        row_id = upsert_distribution(
            name=name, recipients=recipients, report_keys=rk_list,
            cc=cc, subject_template=subject_template,
            body_template=body_template, enabled=enabled,
            trigger_mode=trigger_mode, frequency=frequency,
            days_of_week=days_of_week, month_days=month_days,
            send_time=send_time,
        )
        return jsonify({"success": True, "id": row_id})
    except Exception as e:
        log.exception("Failed to create distribution")
        return jsonify({"success": False, "error": str(e)}), 500


@email_dist_bp.route("/api/email-distributions/<int:dist_id>", methods=["PUT"])
@require_login
def api_update_distribution(dist_id):
    _, err = _require_admin()
    if err:
        return err

    existing = get_distribution_by_id(dist_id)
    if not existing:
        return jsonify({"success": False, "error": "Not found"}), 404

    data = request.get_json() or {}
    name = (data.get("name") or "").strip() or existing["name"]
    recipients = data.get("recipients", existing["recipients"])
    cc = data.get("cc", existing["cc"])
    report_keys_raw = data.get("report_keys")
    subject_template = (data.get("subject_template") or existing["subject_template"]).strip()
    body_template = (data.get("body_template", existing["body_template"]) or "").strip()
    enabled = data.get("enabled", bool(existing["enabled"]))
    trigger_mode = data.get("trigger_mode", existing.get("trigger_mode", "after_reports"))
    frequency = data.get("frequency", existing.get("frequency", "daily"))
    days_of_week = data.get("days_of_week", existing.get("days_of_week", ""))
    month_days = data.get("month_days", existing.get("month_days", ""))
    send_time = data.get("send_time", existing.get("send_time", ""))

    if report_keys_raw is not None:
        rk_list = []
        for rk in report_keys_raw:
            if isinstance(rk, str):
                rk_list.append({"report_key": rk, "file_path_template": ""})
            else:
                rk_list.append({
                    "report_key": rk.get("report_key", rk) if isinstance(rk, dict) else rk,
                    "file_path_template": rk.get("file_path_template", "") if isinstance(rk, dict) else "",
                })
    else:
        rk_list = existing["report_keys"]

    try:
        upsert_distribution(
            name=name, recipients=recipients, report_keys=rk_list,
            cc=cc, subject_template=subject_template,
            body_template=body_template, enabled=enabled,
            trigger_mode=trigger_mode, frequency=frequency,
            days_of_week=days_of_week, month_days=month_days,
            send_time=send_time, dist_id=dist_id,
        )
        return jsonify({"success": True})
    except Exception as e:
        log.exception("Failed to update distribution %d", dist_id)
        return jsonify({"success": False, "error": str(e)}), 500


@email_dist_bp.route("/api/email-distributions/<int:dist_id>", methods=["DELETE"])
@require_login
def api_delete_distribution(dist_id):
    _, err = _require_admin()
    if err:
        return err

    if delete_distribution(dist_id):
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Not found"}), 404


@email_dist_bp.route("/api/email-distributions/<int:dist_id>/toggle", methods=["POST"])
@require_login
def api_toggle_distribution(dist_id):
    _, err = _require_admin()
    if err:
        return err

    new_val = toggle_distribution_enabled(dist_id)
    if new_val is None:
        return jsonify({"success": False, "error": "Not found"}), 404
    return jsonify({"success": True, "enabled": new_val})


@email_dist_bp.route("/api/email-distributions/<int:dist_id>/send-now", methods=["POST"])
@require_login
def api_send_now(dist_id):
    _, err = _require_admin()
    if err:
        return err

    from webapp.services.email_distributions import send_distribution_now
    result = send_distribution_now(dist_id)
    return jsonify(result)


@email_dist_bp.route("/api/email-distributions/<int:dist_id>/log")
@require_login
def api_distribution_log(dist_id):
    _, err = _require_admin()
    if err:
        return err

    entries = get_distribution_log(dist_id=dist_id, limit=50)
    return jsonify({"success": True, "log": entries})


@email_dist_bp.route("/api/email-distributions/log")
@require_login
def api_all_distribution_logs():
    _, err = _require_admin()
    if err:
        return err

    entries = get_distribution_log(limit=50)
    return jsonify({"success": True, "log": entries})


@email_dist_bp.route("/api/email-distributions/debug")
@require_login
def api_distribution_debug():
    """Diagnostic endpoint: dry-run the distribution check and return detailed status."""
    _, err = _require_admin()
    if err:
        return err

    from datetime import datetime
    from zoneinfo import ZoneInfo
    from webapp.db import was_distribution_sent_today
    from webapp.services.email_distributions import (
        EASTERN, _matches_frequency, _is_shabbos_yomtov_today,
        _past_send_time, _reports_completed_today,
    )

    now = datetime.now(EASTERN)
    today = now.date()
    today_str = today.isoformat()

    distributions = get_all_distributions()
    results = []

    for dist in distributions:
        dist_id = dist["id"]
        name = dist["name"]
        info = {
            "id": dist_id,
            "name": name,
            "enabled": bool(dist["enabled"]),
            "trigger_mode": dist.get("trigger_mode", "after_reports"),
            "send_time": dist.get("send_time", ""),
            "frequency": dist.get("frequency", "daily"),
            "days_of_week": dist.get("days_of_week", ""),
            "report_keys": [rk["report_key"] for rk in dist["report_keys"]],
            "recipients": dist["recipients"],
        }

        if not dist["enabled"]:
            info["status"] = "SKIP: disabled"
            results.append(info)
            continue

        if not dist["report_keys"]:
            info["status"] = "SKIP: no report_keys"
            results.append(info)
            continue

        if was_distribution_sent_today(dist_id, today_str):
            info["status"] = "SKIP: already sent today"
            results.append(info)
            continue

        if not _matches_frequency(dist, today):
            info["status"] = f"SKIP: frequency filter (freq={dist.get('frequency')}, dow={dist.get('days_of_week')})"
            results.append(info)
            continue

        if _is_shabbos_yomtov_today(dist["report_keys"], today_str):
            info["status"] = "SKIP: Shabbos/YT"
            results.append(info)
            continue

        trigger = dist.get("trigger_mode", "after_reports")
        if trigger == "after_reports":
            completed = _reports_completed_today(dist["report_keys"], today_str)
            info["status"] = "READY (reports completed)" if completed else "WAITING: reports not completed yet"
        elif trigger == "scheduled":
            past = _past_send_time(dist, now)
            info["past_send_time"] = past
            info["current_time_eastern"] = now.strftime("%H:%M:%S")
            info["status"] = "READY (past send time)" if past else f"WAITING: not past send time ({dist.get('send_time')})"
        else:
            info["status"] = f"UNKNOWN trigger_mode: {trigger}"

        results.append(info)

    return jsonify({
        "success": True,
        "now_eastern": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "today": today_str,
        "distributions": results,
        "thread_alive": _is_thread_alive(),
    })


def _is_thread_alive():
    from webapp.services.email_distributions import _thread
    if _thread is None:
        return False
    return _thread.is_alive()
