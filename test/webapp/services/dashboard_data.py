"""Endpoint-backed dashboard data for the v2 app.

The live app reads D365 OData directly. The test app rebuild uses the
reporting API instead: customer_master supplies the customer universe and
ordered/salesline_release supplies order history and detail rows.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any

from core.dates import D365_GO_LIVE, get_today_eastern
from test.webapp.db import (
    connect,
    get_app_setting,
    get_app_settings_batch,
    get_user_salesman_access,
    normalize_key,
    set_app_setting,
)
from test.webapp.services import mirror, reporting_api
from test.webapp.services.report_access import get_user_profile

log = logging.getLogger(__name__)

_DEFAULT_COMPANY = (os.environ.get("REPORTING_API_DEFAULT_COMPANY") or "ACHM").strip()
_SCOPE_ALL = "__all__"
_LAST_REQUESTED_KEY = "dashboard.last_refresh_requested"
_LAST_COMPLETED_KEY = "dashboard.last_refresh_completed"
_LAST_CUSTOMER_SOURCE_KEY = "dashboard.last_customer_source"
_LAST_ORDER_SOURCE_KEY = "dashboard.last_order_source"
_LAST_ORDER_MIRROR_STATS_KEY = "dashboard.last_order_mirror_stats"
_LAST_BACKFILL_STATS_KEY = "dashboard.last_backfill_stats"
_LAST_ERROR_KEY = "dashboard.last_refresh_error"

# Batch size for the "last order per orderless customer" backfill. The
# salesline_release SP accepts a comma-separated CustomerAccount list;
# tuning this trades API round-trip count vs payload size + SP query
# time per call. ~50 customers/call has been a comfortable middle.
_BACKFILL_BATCH_SIZE = 50

_refresh_thread: threading.Thread | None = None
_last_refresh: str | None = None
_last_refresh_requested: str | None = None
_refresh_state: dict[str, dict[str, Any]] = {}

# Tiny per-process cache of the built dashboard rows. Every customer
# detail page + every per-page permission check used to rebuild this
# from 85k+ mirror rows in Python; that made every navigation feel
# like the app was hung. The cache is invalidated on every refresh and
# auto-expires after a short TTL so it never goes stale.
# Was 30 s when build was a 85k-row GROUP BY + Python aggregation;
# now that the build is a flat SELECT * over the precomputed
# mirror_dashboard_cache (~2.5k rows, single-digit ms), keep a longer
# TTL so concurrent dashboard hits across the worker pool don't even
# touch SQLite. Cache is explicitly invalidated by refresh_cache /
# upsert hooks, so 5 minutes is safe.
_DASHBOARD_BUILD_TTL_S = 300.0
_dashboard_build_lock = threading.Lock()
_dashboard_build_cache: tuple[float, list[dict[str, Any]]] | None = None


def _invalidate_dashboard_build_cache() -> None:
    global _dashboard_build_cache
    with _dashboard_build_lock:
        _dashboard_build_cache = None


def _load_persisted_timestamps() -> None:
    global _last_refresh, _last_refresh_requested
    try:
        _last_refresh_requested = get_app_setting(_LAST_REQUESTED_KEY)
        _last_refresh = get_app_setting(_LAST_COMPLETED_KEY)
    except Exception:
        _last_refresh_requested = None
        _last_refresh = None


_load_persisted_timestamps()


def salesline_window_days() -> int:
    return mirror.SALESLINE_WINDOW_DAYS


def _date_only(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    return s[:10] if len(s) >= 10 else s


def _parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _num(value: Any) -> float:
    if value in (None, "", "NULL"):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_customer_account(value: Any) -> str:
    """Canonical customer ID used when joining customer master to sales lines."""
    if value in (None, "", "NULL"):
        return ""
    return str(value).strip().upper()


def _scope_key(salesman_key: str | None) -> str:
    return normalize_key(salesman_key) or _SCOPE_ALL


def _set_step(scope: str, message: str) -> None:
    _refresh_state.setdefault(scope, {"running": True, "step": ""})["step"] = message


def _source_label(meta: dict[str, Any] | None) -> str:
    source = (meta or {}).get("source") or "unknown"
    labels = {
        "api": "reporting API",
        "fresh_cache": "in-process API cache",
        "stale_cache": "stale API cache",
        "mirror_after_failure": "SQLite mirror after API failure",
        "mirror_no_api": "SQLite mirror; API not configured",
        "failed": "unavailable",
    }
    return labels.get(str(source), str(source).replace("_", " "))


def _salesline_stats_message(stats: dict[str, Any] | None) -> str:
    if not stats:
        return ""
    # Chunked-helper shape (new): {rows_in, chunks_done, chunks_total,
    # errors, ...}. Old upsert_salesline shape (still in persisted
    # rows): {rows_in, inserted, updated, unchanged, skipped_*}. Render
    # whichever fields are present so older snapshots survive a deploy.
    rows_in = int(stats.get("rows_in") or 0)
    if "chunks_total" in stats:
        chunks_done = int(stats.get("chunks_done") or 0)
        chunks_total = int(stats.get("chunks_total") or 0)
        errors = len(stats.get("errors") or [])
        return (
            "Salesline mirror: "
            f"{rows_in:,} API rows across {chunks_done}/{chunks_total} "
            f"monthly chunks ({errors} chunk error{'s' if errors != 1 else ''})"
        )
    skipped = (
        int(stats.get("skipped_missing_order") or 0)
        + int(stats.get("skipped_missing_date") or 0)
        + int(stats.get("skipped_outside_window") or 0)
    )
    return (
        "Salesline mirror: "
        f"{rows_in:,} API rows, "
        f"{int(stats.get('inserted') or 0):,} inserted, "
        f"{int(stats.get('updated') or 0):,} updated, "
        f"{int(stats.get('unchanged') or 0):,} unchanged, "
        f"{skipped:,} skipped"
    )


def _last_salesline_stats_message() -> str:
    raw = get_app_setting(_LAST_ORDER_MIRROR_STATS_KEY)
    if not raw:
        return ""
    try:
        return _salesline_stats_message(json.loads(raw))
    except Exception:
        return ""


def _backfill_stats_message(stats: dict[str, int] | None) -> str:
    if not stats:
        return ""
    customers = int(stats.get("customers_to_backfill") or 0)
    if not customers:
        return ""
    return (
        f"Last-order backfill: pinned {int(stats.get('rows_pinned') or 0):,} "
        f"orders for {customers:,} long-tail customers "
        f"({int(stats.get('api_calls') or 0)} API calls, "
        f"{int(stats.get('rows_fetched') or 0):,} rows fetched, "
        f"{int(stats.get('errors') or 0)} errors)"
    )


def _last_backfill_stats_message() -> str:
    raw = get_app_setting(_LAST_BACKFILL_STATS_KEY)
    if not raw:
        return ""
    try:
        return _backfill_stats_message(json.loads(raw))
    except Exception:
        return ""


def _fetch_customers(salesman_key: str | None) -> tuple[list[dict], str]:
    params: dict[str, Any] = {}
    if salesman_key:
        params["salesman"] = salesman_key
    try:
        rows = reporting_api.run("customer_master", params)
    except Exception as exc:
        # The order rows contain enough customer fields to seed the dashboard.
        # Do not let customer-master downtime block the first dashboard load.
        log.warning("Dashboard customer-master fetch failed; deriving customers from orders: %s", exc)
        return [], "customer_master unavailable"
    return list(rows or []), _source_label(reporting_api.last_run_source())


def _orderless_customer_accounts(salesman_key: str | None) -> list[str]:
    """Customers in master that have no row in the salesline mirror at
    all (i.e. their last order is older than the rolling window). These
    are the customers the backfill loop pulls full history for so the
    dashboard can still show them a last-order date.

    Reads against ``mirror_sales_header`` instead of the underlying
    ``mirror_salesline`` table -- the header has one row per order
    rather than per line, so the existence check skips 80k+ rows of
    line detail entirely.
    """
    mirror.init_mirror_db()
    where_extra = ""
    params: list[Any] = []
    if salesman_key:
        where_extra = " AND sales_group = ?"
        params.append(salesman_key)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT customer_account
            FROM mirror_customers
            WHERE customer_account IS NOT NULL
              AND customer_account <> ''
              {where_extra}
              AND customer_account NOT IN (
                  SELECT DISTINCT customer_account
                  FROM mirror_sales_header
                  WHERE customer_account IS NOT NULL
                    AND customer_account <> ''
              )
            ORDER BY customer_account
            """,
            params,
        ).fetchall()
    return [r["customer_account"] for r in rows if r["customer_account"]]


