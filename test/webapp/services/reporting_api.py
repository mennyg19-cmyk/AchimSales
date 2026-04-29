"""HTTP client for the on-prem Reporting API.

Architecture (from the brother's project dump):

    Browser  ->  Azure web app  ->  Hybrid Connection
              ->  on-prem reporting API (aic-inordera:8080)
              ->  SQL Server

The Flask app talks to the reporting API over HTTP. The reporting API
calls the stored procedure and returns JSON.

Endpoint shape:
    POST {REPORTING_API_BASE_URL}/api/reports/{report_id}/run
    Headers: X-API-Key: <REPORTING_API_KEY>, Content-Type: application/json
    Body:    { <filter params, PascalCase> }
    Returns: { columns, report_id, row_count, rows: [ { ... }, ... ] }

Environment
-----------
REPORTING_API_BASE_URL
    Base URL, e.g. http://aic-inordera:8080. If unset, the client is
    "not configured" and run() will fall back through the resolution
    chain in report_runner.

REPORTING_API_KEY
    API key sent in the X-API-Key header.

REPORTING_API_TIMEOUT_SECONDS
    Per-request timeout (default 60).

REPORTING_API_CACHE_TTL_SECONDS
    Fresh-cache TTL in seconds (default 300 = 5 minutes). Set to 0 to
    disable caching.

REPORTING_API_CACHE_STALE_TTL_SECONDS
    Stale-cache TTL in seconds (default 86400 = 24 hours). When the API
    is unreachable but a stale cached response is younger than this, we
    return the stale rows.

Report-id mapping
-----------------
The in-app report key (e.g. "ordered") is mapped to the API's report_id
(e.g. "salesline_release") via REPORT_ID_MAP. When we add more reports
we just extend that dict.

Filter translation
------------------
The viewer's filter form uses lowercase / snake_case keys for sharing
across reports. Each report has a translator that turns those into the
PascalCase parameter names the SP expects. See _translate_ordered.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Callable

import requests

log = logging.getLogger(__name__)


class ReportingApiNotConfigured(RuntimeError):
    """REPORTING_API_BASE_URL isn't set in this environment."""


class ReportingApiError(RuntimeError):
    """The reporting API returned a non-success response or was unreachable."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    return bool(os.environ.get("REPORTING_API_BASE_URL"))


def _base_url() -> str:
    base = os.environ.get("REPORTING_API_BASE_URL", "").rstrip("/")
    if not base:
        raise ReportingApiNotConfigured(
            "REPORTING_API_BASE_URL is not set; cannot call the reporting API"
        )
    return base


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    key = os.environ.get("REPORTING_API_KEY")
    if key:
        h["X-API-Key"] = key
    return h


def _timeout() -> int:
    try:
        return int(os.environ.get("REPORTING_API_TIMEOUT_SECONDS", "120"))
    except ValueError:
        return 120


def _fresh_ttl() -> int:
    try:
        return int(os.environ.get("REPORTING_API_CACHE_TTL_SECONDS", "300"))
    except ValueError:
        return 300


def _stale_ttl() -> int:
    try:
        return int(os.environ.get("REPORTING_API_CACHE_STALE_TTL_SECONDS", "86400"))
    except ValueError:
        return 86400


def _lookup_ttl() -> int:
    """Cache TTL for derived lookup lists (salesmen, customers).

    Defaults to 1h since these change rarely; can be tuned via
    REPORTING_API_LOOKUP_TTL_SECONDS.
    """
    try:
        return int(os.environ.get("REPORTING_API_LOOKUP_TTL_SECONDS", "3600"))
    except ValueError:
        return 3600


# ---------------------------------------------------------------------------
# Filter translation
# ---------------------------------------------------------------------------


def _csv(value: Any) -> str | None:
    """Coerce list-or-scalar to a comma-separated string, or None if empty."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        items = [str(x).strip() for x in value if str(x).strip()]
        return ",".join(items) if items else None
    s = str(value).strip()
    return s or None


def _resolve_period(p: dict) -> tuple[str | None, str | None]:
    """Resolve the form's period selector into (date_from_iso, date_to_iso).

    The filter form sends:
        period=daily|last_7_days|mtd|ytd|all_time|custom
        start_date=YYYY-MM-DD  (custom only)
        end_date=YYYY-MM-DD    (custom only)

    Mirrors core.dates.parse_period() so the test app uses the exact
    same period semantics as the live app.
    """
    period = (p.get("period") or "").strip().lower()
    start = (p.get("start_date") or "").strip()
    end   = (p.get("end_date") or "").strip()

    # Custom: dates picked manually
    if period == "custom" or (start and end and not period):
        return (start or None, end or None)

    # All time: no date filter at all (let the SP decide)
    if period in ("all_time", ""):
        return (None, None)

    # Named period: defer to core.dates.parse_period()
    try:
        from core.dates import parse_period
        spec = parse_period(period)
        return (spec.start_date.isoformat(), spec.end_date.isoformat())
    except Exception as exc:
        log.warning("Could not resolve period %r: %s", period, exc)
        return (None, None)


