"""JSON API backing the filter page and the report viewer.

Endpoints (all scoped under ``/api/reports/<key>/...``):

* ``GET  /salesmen``     -- dropdown source for the filter form
* ``GET  /customers``    -- customer multi-select source (optional ?salesman=)
* ``GET  /years``        -- year dropdown source
* ``POST /run``          -- execute the report (stub) and return the multi-tab payload
* ``POST /export.xlsx``  -- build a multi-sheet workbook from that payload + the
                             client's current column order / hidden columns per tab

Phase 3 is still backed by mock data (``services/report_runner.py``).
The surface area here is the one that will swap to a real SP call later
without touching the frontend.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, Response, abort, jsonify, request

from test.config.reports import REPORTS, get_report
from test.webapp.auth import require_login
from test.webapp.services.mock_data import CUSTOMERS, SALESMEN, customers_by_salesman
from test.webapp.services.report_export import build_workbook
from test.webapp.services.report_runner import run_report

report_api_bp = Blueprint("report_api", __name__, url_prefix="/api/reports")


def _ensure_report(key: str):
    if key not in REPORTS:
        abort(404, description=f"Unknown report '{key}'")


# ---------------------------------------------------------------------------
# Filter-form reference data
# ---------------------------------------------------------------------------


@report_api_bp.get("/<key>/salesmen")
@require_login
def list_salesmen(key: str):
    _ensure_report(key)
    return jsonify(SALESMEN)


@report_api_bp.get("/<key>/customers")
@require_login
def list_customers(key: str):
    """All customers, or one salesman's book via ``?salesman=``."""
    _ensure_report(key)
    salesman = (request.args.get("salesman") or "").strip()
    rows = customers_by_salesman(salesman) if salesman else list(CUSTOMERS)
    return jsonify([{"key": c["key"], "name": c["name"]} for c in rows])


@report_api_bp.get("/<key>/years")
@require_login
def list_years(key: str):
    _ensure_report(key)
    current = date.today().year
    return jsonify([{"key": str(y), "name": str(y)} for y in range(current, 2019, -1)])


# ---------------------------------------------------------------------------
# Run + export
# ---------------------------------------------------------------------------


def _params_from_request() -> dict:
    """Accept params either from JSON body or URL query.

    Multi-value fields (currently just ``customers``) come back as lists.
    """
    body = request.get_json(silent=True) or {}
    source = body.get("params") if isinstance(body.get("params"), dict) else None

    if source is not None:
        # JSON body -- trust the shape as-is.
        params = {k: v for k, v in source.items() if v not in (None, "")}
    else:
        params = {k: v for k, v in request.args.items() if v != ""}
        customers = [c for c in request.args.getlist("customers") if c]
        if customers:
            params["customers"] = customers
    return params


@report_api_bp.post("/<key>/run")
@require_login
def run(key: str):
    _ensure_report(key)
    report = get_report(key)
    params = _params_from_request()
    payload = run_report(key, report.name, params)
    return jsonify(payload)


@report_api_bp.post("/<key>/export.xlsx")
@require_login
def export_xlsx(key: str):
    """Build a multi-sheet workbook.

    Body:
        {
          "params":       { ... same shape as /run ... },
          "layouts":      { "<tab_key>": {"order": [...fields...], "hidden": [...fields...]} },
          "dropped_tabs": [ "<tab_key>", ... ]   # tabs the user deleted; skipped in export
        }
    """
    _ensure_report(key)
    report = get_report(key)

    body = request.get_json(silent=True) or {}
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    layouts = body.get("layouts") if isinstance(body.get("layouts"), dict) else {}
    dropped = body.get("dropped_tabs") if isinstance(body.get("dropped_tabs"), list) else []
    dropped_set = {str(k) for k in dropped}

    payload = run_report(key, report.name, params or {})
    if dropped_set:
        payload = dict(payload)
        payload["tabs"] = [t for t in payload.get("tabs", []) if str(t.get("key")) not in dropped_set]

    xlsx_bytes = build_workbook(payload, layouts)

    filename = f"{report.name.replace(' ', '_')}.xlsx"
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
