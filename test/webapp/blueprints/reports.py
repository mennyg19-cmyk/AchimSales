"""Reports blueprint -- filter + view.

Flow:
  /                         -> home page (report cards + presets) lives in app.index
  /reports                  -> legacy alias that redirects to /
  /report/<key>             -> filter page
  /report/<key>/view?params -> grid viewer; client POSTs the same params to /run
"""

from __future__ import annotations

import json

from flask import Blueprint, abort, redirect, render_template, request, url_for

from test.config.reports import REPORTS, get_report
from test.webapp.auth import require_login

reports_bp = Blueprint("reports", __name__)


# URL-only metadata, not real filter values. Don't show as chips or forward.
_META_PARAMS = {"preset", "preset_name"}


@reports_bp.route("/reports")
@require_login
def list_all():
    return redirect(url_for("index"))


@reports_bp.route("/report/<report_key>")
@require_login
def filter_form(report_key: str):
    if report_key not in REPORTS:
        abort(404)
    return render_template(
        "report_form.html",
        report=get_report(report_key),
        active_tab="reports",
    )


@reports_bp.route("/report/<report_key>/view")
@require_login
def view(report_key: str):
    if report_key not in REPORTS:
        abort(404)

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

    return render_template(
        "report_view.html",
        report=get_report(report_key),
        params=params,
        # Serialised for the data-params attribute so the client can POST
        # it back to /run without re-parsing the URL.
        params_json=json.dumps(params),
        preset_name=preset_name,
        preset_id=preset_id,
        active_tab="reports",
    )