def _backfill_last_orders(
    salesman_key: str | None,
    scope: str,
) -> dict[str, int]:
    """For every customer in master with no orders in the rolling
    mirror window, fetch their entire order history since D365
    go-live and pin **all** of it in the mirror so the rolling-window
    pruner can't drop it.

    We used to only pin the *latest* line per customer here, but that
    made every multi-order long-tail customer look like a single-order
    "new" customer to the dashboard classifier. Pinning the full
    history is the right shape: the API call costs the same either way,
    and the extra rows are negligible (long-tail customers are
    long-tail precisely because they don't order much).
    """
    accounts = _orderless_customer_accounts(salesman_key)
    stats = {
        "customers_to_backfill": len(accounts),
        "api_calls":             0,
        "rows_pinned":           0,
        "rows_fetched":          0,
        "errors":                0,
    }
    if not accounts:
        return stats

    today = get_today_eastern()
    # period=all_time translates to (None, None) for the SP, which makes
    # it fall back to its own short default window and return nothing
    # for dormant customers. Send an explicit custom range from D365
    # go-live to today instead -- that's the full valid history window.
    backfill_start = D365_GO_LIVE.isoformat()
    backfill_end = today.isoformat()

    pinned_rows: list[dict] = []
    for i in range(0, len(accounts), _BACKFILL_BATCH_SIZE):
        batch = accounts[i : i + _BACKFILL_BATCH_SIZE]
        _set_step(
            scope,
            f"Filling in last-order history "
            f"({min(i + _BACKFILL_BATCH_SIZE, len(accounts))}/{len(accounts)} customers)...",
        )
        params: dict[str, Any] = {
            "period": "custom",
            "start_date": backfill_start,
            "end_date": backfill_end,
            "customers": ",".join(batch),
        }
        if _DEFAULT_COMPANY:
            params["company"] = _DEFAULT_COMPANY
        try:
            rows = reporting_api.run("ordered", params, no_piggyback=True)
        except Exception as exc:
            log.warning("Backfill batch failed (%d customers): %s", len(batch), exc)
            stats["errors"] += 1
            continue
        stats["api_calls"] += 1
        stats["rows_fetched"] += len(rows or [])
        if not rows:
            continue
        # Pin every row we got back, not just the latest per customer.
        # Multi-order long-tail customers need their full history in
        # the mirror so the dashboard classifier can tell "1 order"
        # ("new") from "many orders, none recent" ("inactive").
        pinned_rows.extend(rows)

    if pinned_rows:
        upsert_stats = mirror.upsert_salesline(
            pinned_rows,
            trigger="backfill",
            keep_forever=True,
        )
        stats["rows_pinned"] = int(upsert_stats.get("inserted", 0)) + int(upsert_stats.get("updated", 0))
    return stats


