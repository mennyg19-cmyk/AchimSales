"""Reports blueprint -- list + filter + view.

Flow:
  /reports                  -> list of reports
  /report/<key>             -> filter page (Phase 2)
  /report/<key>/view?params -> grid viewer; auto-runs with the posted params
                               (Phase 3 will fill in the grid)
"""

from __future__ import annotations

import json

from flask import Blueprint, abort, render_template, request

from test.config.reports import REPORTS, get_report, list_reports
from test.webapp.auth import require_login

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/reports")
@require_login
def list_all():
    return render_template("reports_list.html", reports=list_reports())


@reports_bp.route("/report/<report_key>")
@require_login
def filter_form(report_key: str):
    if report_key not in REPORTS:
        abort(404)
    return render_template("report_form.html", report=get_report(report_key))


@reports_bp.route("/report/<report_key>/view")
@require_login
def view(report_key: str):
    if report_key not in REPORTS:
        abort(404)

    # Pull the filter params off the query string. `customers` is multi-valued.
    params: dict = {}
    for k, v in request.args.items(multi=False):
        if v != "":
            params[k] = v
    customers = [c for c in request.args.getlist("customers") if c]
    if customers:
        params["customers"] = customers

    return render_template(
        "report_view.html",
        report=get_report(report_key),
        params=params,
        # Serialise for the data-params attribute so the client can POST
        # it back to /run without re-parsing the URL.
        params_json=json.dumps(params),
    )
