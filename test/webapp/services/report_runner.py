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
            "source":      "reporting_api" | "fixture",
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

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from test.webapp.services.reports import ordered as ordered_builder
from test.webapp.services import reporting_api

log = logging.getLogger(__name__)


# Path to the JSON fixture stashed from the brother's test dump. Used as a
# fallback when the reporting API is unreachable AND no stale cache exists.
_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"
_ORDERED_FIXTURE = _FIXTURE_DIR / "ordered_dump.json"


# ---------------------------------------------------------------------------
# Fixture helpers (used only when the API is unreachable)
# ---------------------------------------------------------------------------


def _load_ordered_fixture() -> list[dict] | None:
    if not _ORDERED_FIXTURE.exists():
        return None
    try:
        with _ORDERED_FIXTURE.open(encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not read ordered fixture %s: %s", _ORDERED_FIXTURE, exc)
    return None


def _filter_ordered_fixture(rows: list[dict], params: dict) -> list[dict]:
    """Apply a few obvious filters to the fixture so it at least reflects
    the chosen filters during local dev / API-down scenarios.
    """
    out = rows
    status = params.get("status")
    if status:
        out = [r for r in out if (r.get("SalesStatus") or "").lower() == str(status).lower()]
    customers = params.get("customers")
    if customers:
        if isinstance(customers, str):
            customers = [customers]
        wanted = {str(c) for c in customers}
        out = [r for r in out if str(r.get("CustomerAccount")) in wanted]
    return out


# ---------------------------------------------------------------------------
# Per-report builders
# ---------------------------------------------------------------------------


def _build_ordered(params: dict) -> tuple[list[dict], dict]:
    """Build the ordered report's multi-tab payload + source metadata.

    Source-selection order:
        1. Reporting API (on-prem via Hybrid Connection) — preferred when
           REPORTING_API_BASE_URL is set. The client also handles fresh +
           stale caching internally.
        2. JSON fixture stashed in test/fixtures/ordered_dump.json — used
           in local dev (no env vars) or when the API is unreachable AND
           no stale cache exists.

    There is no random-mock fallback. If neither source works, an empty
    payload is returned and the badge will say so.
    """
    rows: list[dict] | None = None
    source: dict[str, Any] = {"source": "unknown"}

    if reporting_api.is_configured() and os.environ.get("USE_REPORTING_API_ORDERED", "1") != "0":
        # Pre-compute the body we'll send so the UI can show it even on
        # failure or fallback.
        request_preview = reporting_api.preview("ordered", params)
        api_started = time.monotonic()
        try:
            rows = reporting_api.run("ordered", params)
            elapsed_ms = int((time.monotonic() - api_started) * 1000)
            log.info("ordered report: pulled %d rows from reporting API in %d ms",
                     len(rows), elapsed_ms)
            source = {
                "source":       "reporting_api",
                "label":        "Reporting API (live data)",
                "rows_fetched": len(rows),
                "elapsed_ms":   elapsed_ms,
                "timeout_s":    int(os.environ.get("REPORTING_API_TIMEOUT_SECONDS", "120")),
                "endpoint":     request_preview.get("url"),
                "request_body": request_preview.get("body"),
            }
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - api_started) * 1000)
            log.exception(
                "Reporting API fetch for ordered failed after %d ms, falling back to fixture: %s",
                elapsed_ms, exc,
            )
            rows = None
            source = {
                "source":       "reporting_api_failed",
                "label":        "API call failed — see fallback below",
                "error":        str(exc),
                "elapsed_ms":   elapsed_ms,
                "timeout_s":    int(os.environ.get("REPORTING_API_TIMEOUT_SECONDS", "120")),
                "endpoint":     request_preview.get("url"),
                "request_body": request_preview.get("body"),
            }

    if rows is None:
        fixture_rows = _load_ordered_fixture()
        if fixture_rows is not None:
            log.info("ordered report: using fixture (%d rows)", len(fixture_rows))
            rows = _filter_ordered_fixture(fixture_rows, params)
            previous = source if source.get("source") == "reporting_api_failed" else None
            source = {
                "source": "fixture",
                "label":  "Fixture (test data dump) — not real data",
                "rows_fetched": len(rows),
                "fixture_file": str(_ORDERED_FIXTURE),
            }
            if previous:
                source["api_error"] = previous.get("error")
                if previous.get("elapsed_ms") is not None:
                    source["elapsed_ms"] = previous["elapsed_ms"]
                if previous.get("timeout_s") is not None:
                    source["timeout_s"] = previous["timeout_s"]
                if previous.get("request_body") is not None:
                    source["request_body"] = previous["request_body"]
                if previous.get("endpoint"):
                    source["endpoint"] = previous["endpoint"]

    if rows is not None:
        return ordered_builder.build(rows), source

    # Last resort: nothing worked. Return a single empty Summary tab so the
    # viewer doesn't crash, and label it clearly.
    log.warning("ordered report: no API + no fixture available")
    return ordered_builder.build([]), {
        "source": "no_data",
        "label":  "No data source available — check API config",
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


_BUILDERS = {
    "ordered": _build_ordered,
}


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
        "tabs":         tabs,
        "data_source":  source_meta,
    }