def _fetch_order_history(salesman_key: str | None) -> tuple[list[dict], str]:
    # Dashboard is intentionally backed by the rolling salesline mirror.
    # Refresh only that window so the endpoint/mirror contract stays bounded.
    today = get_today_eastern()
    start = today - timedelta(days=mirror.SALESLINE_WINDOW_DAYS)
    params: dict[str, Any] = {
        "period": "custom",
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
    }
    if _DEFAULT_COMPANY:
        params["company"] = _DEFAULT_COMPANY
    if salesman_key:
        params["salesman"] = salesman_key
    rows = reporting_api.run("ordered", params)
    source = _source_label(reporting_api.last_run_source())
    return list(rows or []), source


def refresh_cache(salesman_key: str | None = None) -> None:
    """Refresh the shared endpoint mirrors used by the dashboard."""
    global _last_refresh
    scope = _scope_key(salesman_key)
    scope_label = f"salesman={salesman_key}" if salesman_key else "all"
    _refresh_state[scope] = {"running": True, "step": "Refreshing shared endpoint mirrors..."}
    log.info("Dashboard refresh starting (%s)", scope_label)

    try:
        _set_step(scope, "Refreshing customer master mirror...")
        customer_rows, customer_source = _fetch_customers(salesman_key)
        if customer_rows:
            mirror.upsert_customers(customer_rows, trigger="dashboard")
        _refresh_state.setdefault(scope, {})["customer_source"] = customer_source
        _set_step(scope, f"Received {len(customer_rows):,} customers")

        from test.webapp.services import mirror_refresh

        days_back = mirror.SALESLINE_REFRESH_WINDOW_DAYS
        _set_step(
            scope,
            f"Refreshing salesline mirror (last {days_back} days, "
            "chunked monthly)...",
        )
        # The chunked helper handles fetch + piggyback upsert internally;
        # no separate upsert_salesline call. Older history (pre-window)
        # is loaded via the admin "Backfill since D365 go-live" job and
        # then kept forever by the mirror.
        stats = mirror_refresh.refresh_window_chunked(
            scope="salesline",
            days_back=days_back,
            trigger="dashboard",
            triggered_by=f"dashboard:{scope_label}",
        )
        order_source = _source_label(reporting_api.last_run_source())
        _set_step(scope, _salesline_stats_message(stats))
        _refresh_state.setdefault(scope, {})["order_mirror_stats"] = stats
        _refresh_state.setdefault(scope, {})["order_source"] = order_source
        # We no longer call _backfill_last_orders here -- the mirror
        # retains every salesline row since D365 go-live (loaded via
        # the admin backfill button) so the long-tail per-customer
        # pinning that used to live in this step is redundant. Leave
        # the helper in the module for now; just don't call it.
        backfill_stats = {"customers_to_backfill": 0, "api_calls": 0,
                          "rows_pinned": 0, "rows_fetched": 0,
                          "errors": 0, "skipped": "no-window-mirror"}
        _refresh_state.setdefault(scope, {})["backfill_stats"] = backfill_stats

        now = datetime.now().isoformat(timespec="seconds")
        _last_refresh = now
        set_app_setting(_LAST_COMPLETED_KEY, now)
        set_app_setting(_LAST_CUSTOMER_SOURCE_KEY, customer_source)
        set_app_setting(_LAST_ORDER_SOURCE_KEY, order_source)
        set_app_setting(_LAST_ORDER_MIRROR_STATS_KEY, json.dumps(stats))
        set_app_setting(_LAST_BACKFILL_STATS_KEY, json.dumps(backfill_stats))
        set_app_setting(_LAST_ERROR_KEY, "")
        _invalidate_dashboard_build_cache()
        _invalidate_cache_counts()
        order_lines_in = int(stats.get("rows_in") or 0)
        _set_step(scope, f"Done - mirrors refreshed ({len(customer_rows):,} customers, {order_lines_in:,} order lines)")
        log.info("Dashboard mirror refresh complete (%s): %d customers, %d order lines",
                 scope_label, len(customer_rows), order_lines_in)
    except Exception as exc:
        message = str(exc) or "Refresh failed"
        log.exception("Dashboard refresh failed (%s)", scope_label)
        set_app_setting(_LAST_ERROR_KEY, message)
        _set_step(scope, f"Refresh failed - {message}")
        raise
    finally:
        _refresh_state.setdefault(scope, {})["running"] = False


