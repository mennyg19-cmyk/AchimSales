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
    """Format a date-or-datetime as 'YYYY-MM-DD HH:MM:SS' (Eastern wall
    clock, no offset suffix). The SP's date params are SQL Server
    `datetime`, which rejects offset suffixes -- it interprets whatever
    we send as already-Eastern, so we just convert the moment into
    Eastern wall-clock and strip the offset.

    Date-only inputs are anchored at 00:00:00 in Eastern Time --
    callers should pass a real datetime if they want end-of-day.
    """
    from datetime import date, datetime, time
    if isinstance(dt, datetime):
        d = dt if dt.tzinfo else dt.replace(tzinfo=_EASTERN)
        d = d.astimezone(_EASTERN)
    elif isinstance(dt, date):
        d = datetime.combine(dt, time(0, 0, 0), tzinfo=_EASTERN)
    else:
        raise TypeError(f"Cannot format non-date value: {dt!r}")

    # 'YYYY-MM-DD HH:MM:SS' -- space separator, no microseconds, no T,
    # no offset (SP doesn't accept it).
    return d.strftime("%Y-%m-%d %H:%M:%S")


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


_DEFAULT_COMPANY = (os.environ.get("REPORTING_API_DEFAULT_COMPANY") or "ACHM").strip()


def _translate_customer_master(p: dict) -> dict[str, Any]:
    """In-app filter dict -> usp_customer_master SP params.

    The Customer Master SP exposes these PascalCase parameters (all
    documented as optional, see customer_master_frontend_handoff.md):

        Company, AccountNum, CustomerAccount, CustomerNameContains,
        CustGroup, Currency, SalesGroup, PartyState, MarkupGroup,
        DlvMode, DlvTerm, InventSiteId,
        CreditMaxMin, CreditMaxMax,
        CreatedDateTimeFrom, CreatedDateTimeTo

    Defensive default: when no filters are supplied (the dropdown /
    nightly-mirror snapshot use case) we still send ``Company`` so the
    on-prem API has at least one parameter to bind. An empty body has
    been observed to 500 even though the spec calls all params
    optional, so this avoids relying on that promise.

    The default company comes from REPORTING_API_DEFAULT_COMPANY
    (falls back to ``ACHM``) and is only injected when the caller
    didn't already specify one.
    """
    out: dict[str, Any] = {}

    if not p:
        if _DEFAULT_COMPANY:
            out["Company"] = _DEFAULT_COMPANY
        return out

    # Pass through anything already in PascalCase.
    _PASCAL_KEYS = {
        "Company", "AccountNum", "CustomerAccount", "CustomerNameContains",
        "CustGroup", "Currency", "SalesGroup", "PartyState", "MarkupGroup",
        "DlvMode", "DlvTerm", "InventSiteId",
        "CreditMaxMin", "CreditMaxMax",
        "CreatedDateTimeFrom", "CreatedDateTimeTo",
    }
    for k in _PASCAL_KEYS:
        if k in p and p[k] not in (None, ""):
            out[k] = p[k]

    # snake_case aliases used elsewhere in this app's filter forms.
    if not out.get("CustomerNameContains"):
        if v := (p.get("name_contains") or p.get("customer_name_contains")):
            out["CustomerNameContains"] = str(v).strip()
    if not out.get("CustomerAccount"):
        if v := (p.get("customer_account") or p.get("customers")):
            out["CustomerAccount"] = _csv(v) if isinstance(v, list) else str(v).strip()
    if not out.get("SalesGroup"):
        if v := (p.get("salesman") or p.get("sales_group")):
            out["SalesGroup"] = _csv(v) if isinstance(v, list) else str(v).strip()
    if not out.get("PartyState"):
        if v := p.get("state"):
            out["PartyState"] = str(v).strip()

    # Date range in the form's period vocabulary collapses into From/To
    # using the same Eastern-time helpers as the ordered translator.
    if "CreatedDateTimeFrom" not in out and "CreatedDateTimeTo" not in out:
        date_from, date_to = _resolve_period(p)
        if date_from:
            out["CreatedDateTimeFrom"] = date_from
        if date_to:
            out["CreatedDateTimeTo"] = date_to

    # Always send Company (the on-prem API has been observed to 500 on
    # certain shapes when Company is omitted). Caller can override with
    # an explicit Company if they really need a different tenant.
    if "Company" not in out and _DEFAULT_COMPANY:
        out["Company"] = _DEFAULT_COMPANY

    return out


