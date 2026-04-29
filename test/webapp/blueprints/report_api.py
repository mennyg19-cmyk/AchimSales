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

import logging
import time
import os
import requests
from datetime import date

from flask import Blueprint, Response, abort, jsonify, request

from test.config.reports import REPORTS, get_report
from test.webapp.auth import current_user, has_sharepoint_access, require_login
from test.webapp.db import log_report_run
from test.webapp.services.email_outbox import send_report_email
from test.webapp.services.mock_data import CUSTOMERS, SALESMEN, customers_by_salesman
from test.webapp.services.report_export import build_workbook
from test.webapp.services.report_runner import run_report
from test.webapp.services import reporting_api

log = logging.getLogger(__name__)

report_api_bp = Blueprint("report_api", __name__, url_prefix="/api/reports")

# Separate blueprint for SharePoint browser endpoints (mounted at /api/sharepoint)
sharepoint_api_bp = Blueprint("sharepoint_api", __name__, url_prefix="/api/sharepoint")


def _normalise_layouts(raw) -> tuple[dict, set[str]]:
    """Convert the client's {tab_hidden, hidden_fields, field_order} shape into
    the {order, hidden} shape that ``report_export`` wants, and pull out the
    set of tab keys that were deleted entirely."""
    out: dict[str, dict] = {}
    dropped: set[str] = set()
    if not isinstance(raw, dict):
        return out, dropped
    for tab_key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("tab_hidden"):
            dropped.add(str(tab_key))
            continue
        out[str(tab_key)] = {
            "order":  list(entry.get("field_order") or entry.get("order") or []),
            "hidden": list(entry.get("hidden_fields") or entry.get("hidden") or []),
        }
    return out, dropped


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

    if reporting_api.is_configured():
        try:
            return jsonify(reporting_api.list_salesmen())
        except Exception:
            log.exception("reporting_api.list_salesmen failed; falling back to mock")

    return jsonify(SALESMEN)


@report_api_bp.get("/<key>/customers")
@require_login
def list_customers(key: str):
    """All customers, or one salesman's book via ``?salesman=``."""
    _ensure_report(key)
    salesman = (request.args.get("salesman") or "").strip()

    if reporting_api.is_configured():
        try:
            return jsonify(reporting_api.list_customers(salesman or None))
        except Exception:
            log.exception("reporting_api.list_customers failed; falling back to mock")

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

    user = current_user() or {}
    user_email = user.get("email") or ""
    started = time.time()
    try:
        payload = run_report(key, report.name, params)
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        try:
            log_report_run(
                user_email=user_email, report_key=key, report_name=report.name,
                params=params, rows_returned=None, duration_ms=duration_ms,
                status="failed", error_message=str(exc),
            )
        except Exception:
            log.exception("failed to record failed run_report log")
        raise

    duration_ms = int((time.time() - started) * 1000)
    rows = 0
    for tab in payload.get("tabs", []) or []:
        rows += len(tab.get("rows") or [])
    try:
        log_report_run(
            user_email=user_email, report_key=key, report_name=report.name,
            params=params, rows_returned=rows, duration_ms=duration_ms,
            status="success",
        )
    except Exception:
        log.exception("failed to record run_report log")
    return jsonify(payload)


@report_api_bp.post("/<key>/export.xlsx")
@require_login
def export_xlsx(key: str):
    """Build a multi-sheet workbook.

    Body:
        {
          "params":  { ... same shape as /run ... },
          "layouts": { "<tab_key>": {
                         "tab_hidden":   bool,
                         "hidden_fields": [fields...],
                         "field_order":   [fields...]
                      } }
        }

    Any tab with ``tab_hidden=true`` is dropped entirely (no sheet).
    """
    _ensure_report(key)
    report = get_report(key)

    body = request.get_json(silent=True) or {}
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    layouts_raw = body.get("layouts") if isinstance(body.get("layouts"), dict) else {}
    layouts, dropped = _normalise_layouts(layouts_raw)

    payload = run_report(key, report.name, params or {})
    if dropped:
        payload = dict(payload)
        payload["tabs"] = [t for t in payload.get("tabs", []) if str(t.get("key")) not in dropped]

    xlsx_bytes = build_workbook(payload, layouts)

    filename = f"{report.name.replace(' ', '_')}.xlsx"
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Email-now
# ---------------------------------------------------------------------------


