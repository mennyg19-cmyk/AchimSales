"""Admin-only diagnostic page for the on-prem reporting API.

Exposes:
    GET  /diag                -- HTML page with env-var status + a "Run test" button
    POST /diag/api/ping       -- Calls the reporting API live, returns timing,
                                 status, byte count, first row sample as JSON.

Useful for narrowing down "is the API even reachable?" questions without
having to deploy debug code.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from flask import Blueprint, jsonify, render_template, request

from test.webapp.auth import require_admin
from test.webapp.services import reporting_api


log = logging.getLogger(__name__)

diag_bp = Blueprint("diag", __name__, url_prefix="/diag")


def _env_status() -> dict[str, Any]:
    """Snapshot of every env var the reporting-API client cares about.

    The actual API key is masked (only length + last 4 chars shown).
    """
    base = os.environ.get("REPORTING_API_BASE_URL", "")
    key  = os.environ.get("REPORTING_API_KEY", "")
    timeout = os.environ.get("REPORTING_API_TIMEOUT_SECONDS", "")
    fresh   = os.environ.get("REPORTING_API_CACHE_TTL_SECONDS", "")
    stale   = os.environ.get("REPORTING_API_CACHE_STALE_TTL_SECONDS", "")
    lookup  = os.environ.get("REPORTING_API_LOOKUP_TTL_SECONDS", "")

    if key:
        masked = f"set ({len(key)} chars, ends \u2026{key[-4:]})"
    else:
        masked = "NOT SET"

    return {
        "REPORTING_API_BASE_URL":               base or "NOT SET",
        "REPORTING_API_KEY":                    masked,
        "REPORTING_API_TIMEOUT_SECONDS":        timeout or "(default 120)",
        "REPORTING_API_CACHE_TTL_SECONDS":      fresh   or "(default 300)",
        "REPORTING_API_CACHE_STALE_TTL_SECONDS":stale   or "(default 86400)",
        "REPORTING_API_LOOKUP_TTL_SECONDS":     lookup  or "(default 3600)",
        "is_configured":                        reporting_api.is_configured(),
    }


@diag_bp.get("")
@require_admin
def diag_home():
    from test.webapp.services import mirror, mirror_scheduler
    return render_template(
        "diag.html",
        env_status=_env_status(),
        mirror_freshness=mirror.mirror_freshness(),
        mirror_recent_runs=mirror.list_recent_refresh_runs(limit=20),
        mirror_next_run=mirror_scheduler.next_run_at(),
    )


@diag_bp.post("/api/mirror/refresh")
@require_admin
def diag_mirror_refresh():
    """Manually kick the daily refresh. Returns the result synchronously
    so the admin can see exactly what happened.
    """
    from flask import session
    from test.webapp.services import mirror_scheduler

    triggered_by = (session.get("v2_user") or {}).get("email")
    result = mirror_scheduler.run_now(triggered_by=triggered_by)
    return jsonify(result)


@diag_bp.get("/api/mirror/status")
@require_admin
def diag_mirror_status():
    from test.webapp.services import mirror, mirror_scheduler
    return jsonify({
        "freshness":   mirror.mirror_freshness(),
        "recent_runs": mirror.list_recent_refresh_runs(limit=20),
        "next_run":    mirror_scheduler.next_run_at(),
    })


@diag_bp.post("/api/ping")
@require_admin
def diag_ping():
    """Fire one live POST against the reporting API and return everything
    we can about the round-trip.

    Body (JSON, optional):
        {
          "report_id":   "salesline_release",   // default
          "params":      { "CustomerAccount": "11528" }, // SP params, raw
          "timeout_s":   30                     // override the client default
        }
    """
    body = request.get_json(silent=True) or {}
    report_id = (body.get("report_id") or "salesline_release").strip()
    sp_params = body.get("params") if isinstance(body.get("params"), dict) else {}
    try:
        timeout_s = int(body.get("timeout_s") or os.environ.get("REPORTING_API_TIMEOUT_SECONDS", "120"))
    except (TypeError, ValueError):
        timeout_s = 120

    if not reporting_api.is_configured():
        return jsonify({
            "ok": False,
            "stage": "config",
            "error": "REPORTING_API_BASE_URL is not set",
        }), 200

    base = os.environ["REPORTING_API_BASE_URL"].rstrip("/")
    url = f"{base}/api/reports/{report_id}/run"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    api_key = os.environ.get("REPORTING_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key

    log.info("diag/ping: POST %s timeout=%ds params=%s", url, timeout_s, sp_params)
    started = time.monotonic()
    try:
        resp = requests.post(url, headers=headers, json=sp_params, timeout=timeout_s)
        elapsed_ms = int((time.monotonic() - started) * 1000)
    except requests.RequestException as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return jsonify({
            "ok": False,
            "stage": "network",
            "error": f"{type(exc).__name__}: {exc}",
            "url": url,
            "params_sent": sp_params,
            "timeout_s": timeout_s,
            "elapsed_ms": elapsed_ms,
        }), 200

    body_bytes = resp.content or b""
    try:
        parsed = resp.json()
    except ValueError:
        parsed = None

    sample_row = None
    row_count = None
    columns = None
    if isinstance(parsed, dict):
        rows = parsed.get("rows")
        if isinstance(rows, list):
            row_count = len(rows)
            sample_row = rows[0] if rows else None
        cols = parsed.get("columns")
        if isinstance(cols, list):
            columns = cols
        elif sample_row:
            columns = list(sample_row.keys())

    return jsonify({
        "ok": resp.ok,
        "stage": "response",
        "url": url,
        "params_sent": sp_params,
        "timeout_s": timeout_s,
        "elapsed_ms": elapsed_ms,
        "http_status": resp.status_code,
        "bytes_received": len(body_bytes),
        "json_parsed": parsed is not None,
        "row_count": row_count,
        "columns": columns,
        "sample_row": sample_row,
        "raw_body_preview": (body_bytes[:1500].decode("utf-8", errors="replace")
                             if not parsed else None),
    })