def get_last_refresh() -> str | None:
    global _last_refresh
    if _last_refresh:
        return _last_refresh
    _last_refresh = get_app_setting(_LAST_COMPLETED_KEY)
    if _last_refresh:
        return _last_refresh
    try:
        fresh = mirror.mirror_freshness()
        latest = (fresh.get("salesline") or {}).get("last_seen_utc") or (fresh.get("customers") or {}).get("last_seen_utc")
        if latest:
            _last_refresh = str(latest)
    except Exception:
        return None
    return _last_refresh


def mark_refresh_requested() -> str:
    global _last_refresh_requested
    _last_refresh_requested = datetime.now().isoformat(timespec="seconds")
    set_app_setting(_LAST_REQUESTED_KEY, _last_refresh_requested)
    return _last_refresh_requested


def get_refresh_status(salesman_key: str | None = None) -> dict[str, Any]:
    scope = _scope_key(salesman_key)
    state = _refresh_state.get(scope, {})
    counts = get_cache_counts()

    # Batch every app_settings read used below into one connection
    # instead of opening 5-7 separate ones. On OneDrive each connect()
    # adds enough latency that this is visible in page-load time.
    settings = get_app_settings_batch([
        _LAST_REQUESTED_KEY,
        _LAST_COMPLETED_KEY,
        _LAST_CUSTOMER_SOURCE_KEY,
        _LAST_ORDER_SOURCE_KEY,
        _LAST_ORDER_MIRROR_STATS_KEY,
        _LAST_BACKFILL_STATS_KEY,
        _LAST_ERROR_KEY,
    ])

    last_completed = _last_refresh or settings.get(_LAST_COMPLETED_KEY)
    if not last_completed:
        # Final fallback to the mirror's own freshness timestamps.
        # get_last_refresh() handles that path and module-caches the
        # result, so future calls skip it.
        last_completed = get_last_refresh()

    def _stats_or_persisted(state_key: str, persisted_key: str, renderer):
        live = renderer(state.get(state_key))
        if live:
            return live
        raw = settings.get(persisted_key)
        if not raw:
            return ""
        try:
            return renderer(json.loads(raw))
        except Exception:
            return ""

    return {
        "running": bool(state.get("running", False)),
        "step": state.get("step", ""),
        "last_requested": _last_refresh_requested or settings.get(_LAST_REQUESTED_KEY),
        "last_completed": last_completed,
        "cache_customers": counts["customers"],
        "cache_order_lines": counts["order_lines"],
        "dated_order_lines": counts["dated_order_lines"],
        "customers_with_last_order": counts["customers_with_last_order"],
        "order_customers": counts["order_customers"],
        "customer_source": state.get("customer_source") or settings.get(_LAST_CUSTOMER_SOURCE_KEY),
        "order_source": state.get("order_source") or settings.get(_LAST_ORDER_SOURCE_KEY),
        "order_mirror_stats": _stats_or_persisted("order_mirror_stats", _LAST_ORDER_MIRROR_STATS_KEY, _salesline_stats_message),
        "backfill_stats": _stats_or_persisted("backfill_stats", _LAST_BACKFILL_STATS_KEY, _backfill_stats_message),
        "last_error": settings.get(_LAST_ERROR_KEY),
        "salesline_window_days": mirror.SALESLINE_WINDOW_DAYS,
    }


# Cache for get_cache_counts(): cheap enough now that we read most
# numbers from the precomputed mirror_dashboard_cache, but the
# salesline count queries still benefit from a short TTL so the three
# helpers that call this per dashboard render only run the SQL once.
_CACHE_COUNTS_TTL_S = 60.0
_cache_counts_lock = threading.Lock()
_cache_counts_value: tuple[float, dict[str, int]] | None = None


