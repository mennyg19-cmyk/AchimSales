"""Reports blueprint -- home + filter + view.

Flow:
  /reports                  -> home page: report cards + conditional "My Presets" tab
  /report/<key>             -> filter page
  /report/<key>/view?params -> grid viewer; client POSTs the same params to /run
"""

from __future__ import annotations

import json

from flask import Blueprint, abort, render_template, request

from test.config.reports import REPORTS
from test.webapp.auth import current_user, require_login
from test.webapp.blueprints.presets import load_presets_for
from test.webapp.db import connect
from test.webapp.services.report_access import can_access_report, get_report_for_user, list_accessible_reports

reports_bp = Blueprint("reports", __name__)


# URL-only metadata, not real filter values. Don't show as chips or forward.
_META_PARAMS = {"preset", "preset_name"}


def _preset_layouts_for(preset_id: str, email: str) -> dict:
    """Return the ``layouts_json`` body for a given preset owned by this user.

    Silently returns ``{}`` for bad ids / wrong owner so the viewer just
    runs fresh instead of erroring.
    """
    if not preset_id:
        return {}
    try:
        pid = int(preset_id)
    except (TypeError, ValueError):
        return {}
    with connect() as conn:
        row = conn.execute(
            "SELECT layouts_json FROM saved_reports WHERE id = ? AND user_email = ?",
            (pid, (email or "").lower()),
        ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["layouts_json"] or "{}") or {}
    except json.JSONDecodeError:
        return {}


@reports_bp.route("/reports")
@require_login
def list_all():
    from test.webapp.db import get_user_preferences

    u = current_user() or {}
    presets = load_presets_for(u.get("email", ""))
    prefs = get_user_preferences(u.get("email", ""))
    default_tab = prefs.get("default_tab") or "all"
    # If the user prefers presets but has none yet, fall back to "all".
    if default_tab == "presets" and not presets:
        default_tab = "all"
    email = (u.get("email") or "").lower()
    return render_template(
        "reports.html",
        reports=list_accessible_reports(email, include_disabled=False),
        presets=presets,
        active_tab="reports",
        default_reports_tab=default_tab,
    )


@reports_bp.route("/report/<report_key>")
@require_login
def filter_form(report_key: str):
    if report_key not in REPORTS:
        abort(404)
    u = current_user() or {}
    email = (u.get("email") or "").lower()
    if not can_access_report(email, report_key):
        abort(403, description="You do not have access to this report.")
    report = get_report_for_user(email, report_key)
    if not report.enabled:
        abort(404, description=f"Report '{report_key}' is not yet wired to a data source")
    # In-app-only reports skip the standard filter form -> viewer flow.
    # If somebody hits this URL directly (bookmark, old link), bounce
    # them to the report's dedicated landing page.
    if report.in_app_only and report.in_app_endpoint:
        from flask import redirect, url_for
        return redirect(url_for(report.in_app_endpoint))
    return render_template(
        "report_form.html",
        report=report,
        active_tab="reports",
    )


@reports_bp.route("/report/<report_key>/view")
@require_login
def view(report_key: str):
    if report_key not in REPORTS:
        abort(404)
    u = current_user() or {}
    email = (u.get("email") or "").lower()
    if not can_access_report(email, report_key):
        abort(403, description="You do not have access to this report.")
    report = get_report_for_user(email, report_key)
    if not report.enabled:
        abort(404, description=f"Report '{report_key}' is not yet wired to a data source")

    # Pull filter params off the query string. `customers` is multi-valued.
    params: dict = {}
    for k, v in request.args.items(multi=False):
        if v != "" and k not in _META_PARAMS:
            params[k] = v
    customers = [c for c in request.args.getlist("customers") if c]
    if customers:
        params["customers"] = customers

    preset_name = (request.args.get("preset_name") or "").strip()
    preset_id = request.args.get("preset") or ""

    user_email = email
    preset_layouts = _preset_layouts_for(preset_id, user_email) if preset_id else {}

    return render_template(
        "report_view.html",
        report=report,
        params=params,
        # Serialised for the data-params attribute so the client can POST
        # it back to /run without re-parsing the URL.
        params_json=json.dumps(params),
        preset_name=preset_name,
        preset_id=preset_id,
        preset_layouts_json=json.dumps(preset_layouts),
        active_tab="reports",
    )
