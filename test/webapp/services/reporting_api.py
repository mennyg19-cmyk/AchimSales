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


# America/New_York handles DST automatically -- emits -04:00 in DST and
# -05:00 the rest of the year. Loaded once at import; cheap to reuse.
try:
    from zoneinfo import ZoneInfo
    _EASTERN = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover -- only hits if tzdata is unavailable
    log.warning("zoneinfo unavailable; falling back to fixed -05:00 (no DST)")
    from datetime import timezone as _tz, timedelta as _td
    _EASTERN = _tz(_td(hours=-5), name="EST")


def _format_eastern(dt) -> str:
    """Format a date-or-datetime as 'YYYY-MM-DD HH:MM:SS-OFFSET' anchored
    in America/New_York. Date-only inputs are anchored at 00:00:00 in
    Eastern Time -- callers should pass a real datetime if they want
    end-of-day.
    """
    from datetime import date, datetime, time
    if isinstance(dt, datetime):
        d = dt if dt.tzinfo else dt.replace(tzinfo=_EASTERN)
        d = d.astimezone(_EASTERN)
    elif isinstance(dt, date):
        d = datetime.combine(dt, time(0, 0, 0), tzinfo=_EASTERN)
    else:
        raise TypeError(f"Cannot format non-date value: {dt!r}")

    # SP wants 'YYYY-MM-DD HH:MM:SS-04:00' (space separator, explicit
    # offset, no microseconds, no T).
    base = d.strftime("%Y-%m-%d %H:%M:%S")
    off  = d.strftime("%z")  # "-0400" or "-0500"
    if off and len(off) == 5:
        off = off[:3] + ":" + off[3:]  # -0400 -> -04:00
    return base + off


def _resolve_period(p: dict) -> tuple[str | None, str | None]:
    """Resolve the form's period selector into (date_from, date_to)
    formatted strings ready for the SP's CreatedDateTimeFrom / To.

    The filter form sends:
        period=daily|last_7_days|mtd|ytd|all_time|custom
        start_date=YYYY-MM-DD  (custom only)
        end_date=YYYY-MM-DD    (custom only)

    The SP expects 24-hour datetimes in Eastern Time:
        from: 'YYYY-MM-DD 00:00:00-04:00'  (start of the first day)
        to:   'YYYY-MM-DD 23:59:59-04:00'  (end of the last day)

    The offset is whichever Eastern offset is current (handles DST).
    Mirrors core.dates.parse_period() for the date math itself.
    """
    from datetime import date, datetime, time

    period = (p.get("period") or "").strip().lower()
    start_raw = (p.get("start_date") or "").strip()
    end_raw   = (p.get("end_date") or "").strip()

    # All time: no date filter at all (let the SP decide).
    if period in ("all_time", ""):
        return (None, None)

    start_date: date | None = None
    end_date: date | None = None

    # Custom: dates picked manually.
    if period == "custom" or (start_raw and end_raw and not period):
        try:
            if start_raw:
                start_date = datetime.strptime(start_raw[:10], "%Y-%m-%d").date()
            if end_raw:
                end_date = datetime.strptime(end_raw[:10], "%Y-%m-%d").date()
        except ValueError as exc:
            log.warning("Could not parse custom date range %r..%r: %s",
                        start_raw, end_raw, exc)
            return (None, None)
    else:
        # Named period: defer to core.dates.parse_period().
        try:
            from core.dates import parse_period
            spec = parse_period(period)
            start_date = spec.start_date
            end_date   = spec.end_date
        except Exception as exc:
            log.warning("Could not resolve period %r: %s", period, exc)
            return (None, None)

    # Anchor each side to the right wall-clock moment in Eastern time.
    out_from = _format_eastern(
        datetime.combine(start_date, time(0, 0, 0), tzinfo=_EASTERN)
    ) if start_date else None
    out_to = _format_eastern(
        datetime.combine(end_date, time(23, 59, 59), tzinfo=_EASTERN)
    ) if end_date else None
    return (out_from, out_to)


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


