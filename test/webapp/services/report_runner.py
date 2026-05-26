"""Run a report and return the multi-tab payload the viewer expects.

Reports wired to real data so far (via the on-prem reporting API at
REPORTING_API_BASE_URL):

  * **ordered**  -- salesline_release SP
  * **invoiced** -- invoiced_order_charges SP

All other reports are intentionally hidden from the homepage until they
get their own SP + builder; calling run_report() for an unwired key
raises a clear error so we never silently serve fake numbers.

Output shape (what /api/reports/<key>/run serialises):

    {
        "report_key":   "ordered",
        "report_name":  "Ordered Report",
        "generated_at": "2026-04-29T18:00:00Z",
        "params":       { ... echoed filter params ... },
        "tabs":         [ ... ],
        "data_source":  {
            "source":      "api" | "fresh_cache" | "stale_cache" | "mirror_after_failure" | "mirror_no_api",
            "label":       <human label>,
            "endpoint":    <full URL we POSTed to>,
            "request_body":<exact JSON we sent>,
            "elapsed_ms":  <int>,
            ...
        }
    }

Column types drive formatting in both the grid and the Excel export:
    text | int | money | percent | date
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from test.webapp.services.reports import ordered as ordered_builder
from test.webapp.services.reports import invoiced as invoiced_builder
from test.webapp.services.reports import salesman as salesman_builder
from test.webapp.services.reports import number_4 as number_4_builder
from test.webapp.services.reports import customer_activity as customer_activity_builder
from test.webapp.services import reporting_api

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared source-metadata helpers
# ---------------------------------------------------------------------------


_SOURCE_LABEL_MAP = {
    "api":                  "Reporting API (live data)",
    "fresh_cache":          "Reporting API (cached, less than a few minutes old)",
    "stale_cache":          "Cached snapshot (live API was unreachable)",
    "mirror_first":         "SQLite mirror (daily-fresh; click Refresh data for live)",
    "mirror_after_failure": "SQLite mirror (live API was unreachable)",
    "mirror_no_api":        "SQLite mirror (API not configured)",
}


def _source_meta(request_preview: dict, rows: list[dict], elapsed_ms: int) -> dict:
    """Build the data_source envelope from the last reporting_api.run() call."""
    actual = reporting_api.last_run_source() or {}
    actual_source = actual.get("source", "api")
    meta = {
        "source":       actual_source,
        "label":        _SOURCE_LABEL_MAP.get(actual_source, "Reporting API"),
        "rows_fetched": len(rows),
        "elapsed_ms":   elapsed_ms,
        "timeout_s":    int(os.environ.get("REPORTING_API_TIMEOUT_SECONDS", "120")),
        "endpoint":     request_preview.get("url"),
        "request_body": request_preview.get("body"),
    }
    if actual.get("reason"):
        meta["fallback_reason"] = actual["reason"]
    return meta


# ---------------------------------------------------------------------------
# Per-report builders
# ---------------------------------------------------------------------------


def _build_ordered(params: dict) -> tuple[list[dict], dict]:
    """Build the ordered report's multi-tab payload + source metadata.

    Source-selection order:
        1. Reporting API (on-prem via Hybrid Connection).
        2. Reporting API client's cache / SQLite mirror fallback.

    There is no fixture or random-mock fallback. If API + mirror cannot
    satisfy the request, the caller gets a clear error instead of fake rows.
    """
    request_preview = reporting_api.preview("ordered", params)
    api_started = time.monotonic()
    try:
        rows = reporting_api.run("ordered", params)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - api_started) * 1000)
        log.exception("Ordered report fetch failed after %d ms: %s", elapsed_ms, exc)
        raise RuntimeError(f"Ordered report data unavailable from API or mirror: {exc}") from exc

    elapsed_ms = int((time.monotonic() - api_started) * 1000)
    actual = reporting_api.last_run_source() or {}
    log.info("ordered report: pulled %d rows (effective source=%s) in %d ms",
             len(rows), actual.get("source", "api"), elapsed_ms)
    return ordered_builder.build(rows), _source_meta(request_preview, rows, elapsed_ms)


def _build_invoiced(params: dict) -> tuple[list[dict], dict]:
    """Build the invoiced report's multi-tab payload + source metadata.

    The new ``invoiced_order_charges`` SP only takes a single
    ``InvoiceAccount`` value, so multi-customer requests go to the API
    with no InvoiceAccount filter (date + SalesGroup only) and we
    narrow to the user's selected accounts after the fact. The mirror
    layer receives every row that came back from the API regardless
    so offline fallbacks see the full window.
    """
    request_preview = reporting_api.preview("invoiced", params)
    api_started = time.monotonic()
    try:
        rows = reporting_api.run("invoiced", params)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - api_started) * 1000)
        log.exception("Invoiced report fetch failed after %d ms: %s", elapsed_ms, exc)
        raise RuntimeError(f"Invoiced report data unavailable from API or mirror: {exc}") from exc
    elapsed_ms = int((time.monotonic() - api_started) * 1000)

    # Multi-customer post-filter. Single-customer requests already
    # passed InvoiceAccount to the SP / mirror so no extra work needed.
    selected = params.get("customers") if isinstance(params, dict) else None
    if isinstance(selected, (list, tuple, set)):
        accts = {str(c).strip().upper() for c in selected if str(c).strip()}
    elif selected:
        accts = {str(selected).strip().upper()}
    else:
        accts = set()
    if len(accts) >= 2:
        def _acct(r: dict) -> str:
            v = r.get("InvoiceAccount") or r.get("CustomerAccount") or r.get("AccountNum")
            return str(v or "").strip().upper()
        rows = [r for r in rows if _acct(r) in accts]

    actual = reporting_api.last_run_source() or {}
    log.info("invoiced report: pulled %d rows (effective source=%s) in %d ms",
             len(rows), actual.get("source", "api"), elapsed_ms)
    return invoiced_builder.build(rows), _source_meta(request_preview, rows, elapsed_ms)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _build_salesman(params: dict) -> tuple[list[dict], dict]:
    """Build the Monthly Salesman Report payload.

    Source: ``invoiced_order_charges`` SP, full prior + current year
    window driven by the form's ``year`` parameter (or the current
    Eastern-time year when missing).
    """
    from core.dates import get_today_eastern

    raw_year = (params or {}).get("year")
    try:
        year = int(raw_year) if raw_year not in (None, "") else None
    except (TypeError, ValueError):
        year = None
    if not year:
        year = get_today_eastern().year

    request_preview = reporting_api.preview("salesman", params)
    api_started = time.monotonic()
    try:
        rows = reporting_api.run("salesman", params)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - api_started) * 1000)
        log.exception("Salesman report fetch failed after %d ms: %s", elapsed_ms, exc)
        raise RuntimeError(
            f"Salesman report data unavailable from API or mirror: {exc}"
        ) from exc
    elapsed_ms = int((time.monotonic() - api_started) * 1000)

    actual = reporting_api.last_run_source() or {}
    log.info("salesman report: pulled %d rows (effective source=%s) in %d ms",
             len(rows), actual.get("source", "api"), elapsed_ms)
    return salesman_builder.build(rows, year=year), _source_meta(request_preview, rows, elapsed_ms)


def _build_number_4(params: dict) -> tuple[list[dict], dict]:
    """Build the Number 4 Report payload.

    Source: the new ``invoice_lines`` SP. Window is a rolling 13
    months ending today so the builder has data for both the 12-month
    pivot and the YTD pivot in a single fetch.
    """
    from core.dates import get_today_eastern

    today = get_today_eastern()
    request_preview = reporting_api.preview("number_4", params)
    api_started = time.monotonic()
    try:
        rows = reporting_api.run("number_4", params)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - api_started) * 1000)
        log.exception("Number 4 report fetch failed after %d ms: %s", elapsed_ms, exc)
        raise RuntimeError(
            f"Number 4 report data unavailable from API: {exc}"
        ) from exc
    elapsed_ms = int((time.monotonic() - api_started) * 1000)

    actual = reporting_api.last_run_source() or {}
    log.info("number_4 report: pulled %d rows (effective source=%s) in %d ms",
             len(rows), actual.get("source", "api"), elapsed_ms)
    return number_4_builder.build(rows, today=today), _source_meta(request_preview, rows, elapsed_ms)


def _build_customer_activity(params: dict) -> tuple[list[dict], dict]:
    """Build the Customer Activity payload.

    Source: the customer_master mirror (full customer universe) joined
    to ``salesline_release`` SP results over the D365-go-live-to-today
    window so we have a "last order" per customer.
    """
    request_preview = reporting_api.preview("customer_activity", params)
    api_started = time.monotonic()
    try:
        rows = reporting_api.run("customer_activity", params)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - api_started) * 1000)
        log.exception("Customer Activity fetch failed after %d ms: %s", elapsed_ms, exc)
        raise RuntimeError(
            f"Customer Activity data unavailable from API or mirror: {exc}"
        ) from exc
    elapsed_ms = int((time.monotonic() - api_started) * 1000)

    actual = reporting_api.last_run_source() or {}
    log.info("customer_activity: pulled %d salesline rows (effective source=%s) in %d ms",
             len(rows), actual.get("source", "api"), elapsed_ms)
    return (
        customer_activity_builder.build(rows, params=params),
        _source_meta(request_preview, rows, elapsed_ms),
    )


_BUILDERS = {
    "ordered":           _build_ordered,
    "invoiced":          _build_invoiced,
    "salesman":          _build_salesman,
    "number_4":          _build_number_4,
    "customer_activity": _build_customer_activity,
}


def _apply_tab_rules(report_key: str, params: dict, tabs: list[dict]) -> list[dict]:
    """Apply live-style tab visibility rules.

    Ordered report parity:
      - when a concrete salesman filter is applied, omit the "By Salesman" tab
        (the workbook is already scoped to one/many salesmen).

    Invoiced report parity:
      - when a concrete salesman filter is applied (i.e. the request is
        a "shipped report" run for one salesman), omit the Commissions
        tab. Mirrors the live ``InvoicedReportRunner._run_standard`` rule
        ``skip_commissions = bool(salesman_filter)`` which keeps salesmen
        from ever seeing commission data. ``scope_params_for_user``
        forces ``salesman`` for non-privileged roles, so salesmen always
        hit this branch.
    """
    out = list(tabs or [])
    has_salesman_scope = bool((params or {}).get("salesman") or (params or {}).get("salesman_list"))
    if report_key == "ordered":
        if has_salesman_scope:
            out = [t for t in out if str(t.get("key")) != "by_salesman"]
    elif report_key == "invoiced":
        if has_salesman_scope:
            out = [t for t in out if str(t.get("key")) != "commissions"]
    return out


def run_report(report_key: str, report_name: str, params: dict) -> dict[str, Any]:
    """Return the full multi-tab payload for a report.

    Raises KeyError for any report that hasn't been wired to a real
    data source yet, so callers learn about it loudly instead of
    silently serving fake numbers.
    """
    builder = _BUILDERS.get(report_key)
    if builder is None:
        raise KeyError(
            f"Report '{report_key}' is not wired to a data source yet. "
            f"Only the following reports are runnable: {sorted(_BUILDERS)}"
        )

    tabs, source_meta = builder(params)

    return {
        "report_key":   report_key,
        "report_name":  report_name,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "params":       params,
        "tabs":         _apply_tab_rules(report_key, params, tabs),
        "data_source":  source_meta,
    }