def _invalidate_cache_counts() -> None:
    global _cache_counts_value
    with _cache_counts_lock:
        _cache_counts_value = None


def get_cache_counts() -> dict[str, int]:
    global _cache_counts_value
    now = time.monotonic()
    with _cache_counts_lock:
        cached = _cache_counts_value
    if cached is not None and (now - cached[0]) < _CACHE_COUNTS_TTL_S:
        return dict(cached[1])

    mirror.init_mirror_db()
    with connect() as conn:
        customers = conn.execute(
            "SELECT COUNT(*) FROM mirror_customers"
        ).fetchone()[0]
        # COUNT(*) on mirror_salesline goes through the rowid index,
        # which is fine on 85-200k rows. The old COUNT(DISTINCT
        # customer_account ... WHERE order_date <> '') used to be the
        # slowest query on the dashboard render -- replaced by the
        # ``order_customers`` count on mirror_dashboard_cache which is
        # ~2.5k rows and indexed.
        order_lines = conn.execute(
            "SELECT COUNT(*) FROM mirror_salesline"
        ).fetchone()[0]
        dated_order_lines = conn.execute(
            "SELECT COUNT(*) FROM mirror_salesline WHERE order_date <> ''"
        ).fetchone()[0]
        order_customers = conn.execute(
            "SELECT COUNT(*) FROM mirror_dashboard_cache "
            "WHERE last_order_date IS NOT NULL AND last_order_date <> ''"
        ).fetchone()[0]
    counts = {
        "customers": int(customers or 0),
        "order_lines": int(order_lines or 0),
        "dated_order_lines": int(dated_order_lines or 0),
        "order_customers": int(order_customers or 0),
        "customers_with_last_order": int(order_customers or 0),
    }
    with _cache_counts_lock:
        _cache_counts_value = (now, counts)
    return dict(counts)


def get_cache_quality_warning() -> str:
    # Cheap path: only check the two columns that matter for the
    # warning. Avoids the expensive COUNT(DISTINCT) query when all we
    # need is "is the mirror empty?".
    mirror.init_mirror_db()
    with connect() as conn:
        has_customer = conn.execute(
            "SELECT 1 FROM mirror_customers LIMIT 1"
        ).fetchone() is not None
        has_orders = conn.execute(
            "SELECT 1 FROM mirror_salesline LIMIT 1"
        ).fetchone() is not None
    if has_customer or has_orders:
        return ""
    return (
        "No mirrored endpoint data is available yet. Run an ordered report or refresh "
        "the dashboard to populate the shared customer and salesline mirrors."
    )


def cache_needs_order_refresh() -> bool:
    """True when the shared endpoint mirrors are empty.

    Cheap check: only looks for *any* row in each of the three
    relevant places. Doesn't need the cache_counts numbers, so this
    bypasses the COUNT(DISTINCT) work entirely.
    """
    mirror.init_mirror_db()
    with connect() as conn:
        has_customer = conn.execute(
            "SELECT 1 FROM mirror_customers LIMIT 1"
        ).fetchone() is not None
        if not has_customer:
            return True
        has_order = conn.execute(
            "SELECT 1 FROM mirror_salesline LIMIT 1"
        ).fetchone() is not None
        if not has_order:
            return True
        has_dated = conn.execute(
            "SELECT 1 FROM mirror_salesline WHERE order_date <> '' LIMIT 1"
        ).fetchone() is not None
    return not has_dated


def request_background_refresh(salesman_key: str | None = None) -> dict[str, Any]:
    """Start a one-shot dashboard refresh unless that scope is already running."""
    scope = _scope_key(salesman_key)
    before = get_last_refresh() or ""
    requested_at = mark_refresh_requested()
    if _refresh_state.get(scope, {}).get("running"):
        return {
            "started": False,
            "already_running": True,
            "before": before,
            "requested_at": requested_at,
        }

    def _run_refresh() -> None:
        try:
            refresh_cache(salesman_key=salesman_key)
        except Exception:
            log.exception("Dashboard background refresh failed")

    threading.Thread(target=_run_refresh, name="v2-dashboard-one-shot-refresh", daemon=True).start()
    return {
        "started": True,
        "already_running": False,
        "before": before,
        "requested_at": requested_at,
    }


