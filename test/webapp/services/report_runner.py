"""Run a report and return the multi-tab payload the viewer expects.

Currently only the **ordered** report is wired to real data (via the
on-prem reporting API at REPORTING_API_BASE_URL). All other reports
are intentionally hidden from the homepage until they get their own
SP + builder; calling run_report() for an unwired key raises a clear
error so we never silently serve fake numbers.

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
from test.webapp.services import reporting_api

log = logging.getLogger(__name__)


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
    actual_source = actual.get("source", "api")
    log.info("ordered report: pulled %d rows (effective source=%s) in %d ms",
             len(rows), actual_source, elapsed_ms)
    label_map = {
        "api":                  "Reporting API (live data)",
        "fresh_cache":          "Reporting API (cached, less than a few minutes old)",
        "stale_cache":          "Cached snapshot (live API was unreachable)",
        "mirror_after_failure": "SQLite mirror (live API was unreachable)",
        "mirror_no_api":        "SQLite mirror (API not configured)",
    }
    source = {
        "source":       actual_source,
        "label":        label_map.get(actual_source, "Reporting API"),
        "rows_fetched": len(rows),
        "elapsed_ms":   elapsed_ms,
        "timeout_s":    int(os.environ.get("REPORTING_API_TIMEOUT_SECONDS", "120")),
        "endpoint":     request_preview.get("url"),
        "request_body": request_preview.get("body"),
    }
    if actual.get("reason"):
        source["fallback_reason"] = actual["reason"]
    return ordered_builder.build(rows), source


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


_BUILDERS = {
    "ordered": _build_ordered,
}


def _apply_tab_rules(report_key: str, params: dict, tabs: list[dict]) -> list[dict]:
    """Apply live-style tab visibility rules.

    Ordered report parity:
      - when a concrete salesman filter is applied, omit the "By Salesman" tab
        (the workbook is already scoped to one/many salesmen).
    """
    out = list(tabs or [])
    if report_key == "ordered":
        has_salesman_scope = bool((params or {}).get("salesman") or (params or {}).get("salesman_list"))
        if has_salesman_scope:
            out = [t for t in out if str(t.get("key")) != "by_salesman"]
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