# (report_id, translator) keyed by in-app report key.
REPORT_ID_MAP: dict[str, tuple[str, Callable[[dict], dict]]] = {
    "ordered":         ("salesline_release", _translate_ordered),
    "customer_master": ("customer_master",   _translate_customer_master),
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


# Per-thread record of the most recent run()'s effective data source.
# Used by report builders to decorate the data_source badge with
# "served from offline mirror" notices when relevant.
_thread_local = threading.local()


def last_run_source() -> dict[str, Any] | None:
    """Return metadata about the last run() call on this thread, e.g.
    ``{"source": "api"|"fresh_cache"|"stale_cache"|"mirror"|"mirror_after_failure",
       "rows": <int>, "error": <optional>}``.
    """
    return getattr(_thread_local, "last_source", None)


def _set_last_source(**kw) -> None:
    _thread_local.last_source = kw


def clear_cache() -> None:
    """Drop all cached responses (for tests / admin actions)."""
    _cache.clear()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _kick_mirror_upsert(report_id: str, rows: list[dict]) -> None:
    """Fire-and-forget: mirror the rows into local SQLite in a worker
    thread so the user's request is never blocked on the write. Failures
    are logged but never raised.
    """
    if not rows:
        return

    def _worker() -> None:
        try:
            from test.webapp.services import mirror
            if report_id == "customer_master":
                stats = mirror.upsert_customers(rows, trigger="piggyback")
                log.info("mirror piggyback (customers): %s", stats)
            elif report_id == "salesline_release":
                stats = mirror.upsert_salesline(rows, trigger="piggyback")
                log.info("mirror piggyback (salesline): %s", stats)
        except Exception:
            log.exception("mirror piggyback failed for %s", report_id)

    t = threading.Thread(target=_worker, name=f"mirror-upsert-{report_id}",
                         daemon=True)
    t.start()


def run(report_key: str, filter_params: dict) -> list[dict]:
    """Fetch flat rows for a report from the reporting API.

    Resolution order:
        1. Fresh in-process cache hit (<= REPORTING_API_CACHE_TTL_SECONDS).
        2. HTTP call to the reporting API; on success, cache the rows,
           mirror them to local SQLite in the background, and return.
        3. On API failure, in-process stale cache hit (<= STALE_TTL).
        4. Local SQLite mirror fallback (raises MirrorWindowExceeded if
           the request is for data older than the mirror keeps).
        5. Re-raise ``ReportingApiError`` so the caller can decide what
           to do (report_runner falls back to the JSON fixture from
           there for some reports).
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
        _set_last_source(source="fresh_cache", rows=len(fresh))
        return fresh

    if not is_configured():
        # Not configured -- skip the HTTP attempt entirely and fall
        # straight through to the SQLite mirror so the dev shell can
        # still serve cached lookups / customer-last-order pages.
        from test.webapp.services.mirror import MirrorWindowExceeded
        try:
            mirror_rows = _serve_from_mirror(report_id, sp_params)
        except MirrorWindowExceeded:
            _set_last_source(source="failed",
                             error="mirror window exceeded; API not configured")
            raise
        except Exception:
            log.exception("reporting_api: mirror fallback failed (not configured path)")
            mirror_rows = None
        if mirror_rows is not None:
            log.info(
                "reporting_api: API not configured -- serving %d rows from mirror for %s",
                len(mirror_rows), report_id,
            )
            _set_last_source(source="mirror_no_api", rows=len(mirror_rows),
                             reason="API not configured")
            return mirror_rows
        _set_last_source(source="failed", error="API not configured")
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
        # Surface the server's error body in our own exception so the
        # diagnostic page (and the lookup-status banner) can show the
        # actual SQL/SP error instead of just "500 Server Error".
        if not resp.ok:
            snippet = ""
            try:
                snippet = (resp.text or "").strip()
            except Exception:
                snippet = ""
            if snippet:
                snippet = snippet[:500]
                raise requests.HTTPError(
                    f"{resp.status_code} {resp.reason} from {url}: {snippet}",
                    response=resp,
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
            _set_last_source(source="stale_cache", rows=len(stale),
                             reason=str(exc))
            return stale
        # Try the local mirror. ``MirrorWindowExceeded`` is intentionally
        # NOT caught here -- it carries a plain-English message that
        # callers should surface to the user verbatim, and the API
        # round-trip clearly isn't going to fix it.
        from test.webapp.services.mirror import MirrorWindowExceeded
        try:
            mirror_rows = _serve_from_mirror(report_id, sp_params)
        except MirrorWindowExceeded:
            _set_last_source(source="failed",
                             error="mirror window exceeded; live API down")
            raise
        except Exception:
            log.exception("reporting_api: mirror fallback failed after API error")
            mirror_rows = None
        if mirror_rows is not None:
            log.info(
                "reporting_api: serving %d rows from mirror for %s after API failure",
                len(mirror_rows), report_id,
            )
            _set_last_source(source="mirror_after_failure",
                             rows=len(mirror_rows), reason=str(exc))
            return mirror_rows
        _set_last_source(source="failed", error=str(exc))
        raise ReportingApiError(f"Reporting API call failed: {exc}") from exc

    rows = body.get("rows") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise ReportingApiError(
            f"Reporting API returned unexpected payload (no 'rows' list): {body!r}"
        )

    log.info("reporting_api: %s returned %d rows", report_id, len(rows))
    _cache.set(cache_key, rows)
    _kick_mirror_upsert(report_id, rows)
    _set_last_source(source="api", rows=len(rows))
    return rows


def _serve_from_mirror(report_id: str, sp_params: dict) -> list[dict] | None:
    """Best-effort fallback to the local SQLite mirror.

    Returns None if there's no mirror data for this report. Raises
    ``mirror.MirrorWindowExceeded`` (which the caller surfaces verbatim
    to the user) if the request asks for data older than the cache.
    """
    from test.webapp.services import mirror

    if report_id == "customer_master":
        # Customer master is a small, simple snapshot. We treat the
        # mirror as the full universe and let the caller filter
        # in-process if it wants -- the lookup paths here (customer
        # & salesman dropdowns) ignore filters anyway.
        rows = []
        try:
            from test.webapp.db import connect as _conn
            with _conn() as c:
                for r in c.execute("SELECT raw_json FROM mirror_customers"):
                    try:
                        rows.append(json.loads(r["raw_json"]))
                    except Exception:
                        pass
        except Exception:
            log.exception("mirror customer fallback read failed")
            return None
        return rows or None

    if report_id == "salesline_release":
        rows = mirror.get_salesline_fallback(
            customer_account=sp_params.get("CustomerAccount") or None,
            date_from=sp_params.get("CreatedDateTimeFrom") or None,
            date_to=sp_params.get("CreatedDateTimeTo") or None,
            status=sp_params.get("SalesStatus") or None,
        )
        return rows or None

    return None


# ---------------------------------------------------------------------------
# Filter dropdown lookups (non-blocking)
# ---------------------------------------------------------------------------
#
# Customer + salesman dropdowns on the filter form pull from
# rpt.usp_customer_master (the dedicated customer-master SP). We used to
# derive these from an unfiltered salesline_release dump, which was slow
# (30-120s) AND missed customers that hadn't placed orders recently.
#
# Strategy:
#   - lookup_status() / list_salesmen() / list_customers() never block.
#     They return whatever's cached today, kick off a background populate
#     if nothing is cached, and serve from the local SQLite mirror as a
#     final fallback so the dropdowns keep working when the API is down.


_LOOKUP_BASE_REPORT = "customer_master"  # which in-app report key to source from

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
        # ``run()`` may have served from the SQLite mirror after an API
        # failure. Either way the in-process cache now has rows, so we
        # report ``ready`` to the UI; the data-source label on the
        # report viewer still reflects where the bytes came from.
        last = last_run_source()
        source = last.get("source") if isinstance(last, dict) else None
        _lookup_state.update(
            status="ready",
            finished_at=time.time(),
            elapsed_ms=elapsed,
            row_count=len(rows),
            error=None,
            source=source or "api",
        )
        log.info("lookup populate ok: %d rows in %d ms (source=%s)",
                 len(rows), elapsed, source)
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
    cached = len(_cached_lookup_rows())
    state["cached_row_count"] = cached
    # If we have nothing in process but the SQLite mirror has rows,
    # tell the UI it can stop showing "loading" -- the dropdowns will
    # be served from the mirror.
    if cached == 0:
        try:
            from test.webapp.services import mirror
            mirror_count = (mirror.mirror_freshness().get("customers") or {}).get("rows", 0)
            state["mirror_row_count"] = mirror_count
            if mirror_count and state.get("status") != "loading":
                state["fallback_source"] = "mirror"
        except Exception:
            log.debug("lookup_status: mirror_freshness failed", exc_info=True)
    return state


def _customer_name_of(row: dict) -> str:
    """Customer name lookup that handles both customer_master
    (``CustomerName``) and salesline_release (``customername``) shapes.
    """
    return str(
        row.get("CustomerName")
        or row.get("customername")
        or ""
    ).strip()


def list_salesmen() -> list[dict]:
    """Distinct salesmen (SalesGroup). NEVER blocks.

    Sources, in order of preference:
        1. The in-process cache (populated by a background fetch from
           rpt.usp_customer_master).
        2. The local SQLite mirror, so the dropdown keeps working when
           the API is down.
    """
    rows = _cached_lookup_rows()
    if rows:
        seen: set[str] = set()
        for r in rows:
            sg = r.get("SalesGroup")
            if sg in (None, "", "NULL"):
                continue
            seen.add(str(sg).strip())
        if seen:
            return [{"key": s, "name": s} for s in sorted(seen)]

    # Nothing fresh in process. Kick off a background populate AND
    # serve whatever's in the local mirror so the user isn't blocked.
    _kick_lookup_populate()
    try:
        from test.webapp.services import mirror
        return mirror.get_salesmen_fallback()
    except Exception:
        log.exception("list_salesmen: mirror fallback failed")
        return []


def list_customers(salesman: str | None = None) -> list[dict]:
    """Distinct customers. NEVER blocks.

    Same fallback chain as list_salesmen.
    """
    rows = _cached_lookup_rows()
    if rows:
        seen: dict[str, dict] = {}
        sm_filter = (salesman or "").strip() or None
        for r in rows:
            acct = r.get("CustomerAccount") or r.get("AccountNum")
            if acct in (None, "", "NULL"):
                continue
            sg = r.get("SalesGroup")
            sg_str = "" if sg in (None, "", "NULL") else str(sg).strip()
            if sm_filter and sg_str != sm_filter:
                continue
            acct_key = str(acct).strip()
            if acct_key in seen:
                continue
            cname = _customer_name_of(r)
            display = f"{acct_key} - {cname}".strip(" -") if cname else acct_key
            seen[acct_key] = {
                "key": acct_key,
                "name": display,
                "salesman": sg_str,
            }
        if seen:
            return sorted(seen.values(), key=lambda c: c["name"].lower())

    _kick_lookup_populate()
    try:
        from test.webapp.services import mirror
        return mirror.get_customers_fallback(salesman=salesman)
    except Exception:
        log.exception("list_customers: mirror fallback failed")
        return []