@report_api_bp.post("/<key>/email-now")
@require_login
def email_now(key: str):
    """Generate the xlsx and drop it into the test outbox as a .eml file.

    In the test sandbox we never actually hit SMTP; we write a fully-formed
    RFC 822 message into ``test/outbox/`` so the user can inspect exactly
    what the live app would send.
    """
    _ensure_report(key)
    report = get_report(key)

    body = request.get_json(silent=True) or {}
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    layouts_raw = body.get("layouts") if isinstance(body.get("layouts"), dict) else {}
    subject = (body.get("subject") or "").strip() or f"{report.name} (test)"
    recipients_raw = (body.get("recipients") or "").strip()
    sharepoint_path = (body.get("sharepoint_path") or "").strip() or None

    u = current_user() or {}
    if sharepoint_path and not has_sharepoint_access(u):
        return jsonify({"error": "SharePoint access is not enabled for your account."}), 403

    if not recipients_raw and not sharepoint_path:
        return jsonify({"error": "Pick at least one delivery option (email recipients or SharePoint folder)."}), 400

    layouts, dropped = _normalise_layouts(layouts_raw)

    payload = run_report(key, report.name, params or {})
    if dropped:
        payload = dict(payload)
        payload["tabs"] = [t for t in payload.get("tabs", []) if str(t.get("key")) not in dropped]

    xlsx_bytes = build_workbook(payload, layouts)
    filename = f"{report.name.replace(' ', '_')}.xlsx"

    if recipients_raw:
        result = send_report_email(
            sender_email=u.get("email") or "unknown@test",
            recipients_raw=recipients_raw,
            subject=subject,
            report_key=key,
            report_name=report.name,
            xlsx_bytes=xlsx_bytes,
            filename=filename,
            sharepoint_path=sharepoint_path,
        )
        if not result.get("ok"):
            return jsonify({"error": result.get("error") or "Could not send."}), 400
        return jsonify(result)

    # SharePoint-only save (no email recipients)
    from test.webapp.services.sharepoint import upload_file
    try:
        sp = upload_file(sharepoint_path, filename, xlsx_bytes)
    except Exception as e:
        log.exception("SharePoint-only upload failed")
        return jsonify({"error": f"SharePoint upload failed: {e}"}), 500
    return jsonify({
        "ok":              True,
        "sharepoint_saved": True,
        "sharepoint_url":   sp.get("webUrl"),
        "sharepoint_path":  sharepoint_path,
    })


# ---------------------------------------------------------------------------
# SharePoint folder browser (picker backend)
# ---------------------------------------------------------------------------


@sharepoint_api_bp.get("/configured")
@require_login
def sp_configured():
    from test.webapp.services.sharepoint import get_root_path, is_configured
    allowed = has_sharepoint_access()
    return jsonify({
        "configured": bool(is_configured()),
        "root_path":  get_root_path(),
        "allowed":    bool(allowed),
    })


@sharepoint_api_bp.get("/folders")
@require_login
def sp_folders():
    if not has_sharepoint_access():
        return jsonify({"error": "SharePoint access not enabled for your account."}), 403
    rel_path = (request.args.get("path") or "").strip("/")
    try:
        from test.webapp.services.sharepoint import list_folders
        folders = list_folders(rel_path)
    except Exception as e:
        log.exception("sp_folders failed")
        return jsonify({"error": str(e)}), 500
    return jsonify({"path": rel_path, "folders": folders})


# ---------------------------------------------------------------------------
# API Connection Inordera Test
# ---------------------------------------------------------------------------

@report_api_bp.route("/test-reporting-api", methods=["GET"])
@require_login
def api_test_reporting_api():
    base_url = os.environ.get("REPORTING_API_BASE_URL")
    api_key = os.environ.get("REPORTING_API_KEY")

    if not base_url:
        return jsonify({"error": "REPORTING_API_BASE_URL is not set"}), 500

    if not api_key:
        return jsonify({"error": "REPORTING_API_KEY is not set"}), 500

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }

    payload = {
        "Company": "ACHM",
        "SalesOrderNumber": "ORD00795476",
    }

    try:
        response = requests.post(
            f"{base_url}/api/reports/salesline_release/run",
            headers=headers,
            json=payload,
            timeout=60,
        )

        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            body = response.json()
        else:
            body = response.text

        return jsonify({
            "request_url": f"{base_url}/api/reports/salesline_release/run",
            "status_code": response.status_code,
            "response_body": body,
        }), response.status_code

    except Exception as exc:
        return jsonify({
            "error": str(exc),
            "request_url": f"{base_url}/api/reports/salesline_release/run",
        }), 500