def _translate_ordered(p: dict) -> dict[str, Any]:
    """In-app filter dict -> salesline_release SP params.

    Source filter shape (what the run endpoint hands us):
        period      : daily|last_7_days|mtd|ytd|all_time|custom
        start_date  : YYYY-MM-DD  (when period=custom)
        end_date    : YYYY-MM-DD  (when period=custom)
        customers   : list[str] of CustomerAccount values
        salesman    : SalesGroup string
        status      : SalesStatus string
        order_no    : SalesOrderNumber (free text, optional)
        item        : Item code (free text, optional)
        company     : Company code (defaults to whatever the SP uses)

    SP target body (PascalCase, exactly as documented in the API dump):
        CreatedDateTimeFrom / CreatedDateTimeTo  (mapped from period)
        CustomerAccount, SalesGroup, SalesStatus,
        SalesOrderNumber, Item, Company

    Empty / unset fields are dropped so the SP can fall back to its
    own defaults.
    """
    out: dict[str, Any] = {}

    date_from, date_to = _resolve_period(p)
    if date_from:
        out["CreatedDateTimeFrom"] = date_from
    if date_to:
        out["CreatedDateTimeTo"] = date_to

    if v := _csv(p.get("customers")):
        out["CustomerAccount"] = v
    if v := _csv(p.get("salesman")):
        out["SalesGroup"] = v
    if v := _csv(p.get("status")):
        out["SalesStatus"] = v
    if v := _csv(p.get("order_no")):
        out["SalesOrderNumber"] = v
    if v := _csv(p.get("item")):
        out["Item"] = v
    if v := _csv(p.get("company")):
        out["Company"] = v

    return out


# (report_id, translator) keyed by in-app report key.
REPORT_ID_MAP: dict[str, tuple[str, Callable[[dict], dict]]] = {
    "ordered": ("salesline_release", _translate_ordered),
}


def preview(report_key: str, filter_params: dict) -> dict[str, Any]:
    """Return the exact request that *would* be sent to the reporting API
    for these filters, without actually calling the API.

    Used by the filter form (live preview) and the report viewer (audit).
    Returns:
        {
          "report_id":  "salesline_release",
          "url":        "http://aic-inordera:8080/api/reports/.../run",
          "method":     "POST",
          "body":       {<PascalCase SP params>},
          "configured": True/False,    // is REPORTING_API_BASE_URL set?
        }
    """
    entry = REPORT_ID_MAP.get(report_key)
    if entry is None:
        return {
            "report_id":  None,
            "url":        None,
            "method":     "POST",
            "body":       {},
            "configured": is_configured(),
            "warning":    f"No reporting-API mapping for report '{report_key}'",
        }
    report_id, translator = entry
    body = translator(filter_params or {})

    base = (os.environ.get("REPORTING_API_BASE_URL") or "").rstrip("/")
    url = f"{base}/api/reports/{report_id}/run" if base else None

    return {
        "report_id":  report_id,
        "url":        url,
        "method":     "POST",
        "body":       body,
        "configured": is_configured(),
    }


# ---------------------------------------------------------------------------
# Cache (in-process, per worker)
# ---------------------------------------------------------------------------


