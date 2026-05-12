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


@diag_bp.get("/api/probe/customer-history")
@require_admin
def diag_probe_customer_history():
    """Call salesline_release for ONE customer over the full go-live
    window so we can see whether the SP returns historical orders for a
    customer the dashboard currently lists as "no orders". Used to
    debug the last-order backfill.

    Query params:
        account   -- the CustomerAccount to probe (required)
        days      -- override the lookback in days (default: since
                     D365 go-live; pass e.g. 365 for a tighter range)
    """
    from core.dates import D365_GO_LIVE, get_today_eastern
    from test.webapp.services import reporting_api

    account = (request.args.get("account") or "").strip()
    if not account:
        return jsonify({"ok": False, "error": "account query param required"}), 400

    try:
        days = int(request.args.get("days") or 0)
    except (TypeError, ValueError):
        days = 0

    today = get_today_eastern()
    if days > 0:
        from datetime import timedelta
        start = (today - timedelta(days=days)).isoformat()
    else:
        start = D365_GO_LIVE.isoformat()

    params = {
        "period":     "custom",
        "start_date": start,
        "end_date":   today.isoformat(),
        "customers":  account,
        "company":    os.environ.get("REPORTING_API_DEFAULT_COMPANY") or "ACHM",
    }

    try:
        rows = reporting_api.run("ordered", params, no_piggyback=True)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "account": account,
            "params": params,
            "error": f"{type(exc).__name__}: {exc}",
        }), 200

    return jsonify({
        "ok": True,
        "account": account,
        "params": params,
        "row_count": len(rows),
        "first_rows": rows[:3],
        "distinct_customer_accounts_returned":
            sorted({(r.get("CustomerAccount") or r.get("customeraccount") or "") for r in rows[:200]}),
    })


@diag_bp.get("/api/mirror/salesline")
@require_admin
def diag_salesline_dump():
    """Inspect what's actually in mirror_salesline.

    Query params:
        customer  -- filter to one CustomerAccount (case-insensitive)
        order     -- filter to one SalesOrderNumber
        date_from -- order_date >= this (YYYY-MM-DD)
        date_to   -- order_date <= this (YYYY-MM-DD)
        limit     -- max rows to return (default 100, max 1000)
        offset    -- paging offset
        raw       -- "1" to also include the raw_json blob per row

    Always returns:
        total            -- matching row count
        distinct_orders  -- distinct SalesOrderNumber count in match
        distinct_customers -- distinct CustomerAccount count in match
        earliest_order_date / latest_order_date for the match
        rows             -- requested page, normalized columns
    """
    from test.webapp.db import connect
    from test.webapp.services import mirror
    mirror.init_mirror_db()

    customer = (request.args.get("customer") or "").strip().upper()
    order_no = (request.args.get("order") or "").strip()
    date_from = (request.args.get("date_from") or "").strip()[:10]
    date_to = (request.args.get("date_to") or "").strip()[:10]
    include_raw = request.args.get("raw") == "1"
    try:
        limit = max(1, min(int(request.args.get("limit") or 100), 1000))
    except (TypeError, ValueError):
        limit = 100
    try:
        offset = max(0, int(request.args.get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0

    where: list[str] = []
    params: list[Any] = []
    if customer:
        where.append("customer_account = ?")
        params.append(customer)
    if order_no:
        where.append("sales_order_number = ?")
        params.append(order_no)
    if date_from:
        where.append("order_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("order_date <= ?")
        params.append(date_to)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    cols = (
        "sales_order_number, line_number, customer_account, customer_name, "
        "sales_group, order_date, created_datetime, po_number, item_number, "
        "item_name, unit_price, order_status, status, qty_ordered, qty_shipped, "
        "qty_cancelled, ordered_dollars, shipped_dollars, cancelled_dollars, "
        "first_seen_utc, last_seen_utc"
    )
    if include_raw:
        cols += ", raw_json"

    with connect() as conn:
        agg = conn.execute(
            "SELECT COUNT(*) AS total, "
            "       COUNT(DISTINCT sales_order_number) AS distinct_orders, "
            "       COUNT(DISTINCT customer_account)   AS distinct_customers, "
            "       MIN(order_date) AS earliest_order_date, "
            "       MAX(order_date) AS latest_order_date "
            "FROM mirror_salesline" + where_sql,
            params,
        ).fetchone()
        page = conn.execute(
            f"SELECT {cols} FROM mirror_salesline{where_sql} "
            "ORDER BY order_date DESC, sales_order_number DESC, line_number "
            "LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()

    return jsonify({
        "filters": {
            "customer": customer or None,
            "order":    order_no or None,
            "date_from": date_from or None,
            "date_to":   date_to or None,
        },
        "total":              int(agg["total"] or 0) if agg else 0,
        "distinct_orders":    int(agg["distinct_orders"] or 0) if agg else 0,
        "distinct_customers": int(agg["distinct_customers"] or 0) if agg else 0,
        "earliest_order_date": (agg["earliest_order_date"] if agg else None),
        "latest_order_date":   (agg["latest_order_date"] if agg else None),
        "limit":  limit,
        "offset": offset,
        "rows":   [dict(r) for r in page],
    })


@diag_bp.get("/api/mirror/customer-match")
@require_admin
def diag_customer_match():
    """Compare customer_account values between mirror_customers and
    mirror_salesline. Surfaces whether the dashboard's "customers with no
    orders" buckets are real (customer simply didn't order in the window)
    or a formatting mismatch between the two endpoints.
    """
    from test.webapp.db import connect
    from test.webapp.services import mirror
    mirror.init_mirror_db()
    with connect() as conn:
        cust_accts = {r["customer_account"] for r in conn.execute(
            "SELECT customer_account FROM mirror_customers"
        ) if r["customer_account"]}
        sale_accts = {r["customer_account"] for r in conn.execute(
            "SELECT DISTINCT customer_account FROM mirror_salesline "
            "WHERE customer_account IS NOT NULL AND customer_account <> ''"
        )}
        # Pull a few raw-JSON samples so we can compare what the two
        # endpoints actually return for CustomerAccount.
        cust_samples = [dict(r) for r in conn.execute(
            "SELECT customer_account, raw_json FROM mirror_customers LIMIT 3"
        )]
        sale_samples = [dict(r) for r in conn.execute(
            "SELECT customer_account, raw_json FROM mirror_salesline LIMIT 3"
        )]

    in_both = cust_accts & sale_accts
    only_cust = cust_accts - sale_accts
    only_sale = sale_accts - cust_accts

    def _sample(s: set[str], n: int = 10) -> list[str]:
        return sorted(s)[:n]

    return jsonify({
        "customers_total":            len(cust_accts),
        "salesline_distinct_accts":   len(sale_accts),
        "in_both":                    len(in_both),
        "only_in_customer_master":    len(only_cust),
        "only_in_salesline":          len(only_sale),
        "sample_only_in_customer_master": _sample(only_cust),
        "sample_only_in_salesline":       _sample(only_sale),
        "sample_in_both":                 _sample(in_both),
        "sample_customer_master_rows":    cust_samples,
        "sample_salesline_rows":          sale_samples,
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
