"""JSON API backing the filter page and the report viewer.

Endpoints (all scoped under ``/api/reports/<key>/...``):

* ``GET  /salesmen``     -- dropdown source for the filter form
* ``GET  /customers``    -- customer multi-select source (optional ?salesman=)
* ``GET  /years``        -- year dropdown source
* ``POST /run``          -- execute the report and return the multi-tab payload
* ``POST /export.xlsx``  -- build a multi-sheet workbook from that payload + the
                             client's current column order / hidden columns per tab

Report data comes from the Reporting API, with SQLite cache/mirror as the
only fallback path.
"""

from __future__ import annotations

import logging
import time
import os
import requests
from datetime import date

from flask import Blueprint, Response, abort, jsonify, request

from test.config.reports import REPORTS
from test.webapp.auth import current_user, has_sharepoint_access, require_login
from test.webapp.db import log_report_run
from test.webapp.services.email_outbox import send_report_email
from test.webapp.services.report_layouts import expand_duplicate_tabs, normalise_layouts
from test.webapp.services.report_export import build_workbook
from test.webapp.services.report_runner import run_report
from test.webapp.services import reporting_api
from test.webapp.services import cache_first
from test.webapp.services.report_access import (
    can_access_report,
    get_report_for_user,
    scope_params_for_user,
)

log = logging.getLogger(__name__)

report_api_bp = Blueprint("report_api", __name__, url_prefix="/api/reports")

# Separate blueprint for SharePoint browser endpoints (mounted at /api/sharepoint)
sharepoint_api_bp = Blueprint("sharepoint_api", __name__, url_prefix="/api/sharepoint")


def _ensure_report(key: str):
    u = current_user() or {}
    email = (u.get("email") or "").lower()
    if key not in REPORTS:
        abort(404, description=f"Unknown report '{key}'")
    if not can_access_report(email, key):
        abort(403, description="You do not have access to this report.")
    if not REPORTS[key].enabled:
        abort(404, description=f"Report '{key}' is not yet wired to a data source")


# ---------------------------------------------------------------------------
# Filter-form reference data
# ---------------------------------------------------------------------------


@report_api_bp.get("/<key>/salesmen")
@require_login
def list_salesmen(key: str):
    """Salesman dropdown source.

    Pulls distinct salesmen from the reporting API. Returns an empty
    list (NOT mock data) if the API is unreachable so the UI never
    silently shows fake names. The form falls back to a free-text
    input in that case.
    """
    _ensure_report(key)
    try:
        return jsonify(reporting_api.list_salesmen())
    except Exception:
        log.exception("reporting_api.list_salesmen failed")
        return jsonify([])


@report_api_bp.get("/<key>/customers")
@require_login
def list_customers(key: str):
    """Customer dropdown source. ``?salesman=`` narrows the list."""
    _ensure_report(key)
    salesman = (request.args.get("salesman") or "").strip()
    try:
        return jsonify(reporting_api.list_customers(salesman or None))
    except Exception:
        log.exception("reporting_api.list_customers failed")
        return jsonify([])


@report_api_bp.get("/<key>/years")
@require_login
def list_years(key: str):
    _ensure_report(key)
    current = date.today().year
    return jsonify([{"key": str(y), "name": str(y)} for y in range(current, 2019, -1)])


@report_api_bp.get("/lookups/status")
@require_login
def lookup_status():
    """Where is the salesman/customer lookup populate up to?

    The form polls this every few seconds while loading. Response shape:
        {
          "configured": bool,
          "status": "idle"|"loading"|"ready"|"error",
          "started_at": <epoch>|null,
          "finished_at": <epoch>|null,
          "elapsed_ms": int|null,
          "row_count": int,            # last populate's row count
          "cached_row_count": int,     # what's available right now
          "error": str|null
        }
    """
    return jsonify(reporting_api.lookup_status())


@report_api_bp.get("/<key>/preview-body")
@require_login
def preview_body(key: str):
    """Show the exact body that would be POSTed to the reporting API for
    the given filter params, without actually running the report.

    Filters can come from either the URL query string (the form's natural
    output) or a JSON body (programmatic callers).
    """
    _ensure_report(key)
    params = _params_from_request()
    return jsonify(reporting_api.preview(key, params))


# ---------------------------------------------------------------------------
# Run + export
# ---------------------------------------------------------------------------