# ---------------------------------------------------------------------------
# Filter dropdown lookups (non-blocking)
# ---------------------------------------------------------------------------
#
# Until the brother delivers the dedicated salesman/customer SPs, the dropdown
# data is derived from an unfiltered salesline_release call. That call is
# slow (30-120s) so we MUST NOT block the form's HTTP request on it -- the
# user reported the live preview panel was getting stuck behind it.
#
# Strategy:
#   - lookup_status() / list_salesmen() / list_customers() never block. They
#     return (status, []) the first time, kick off a background populate,
#     and return real rows on subsequent calls once the populate completes.
#   - When the new lookup SPs land we'll just rewrite these to call them
#     directly (and the dropdowns will populate in one round-trip).

_LOOKUP_KEY = f"__lookups__:{_LOOKUP_BASE_REPORT}"

# Tracks the in-flight populate, if any. Guarded by _LOOKUP_LOCK.
_LOOKUP_LOCK = threading.Lock()
_lookup_thread: threading.Thread | None = None
_lookup_state: dict[str, Any] = {
    "status": "idle",     # idle | loading | ready | error
    "started_at": None,
    "finished_at": None,
    "elapsed_ms": None,
    "row_count": 0,
    "error": None,
}


def _populate_lookups_blocking() -> None:
    """Background-thread worker: fetch lookup rows and stuff them into the
    cache. Updates _lookup_state with progress.
    """
    global _lookup_thread
    started = time.monotonic()
    _lookup_state.update(
        status="loading",
        started_at=time.time(),
        finished_at=None,
        elapsed_ms=None,
        row_count=0,
        error=None,
    )
    try:
        rows = run(_LOOKUP_BASE_REPORT, {})
        _cache.set(_LOOKUP_KEY, rows)
        elapsed = int((time.monotonic() - started) * 1000)
        _lookup_state.update(
            status="ready",
            finished_at=time.time(),
            elapsed_ms=elapsed,
            row_count=len(rows),
            error=None,
        )
        log.info("lookup populate ok: %d rows in %d ms", len(rows), elapsed)
    except Exception as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        _lookup_state.update(
            status="error",
            finished_at=time.time(),
            elapsed_ms=elapsed,
            error=str(exc),
        )
        log.exception("lookup populate failed after %d ms: %s", elapsed, exc)
    finally:
        with _LOOKUP_LOCK:
            _lookup_thread = None


def _kick_lookup_populate() -> None:
    """Start a background populate if one isn't already in flight."""
    global _lookup_thread
    if not is_configured():
        return
    with _LOOKUP_LOCK:
        if _lookup_thread is not None and _lookup_thread.is_alive():
            return  # already loading
        t = threading.Thread(
            target=_populate_lookups_blocking,
            name="reporting-api-lookups",
            daemon=True,
        )
        _lookup_thread = t
        t.start()


def _cached_lookup_rows() -> list[dict]:
    """Return the cached lookup rows (or [] if not ready yet)."""
    fresh = _cache.get(_LOOKUP_KEY, max_age_s=_lookup_ttl())
    if fresh is not None:
        return fresh
    return _cache.get(_LOOKUP_KEY, max_age_s=_stale_ttl()) or []


def lookup_status() -> dict[str, Any]:
    """Snapshot of the lookup populate state. The form polls this so it
    can show "Loading..." / row count / error text.
    """
    state = dict(_lookup_state)
    state["configured"] = is_configured()
    state["cached_row_count"] = len(_cached_lookup_rows())
    return state


def list_salesmen() -> list[dict]:
    """Distinct salesmen (SalesGroup) from cached lookup rows.

    NEVER blocks. Returns whatever's cached today; kicks off a background
    populate if nothing is cached yet.
    """
    rows = _cached_lookup_rows()
    if not rows:
        _kick_lookup_populate()
        return []

    seen: set[str] = set()
    for r in rows:
        sg = r.get("SalesGroup")
        if sg in (None, "", "NULL"):
            continue
        seen.add(str(sg).strip())
    return [{"key": s, "name": s} for s in sorted(seen)]


def list_customers(salesman: str | None = None) -> list[dict]:
    """Distinct customers from cached lookup rows. NEVER blocks."""
    rows = _cached_lookup_rows()
    if not rows:
        _kick_lookup_populate()
        return []

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