def get_dashboard_data(
    *,
    salesman_key: str | None = None,
    allowed_salesman_keys: list[str] | None = None,
    exclude_accounts: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build dashboard rows from the shared endpoint mirrors."""
    rows = _build_dashboard_rows_from_mirror()
    salesman_norm = normalize_key(salesman_key)
    allowed_norm = {normalize_key(k) for k in (allowed_salesman_keys or []) if normalize_key(k)}
    excluded = set(exclude_accounts or [])

    out: list[dict[str, Any]] = []
    for item in rows:
        group_norm = normalize_key(item.get("sales_group"))
        if salesman_norm and group_norm != salesman_norm:
            continue
        if allowed_norm and group_norm not in allowed_norm:
            continue
        item["excluded"] = item["customer_account"] in excluded
        out.append(item)
    return sorted(out, key=lambda r: (r.get("customer_name") or r.get("customer_account") or "").lower())


def _row_text(row: Any, key: str) -> str:
    value = row[key] if key in row.keys() else ""
    if value in (None, "NULL"):
        return ""
    return str(value).strip()


def _row_num(row: Any, key: str) -> float:
    value = row[key] if key in row.keys() else 0
    return _num(value)


def _mirror_line_from_row(row: Any) -> dict[str, Any]:
    qty_ordered = _row_num(row, "qty_ordered")
    unit_price = _row_num(row, "unit_price")
    ordered_dollars = _row_num(row, "ordered_dollars")
    if not ordered_dollars and qty_ordered and unit_price:
        ordered_dollars = round(qty_ordered * unit_price, 2)
    return {
        "order_number": _row_text(row, "sales_order_number"),
        "line_number": int(_row_num(row, "line_number")),
        "customer_account": _normalize_customer_account(_row_text(row, "customer_account")),
        "customer_name": _row_text(row, "customer_name"),
        "sales_group": _row_text(row, "sales_group"),
        "order_date": _date_only(_row_text(row, "order_date")),
        "customer_req": _row_text(row, "po_number"),
        "item_number": _row_text(row, "item_number"),
        "item_name": _row_text(row, "item_name"),
        "unit_price": unit_price,
        "order_status": _row_text(row, "order_status"),
        "line_status": _row_text(row, "status"),
        "qty_ordered": qty_ordered,
        "qty_shipped": _row_num(row, "qty_shipped"),
        "qty_cancelled": _row_num(row, "qty_cancelled"),
        "ordered_dollars": ordered_dollars,
        "shipped_dollars": _row_num(row, "shipped_dollars"),
        "cancelled_dollars": _row_num(row, "cancelled_dollars"),
    }


def _read_mirror_lines(
    *,
    customer_account: str | None = None,
    order_number: str | None = None,
) -> list[dict[str, Any]]:
    mirror.init_mirror_db()
    where: list[str] = []
    params: list[Any] = []
    if customer_account:
        where.append("customer_account = ?")
        params.append(_normalize_customer_account(customer_account))
    if order_number:
        where.append("sales_order_number = ?")
        params.append(str(order_number).strip())

    sql = """
        SELECT
            sales_order_number, line_number, customer_account, customer_name,
            sales_group, order_date, po_number, item_number, item_name,
            unit_price, order_status, status, qty_ordered, qty_shipped,
            qty_cancelled, ordered_dollars, shipped_dollars, cancelled_dollars
        FROM mirror_salesline
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY order_date DESC, sales_order_number DESC, line_number"

    with connect() as conn:
        return [_mirror_line_from_row(row) for row in conn.execute(sql, params)]


def _single_value(values: list[str]) -> str:
    unique = sorted({v for v in values if v})
    if not unique:
        return ""
    return unique[0] if len(unique) == 1 else "Mixed"


def _group_mirror_orders(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for line in lines:
        order_number = line.get("order_number") or ""
        if not order_number:
            continue
        grouped.setdefault(order_number, []).append(line)

    orders: list[dict[str, Any]] = []
    for order_number, order_lines in grouped.items():
        dated = sorted(
            d for d in (_date_only(line.get("order_date")) for line in order_lines)
            if d
        )
        first = order_lines[0]
        orders.append({
            "order_number": order_number,
            "order_date": dated[-1] if dated else "",
            "customer_account": first.get("customer_account") or "",
            "customer_name": first.get("customer_name") or "",
            "salesman": first.get("sales_group") or "",
            "customer_req": first.get("customer_req") or "",
            "order_name": "",
            "status": _single_value([line.get("order_status") or "" for line in order_lines]),
            "processing_status": _single_value([line.get("line_status") or "" for line in order_lines]),
            "order_total": round(sum(_num(line.get("ordered_dollars")) for line in order_lines), 2),
            "lines": order_lines,
        })
    orders.sort(key=lambda o: (o["order_date"] or "0000-00-00", o["order_number"]), reverse=True)
    return orders


def _build_dashboard_rows_uncached() -> list[dict[str, Any]]:
    """Read pre-computed dashboard rows from ``mirror_dashboard_cache``.

    Everything that used to happen here at render time (loading every
    sales-header row, grouping in Python, computing gaps/stdev per
    customer) now happens once at refresh time inside
    ``mirror._rebuild_dashboard_cache``. The render path is a flat
    SELECT over ~2.5k customer rows -- a few ms.

    Emits a timing log every call so we can see if the read itself
    ever regresses (e.g. table grows unexpectedly).
    """
    mirror.init_mirror_db()
    t0 = time.monotonic()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT customer_account, customer_name, sales_group,
                   last_order_date, order_count, avg_gap_days, gap_stdev,
                   overdue_threshold, days_since_last, status,
                   last_refreshed
            FROM mirror_dashboard_cache
            """
        ).fetchall()
    t1 = time.monotonic()
    window_days = mirror.SALESLINE_WINDOW_DAYS
    metrics: list[dict[str, Any]] = []
    for row in rows:
        metrics.append({
            "customer_account":   row["customer_account"],
            "customer_name":      row["customer_name"] or row["customer_account"],
            "sales_group":        row["sales_group"] or "",
            "last_order_date":    row["last_order_date"],
            "order_count":        int(row["order_count"] or 0),
            "avg_gap_days":       row["avg_gap_days"],
            "gap_stdev":          row["gap_stdev"],
            "overdue_threshold":  row["overdue_threshold"],
            "days_since_last":    row["days_since_last"],
            "status":             row["status"] or "inactive",
            "last_refreshed":     row["last_refreshed"] or "",
            "mirror_window_days": window_days,
        })
    log.info(
        "dashboard.build_rows: read=%.3fs python=%.3fs total=%.3fs (%d rows)",
        t1 - t0, time.monotonic() - t1, time.monotonic() - t0, len(metrics),
    )
    return metrics


def _build_dashboard_rows_from_mirror() -> list[dict[str, Any]]:
    """Cached wrapper around _build_dashboard_rows_uncached.

    Returns a *copy* per call so callers can mutate items (e.g. setting
    ``excluded``) without corrupting the cache.
    """
    global _dashboard_build_cache
    now = time.monotonic()
    with _dashboard_build_lock:
        cached = _dashboard_build_cache
    if cached is not None and (now - cached[0]) < _DASHBOARD_BUILD_TTL_S:
        return [dict(row) for row in cached[1]]
    fresh = _build_dashboard_rows_uncached()
    with _dashboard_build_lock:
        _dashboard_build_cache = (now, fresh)
    return [dict(row) for row in fresh]


def get_dashboard_summary(data: list[dict[str, Any]]) -> dict[str, Any]:
    included = [d for d in data if not d.get("excluded")]
    avg_gaps = [
        float(d["avg_gap_days"])
        for d in included
        if d.get("avg_gap_days") not in (None, "") and float(d.get("avg_gap_days") or 0) > 0
    ]
    return {
        "total_customers": len(included),
        "new": sum(1 for d in included if d.get("status") == "new"),
        "active": sum(1 for d in included if d.get("status") == "active"),
        "overdue": sum(1 for d in included if d.get("status") == "overdue"),
        "inactive": sum(1 for d in included if d.get("status") == "inactive"),
        "avg_frequency_days": round(sum(avg_gaps) / len(avg_gaps), 1) if avg_gaps else 0,
    }


def get_customer_cached(account: str) -> dict[str, Any] | None:
    """Return dashboard metrics for one customer in O(1).

    Reads the precomputed ``mirror_dashboard_cache`` row by primary
    key. Used by the customer detail page header and by
    :func:`user_can_access_customer` to check the customer's sales
    group, so it has to stay snappy.
    """
    account = _normalize_customer_account(account)
    if not account:
        return None
    mirror.init_mirror_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT customer_account, customer_name, sales_group,
                   last_order_date, order_count, avg_gap_days, gap_stdev,
                   overdue_threshold, days_since_last, status,
                   last_refreshed
            FROM mirror_dashboard_cache
            WHERE customer_account = ?
            """,
            (account,),
        ).fetchone()
    if row is None:
        return None
    return {
        "customer_account":   row["customer_account"],
        "customer_name":      row["customer_name"] or row["customer_account"],
        "sales_group":        row["sales_group"] or "",
        "last_order_date":    row["last_order_date"],
        "order_count":        int(row["order_count"] or 0),
        "avg_gap_days":       row["avg_gap_days"],
        "gap_stdev":          row["gap_stdev"],
        "overdue_threshold":  row["overdue_threshold"],
        "days_since_last":    row["days_since_last"],
        "status":             row["status"] or "inactive",
        "last_refreshed":     row["last_refreshed"] or "",
        "mirror_window_days": mirror.SALESLINE_WINDOW_DAYS,
    }


def get_user_dashboard_scope(email: str) -> dict[str, Any]:
    profile = get_user_profile(email)
    role = profile["role"]
    if role == "salesman":
        return {"role": role, "salesman_key": profile.get("salesman_key"), "allowed_salesman_keys": None}
    if role == "manager":
        return {"role": role, "salesman_key": None, "allowed_salesman_keys": get_user_salesman_access(email)}
    return {"role": role, "salesman_key": None, "allowed_salesman_keys": None}


def user_can_access_customer(email: str, account: str) -> bool:
    scope = get_user_dashboard_scope(email)
    if scope["role"] in {"admin", "developer"}:
        return True
    cached = get_customer_cached(account)
    if not cached:
        return False
    group_norm = normalize_key(cached.get("sales_group"))
    if scope["role"] == "manager":
        allowed = {normalize_key(k) for k in (scope.get("allowed_salesman_keys") or [])}
        return group_norm in allowed
    if scope["role"] == "salesman":
        return group_norm == normalize_key(scope.get("salesman_key"))
    return False


def _cached_lines_for_customer(account: str) -> list[dict[str, Any]]:
    return _read_mirror_lines(customer_account=account)


def _cached_lines_for_order(order_number: str) -> list[dict[str, Any]]:
    return _read_mirror_lines(order_number=order_number)


def fetch_customer_info(account: str) -> dict[str, Any]:
    cached = get_customer_cached(account)
    if cached:
        return {
            "account": cached["customer_account"],
            "name": cached["customer_name"] or cached["customer_account"],
            "sales_group": cached["sales_group"] or "",
            "status": cached["status"],
            "days_since_last": cached["days_since_last"],
            "avg_gap_days": cached["avg_gap_days"],
            "overdue_threshold": cached["overdue_threshold"],
        }
    return {"account": account, "name": account, "sales_group": "", "status": ""}


def fetch_customer_orders(account: str, *, days: int | None = 7, last_n: int | None = None) -> list[dict[str, Any]]:
    lines = _cached_lines_for_customer(account)
    if not last_n and days and days < 9999:
        today = get_today_eastern()
        start = max(D365_GO_LIVE, today - timedelta(days=days))
        lines = [
            line for line in lines
            if (parsed := _parse_date(_date_only(line.get("order_date")))) is not None
            and start <= parsed <= today
        ]
    headers = _group_mirror_orders(lines)
    if last_n:
        return headers[:last_n]
    return headers


def fetch_order_detail(order_number: str) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    lines = _cached_lines_for_order(order_number)
    if not lines:
        return {"order_number": order_number}, [], ""

    first = lines[0]
    customer_account = first.get("customer_account") or ""
    grouped = _group_mirror_orders(lines)
    header = grouped[0] if grouped else {
        "order_number": order_number,
        "order_date": _date_only(first.get("order_date")),
        "status": first.get("order_status") or "",
        "processing_status": first.get("line_status") or "",
        "customer_req": first.get("customer_req") or "",
        "order_name": "",
        "customer_name": first.get("customer_name") or "",
        "salesman": first.get("sales_group") or "",
    }

    detail_lines: list[dict[str, Any]] = []
    for line in sorted(lines, key=lambda ln: _num(ln.get("line_number"))):
        detail_lines.append({
            "order_number": line.get("order_number") or order_number,
            "line_number": int(_num(line.get("line_number"))),
            "item": line.get("item_number") or "",
            "description": line.get("item_name") or "",
            "qty_ordered": _num(line.get("qty_ordered")),
            "qty_shipped": _num(line.get("qty_shipped")),
            "qty_cancelled": _num(line.get("qty_cancelled")),
            "sales_price": _num(line.get("unit_price")),
            "total_ordered": _num(line.get("ordered_dollars")),
            "total_shipped": _num(line.get("shipped_dollars")),
            "total": _num(line.get("shipped_dollars")),
            "status": line.get("line_status") or "",
            "order_status": line.get("order_status") or "",
        })
    return header, detail_lines, customer_account


def user_can_access_order(email: str, customer_account: str) -> bool:
    if not customer_account:
        return False
    return user_can_access_customer(email, customer_account)


def start_background_refresh() -> None:
    """Kick a one-shot refresh on boot iff the mirror is empty.

    Ongoing refreshes are owned by :mod:`mirror_scheduler` (APScheduler
    daily job at 00:00 ET + ``catchup_if_stale`` on boot). User-clicked
    refreshes go through :func:`request_background_refresh`. We used to
    run a 4-hour periodic loop here in addition to all of that, but it
    fired on every gunicorn worker, duplicated the scheduler's work,
    and was the trigger for the 2026-05-18 OOM cascade on B1 (chunked
    salesline pull + the live app's OData paginator collided in the
    same 1.75 GB container).
    """
    global _refresh_thread
    if _refresh_thread and _refresh_thread.is_alive():
        return

    counts = get_cache_counts()
    if counts["customers"] > 0 and counts["order_lines"] > 0:
        return

    def _cold_start() -> None:
        try:
            mark_refresh_requested()
            refresh_cache()
        except Exception:
            log.exception("Initial dashboard background refresh failed")

    _refresh_thread = threading.Thread(target=_cold_start, name="v2-dashboard-cold-start", daemon=True)
    _refresh_thread.start()