def _params_from_request() -> dict:
    """Accept params from any reasonable shape the client might send.

    Resolution order (first match wins):
        1. JSON body ``{"params": {...}}``  (preferred -- matches the
           export/email/schedule envelope used elsewhere).
        2. JSON body that IS the params dict directly (the run-report
           call has historically sent this shape; keep accepting it so
           we don't 500 on cached page loads after a deploy).
        3. URL query string (for GET-style preview calls).

    Multi-value fields (currently just ``customers``) come back as lists.
    """
    body = request.get_json(silent=True)

    # Shape 1: envelope { "params": {...} }
    if isinstance(body, dict) and isinstance(body.get("params"), dict):
        return {k: v for k, v in body["params"].items() if v not in (None, "")}

    # Shape 2: bare params dict. Reject envelope-only keys so we don't
    # treat e.g. {"layouts": {...}} as filter params.
    if isinstance(body, dict) and body and "params" not in body and "layouts" not in body:
        return {k: v for k, v in body.items() if v not in (None, "")}

    # Shape 3: URL query string.
    params = {k: v for k, v in request.args.items() if v != ""}
    customers = [c for c in request.args.getlist("customers") if c]
    if customers:
        params["customers"] = customers
    return params


def _with_cache_meta(payload: dict, meta: dict) -> dict:
    out = dict(payload or {})
    merged = dict(meta or {})
    merged.setdefault("total_rows", cache_first.payload_row_count(out))
    out["_cache_first"] = merged
    return out


def _empty_refreshing_payload(key: str, report_name: str, params: dict, meta: dict) -> dict:
    return {
        "report_key": key,
        "report_name": report_name,
        "generated_at": None,
        "params": params,
        "tabs": [],
        "data_source": {
            "source": "refreshing",
            "label": "Fresh data is still loading",
        },
        "_cache_first": meta,
    }


def _run_report_logged(key: str, report_name: str, params: dict, user_email: str) -> dict:
    started = time.time()
    try:
        payload = run_report(key, report_name, params)
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        # Special-case the mirror-window-exceeded message so users see
        # the plain-English explanation instead of a generic 500.
        from test.webapp.services.mirror import MirrorWindowExceeded
        is_window = isinstance(exc, MirrorWindowExceeded)
        try:
            log_report_run(
                user_email=user_email, report_key=key, report_name=report_name,
                params=params, rows_returned=None, duration_ms=duration_ms,
                status="failed", error_message=str(exc),
            )
        except Exception:
            log.exception("failed to record failed run_report log")
        if is_window:
            raise
        raise

    duration_ms = int((time.time() - started) * 1000)
    rows = 0
    for tab in payload.get("tabs", []) or []:
        rows += len(tab.get("rows") or [])
    try:
        log_report_run(
            user_email=user_email, report_key=key, report_name=report_name,
            params=params, rows_returned=rows, duration_ms=duration_ms,
            status="success",
        )
    except Exception:
        log.exception("failed to record run_report log")
    return payload


def _cached_report_payload(key: str, report_name: str, params: dict, user_email: str) -> dict | None:
    cached = cache_first.cached_payload_for(
        kind="report_run",
        identity=key,
        user_scope=user_email,
        params={"report_name": report_name, "params": params},
    )
    if not cached:
        return None
    payload = dict(cached["payload"])
    meta = dict(payload.get("_cache_first") or {})
    meta.update({
        "state": "cached_for_action",
        "refreshed_utc": cached.get("refreshed_utc"),
        "total_rows": cache_first.payload_row_count(payload),
    })
    payload["_cache_first"] = meta
    return payload


def _report_payload_for_action(
    key: str,
    report_name: str,
    params: dict,
    user_email: str,
    *,
    prefer_cached: bool,
) -> dict:
    if prefer_cached:
        cached = _cached_report_payload(key, report_name, params, user_email)
        if cached:
            return cached
    return _run_report_logged(key, report_name, params, user_email)


@report_api_bp.post("/<key>/run")
@require_login
def run(key: str):
    _ensure_report(key)
    user = current_user() or {}
    user_email = (user.get("email") or "").lower()
    report = get_report_for_user(user_email, key)
    params = _params_from_request()
    try:
        params = scope_params_for_user(user_email, report, params)
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403

    body = request.get_json(silent=True) or {}
    cache_mode = str(body.get("cache_mode") or request.args.get("cache_mode") or "cache_first")
    try:
        wait_seconds = float(body.get("wait_seconds", request.args.get("wait_seconds", cache_first.DEFAULT_WAIT_SECONDS)))
    except (TypeError, ValueError):
        wait_seconds = cache_first.DEFAULT_WAIT_SECONDS

    def _builder() -> dict:
        return _run_report_logged(key, report.name, params, user_email)

    if cache_mode == "live":
        try:
            payload = _builder()
        except Exception as exc:
            from test.webapp.services.mirror import MirrorWindowExceeded
            if isinstance(exc, MirrorWindowExceeded):
                return jsonify({"error": str(exc), "stage": "mirror_window", "message": str(exc)}), 422
            raise
        return jsonify(_with_cache_meta(payload, {"state": "fresh", "live_only": True}))

    result = cache_first.run_cache_first(
        kind="report_run",
        identity=key,
        user_scope=user_email,
        params={"report_name": report.name, "params": params},
        builder=_builder,
        wait_seconds=wait_seconds,
    )
    meta = {
        "state": result["state"],
        "job_id": result.get("job_id"),
        "cache_key": result.get("cache_key"),
        "refreshed_utc": result.get("refreshed_utc"),
        "total_rows": result.get("total_rows"),
        "cached_refreshed_utc": result.get("cached_refreshed_utc"),
        "fresh_refreshed_utc": result.get("fresh_refreshed_utc"),
        "cached_row_count": result.get("cached_row_count"),
        "fresh_row_count": result.get("fresh_row_count"),
        "row_delta": result.get("row_delta"),
        "error": result.get("error"),
    }
    payload = result.get("payload")
    if payload:
        return jsonify(_with_cache_meta(payload, meta))
    if result["state"] == "failed":
        return jsonify({"error": result.get("error") or "Refresh failed", "_cache_first": meta}), 502
    return jsonify(_empty_refreshing_payload(key, report.name, params, meta)), 202