class _Cache:
    """Tiny thread-safe TTL cache.

    Each entry stores the rows + the wall-clock time they were fetched.
    Callers can ask for a "fresh" (within TTL) hit or a "stale" hit
    (older but still within stale TTL) for failover.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, tuple[float, list[dict]]] = {}

    @staticmethod
    def make_key(report_id: str, sp_params: dict) -> str:
        # Stable hash of the params so dict order doesn't matter
        canonical = json.dumps(sp_params, sort_keys=True, default=str)
        digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()
        return f"{report_id}:{digest}"

    def get(self, key: str, *, max_age_s: int) -> list[dict] | None:
        with self._lock:
            entry = self._data.get(key)
        if entry is None:
            return None
        ts, rows = entry
        if max_age_s <= 0:
            return None
        if (time.time() - ts) > max_age_s:
            return None
        return rows

    def set(self, key: str, rows: list[dict]) -> None:
        with self._lock:
            self._data[key] = (time.time(), rows)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_cache = _Cache()


def clear_cache() -> None:
    """Drop all cached responses (for tests / admin actions)."""
    _cache.clear()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(report_key: str, filter_params: dict) -> list[dict]:
    """Fetch flat rows for a report from the reporting API.

    Resolution order:
        1. Fresh cache hit (<= REPORTING_API_CACHE_TTL_SECONDS).
        2. HTTP call to the reporting API; on success, cache + return.
        3. On API failure, stale cache hit (<= STALE_TTL).
        4. Re-raise the API error so the caller can decide what to do
           (report_runner falls back to the JSON fixture from there).
    """
    entry = REPORT_ID_MAP.get(report_key)
    if entry is None:
        raise KeyError(f"No reporting-API mapping for report '{report_key}'")
    report_id, translator = entry

    sp_params = translator(filter_params or {})
    cache_key = _Cache.make_key(report_id, sp_params)

    fresh = _cache.get(cache_key, max_age_s=_fresh_ttl())
    if fresh is not None:
        log.info("reporting_api: fresh cache hit for %s (%d rows)", report_id, len(fresh))
        return fresh

    if not is_configured():
        raise ReportingApiNotConfigured(
            "REPORTING_API_BASE_URL is not set; cannot call the reporting API"
        )

    url = f"{_base_url()}/api/reports/{report_id}/run"
    log.info("reporting_api: POST %s  params=%s", url, sp_params)

    try:
        resp = requests.post(
            url,
            headers=_headers(),
            json=sp_params,
            timeout=_timeout(),
        )
        resp.raise_for_status()
        body = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("reporting_api: call to %s failed: %s", url, exc)
        stale = _cache.get(cache_key, max_age_s=_stale_ttl())
        if stale is not None:
            log.info(
                "reporting_api: serving stale cache for %s (%d rows) after API failure",
                report_id, len(stale),
            )
            return stale
        raise ReportingApiError(f"Reporting API call failed: {exc}") from exc

    rows = body.get("rows") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise ReportingApiError(
            f"Reporting API returned unexpected payload (no 'rows' list): {body!r}"
        )

    log.info("reporting_api: %s returned %d rows", report_id, len(rows))
    _cache.set(cache_key, rows)
    return rows


# ---------------------------------------------------------------------------
# Derived lookup lists (salesmen + customers)
# ---------------------------------------------------------------------------
#
# We don't have dedicated lookup endpoints yet. To populate the filter
# dropdowns on the report form we ask salesline_release for an unfiltered
# row dump and pull the distinct customer + salesman values out. Cached
# for an hour so we don't redo this on every page load.


_LOOKUP_BASE_REPORT = "ordered"  # which in-app report key to source from


def _lookup_rows() -> list[dict]:
    """Get the cached row list used to build the filter dropdowns.

    Uses the same report cache as the run() flow, so a fresh report run
    primes the lookup cache for free.
    """
    cache_key = f"__lookups__:{_LOOKUP_BASE_REPORT}"

    fresh = _cache.get(cache_key, max_age_s=_lookup_ttl())
    if fresh is not None:
        return fresh

    if not is_configured():
        raise ReportingApiNotConfigured(
            "REPORTING_API_BASE_URL is not set; cannot derive lookups"
        )

    rows = run(_LOOKUP_BASE_REPORT, {})
    _cache.set(cache_key, rows)
    return rows


def list_salesmen() -> list[dict]:
    """Distinct salesmen (SalesGroup) seen in salesline_release.

    Returns [{"key": "<group>", "name": "<group>"}] sorted by name.
    Blank/NULL salesmen are dropped (the dump shows 'NULL' for some
    rows; until master data is available we just skip them).
    """
    rows = _lookup_rows()
    seen: set[str] = set()
    for r in rows:
        sg = r.get("SalesGroup")
        if sg in (None, "", "NULL"):
            continue
        seen.add(str(sg).strip())
    return [{"key": s, "name": s} for s in sorted(seen)]


def list_customers(salesman: str | None = None) -> list[dict]:
    """Distinct customers (CustomerAccount + customername) seen in
    salesline_release. Optionally filter to one salesman group.

    Returns [{"key": "<account>", "name": "<account> - <customername>",
              "salesman": "<group>"}] sorted by name.
    """
    rows = _lookup_rows()
    seen: dict[str, dict] = {}
    sm_filter = (salesman or "").strip() or None

    for r in rows:
        acct = r.get("CustomerAccount")
        if acct in (None, "", "NULL"):
            continue
        sg = r.get("SalesGroup")
        sg_str = "" if sg in (None, "", "NULL") else str(sg).strip()
        if sm_filter and sg_str != sm_filter:
            continue

        acct_key = str(acct).strip()
        if acct_key in seen:
            continue

        cname = r.get("customername") or ""
        display = f"{acct_key} - {cname}".strip(" -") if cname else acct_key
        seen[acct_key] = {
            "key": acct_key,
            "name": display,
            "salesman": sg_str,
        }

    return sorted(seen.values(), key=lambda c: c["name"].lower())