@report_api_bp.get("/jobs/<job_id>")
@require_login
def cache_job_status(job_id: str):
    status = cache_first.get_job_status(job_id)
    if not status.get("found"):
        return jsonify(status), 404
    return jsonify(status)


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

    On failure returns a JSON body { "error": "...", "stage": "..." }
    so the client `alert()` shows something useful instead of "HTTP 500".
    """
    _ensure_report(key)
    user = current_user() or {}
    user_email = (user.get("email") or "").lower()
    report = get_report_for_user(user_email, key)

    body = request.get_json(silent=True) or {}
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    try:
        params = scope_params_for_user(user_email, report, params)
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    layouts_raw = body.get("layouts") if isinstance(body.get("layouts"), dict) else {}
    layouts, dropped = normalise_layouts(layouts_raw)

    log.info(
        "export_xlsx: key=%s params=%s layouts_tabs=%s dropped=%s",
        key, params, sorted(layouts.keys()), sorted(dropped),
    )

    # 1) Fetch the data. Same path as /run, so it'll hit the API client's
    #    fresh cache if the user just ran the report.
    try:
        payload = _report_payload_for_action(
            key,
            report.name,
            params or {},
            user_email,
            prefer_cached=bool(body.get("use_cached_data", True)),
        )
    except Exception as exc:
        log.exception("export_xlsx: run_report failed for %s", key)
        return jsonify({
            "error": f"Could not fetch report data: {exc}",
            "stage": "fetch",
        }), 502

    if dropped:
        payload = dict(payload)
        payload["tabs"] = [t for t in payload.get("tabs", []) if str(t.get("key")) not in dropped]
    payload, layouts = expand_duplicate_tabs(payload, layouts)

    tabs = payload.get("tabs") or []
    log.info(
        "export_xlsx: building workbook for %s with %d tabs (rows: %s)",
        key, len(tabs),
        {t.get("key"): len(t.get("rows") or []) for t in tabs},
    )

    # 2) Build the .xlsx. openpyxl raises ValueError on stuff like NaN /
    #    inf / unsupported types -- catch it so the client sees a useful
    #    message instead of a generic 500.
    try:
        xlsx_bytes = build_workbook(payload, layouts)
    except Exception as exc:
        log.exception("export_xlsx: build_workbook failed for %s", key)
        return jsonify({
            "error": f"Could not build the Excel file: {exc}",
            "stage": "build",
            "tab_summary": {t.get("key"): len(t.get("rows") or []) for t in tabs},
        }), 500

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
    u = current_user() or {}
    user_email = (u.get("email") or "").lower()
    report = get_report_for_user(user_email, key)

    body = request.get_json(silent=True) or {}
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    try:
        params = scope_params_for_user(user_email, report, params)
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    layouts_raw = body.get("layouts") if isinstance(body.get("layouts"), dict) else {}
    subject = (body.get("subject") or "").strip() or f"{report.name} (test)"
    recipients_raw = (body.get("recipients") or "").strip()
    sharepoint_path = (body.get("sharepoint_path") or "").strip() or None

    if sharepoint_path and not has_sharepoint_access(u):
        return jsonify({"error": "SharePoint access is not enabled for your account."}), 403

    if not recipients_raw and not sharepoint_path:
        return jsonify({"error": "Pick at least one delivery option (email recipients or SharePoint folder)."}), 400

    layouts, dropped = normalise_layouts(layouts_raw)

    payload = _report_payload_for_action(
        key,
        report.name,
        params or {},
        user_email,
        prefer_cached=bool(body.get("use_cached_data", True)),
    )
    if dropped:
        payload = dict(payload)
        payload["tabs"] = [t for t in payload.get("tabs", []) if str(t.get("key")) not in dropped]
    payload, layouts = expand_duplicate_tabs(payload, layouts)

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
        if payload.get("_cache_first", {}).get("state") == "cached_for_action":
            result["used_cached_data"] = True
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
        "used_cached_data": payload.get("_cache_first", {}).get("state") == "cached_for_action",
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