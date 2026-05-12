"""Endpoint-backed dashboard data for the v2 app.

The live app reads D365 OData directly. The test app rebuild uses the
reporting API instead: customer_master supplies the customer universe and
ordered/salesline_release supplies order history and detail rows.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any

from core.dates import D365_GO_LIVE, get_today_eastern
from test.webapp.db import (
    connect,
    get_app_setting,
    get_user_salesman_access,
    normalize_key,
    set_app_setting,
)
from test.webapp.services import mirror, reporting_api
from test.webapp.services.report_access import get_user_profile

log = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 4 * 3600
_DEFAULT_COMPANY = (os.environ.get("REPORTING_API_DEFAULT_COMPANY") or "ACHM").strip()
_SCOPE_ALL = "__all__"
_LAST_REQUESTED_KEY = "dashboard.last_refresh_requested"
_LAST_COMPLETED_KEY = "dashboard.last_refresh_completed"
_LAST_CUSTOMER_SOURCE_KEY = "dashboard.last_customer_source"
_LAST_ORDER_SOURCE_KEY = "dashboard.last_order_source"
_LAST_ORDER_MIRROR_STATS_KEY = "dashboard.last_order_mirror_stats"
_LAST_ERROR_KEY = "dashboard.last_refresh_error"

_refresh_thread: threading.Thread | None = None
_last_refresh: str | None = None
_last_refresh_requested: str | None = None
_refresh_state: dict[str, dict[str, Any]] = {}


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


def _compute_customer_metrics(
    customer_account: str,
    customer_name: str,
    sales_group: str,
    order_dates: list[str],
) -> dict[str, Any]:
    """Compute live-style frequency and status metrics for one customer."""
    today = get_today_eastern()
    result: dict[str, Any] = {
        "customer_account": customer_account,
        "customer_name": customer_name,
        "sales_group": sales_group,
        "order_dates": sorted(order_dates),
        "last_order_date": None,
        "avg_gap_days": None,
        "gap_stdev": None,
        "overdue_threshold": None,
        "days_since_last": None,
        "status": "new",
    }

    parsed = sorted(d for d in (_parse_date(x) for x in order_dates) if d is not None)
    if not parsed:
        return result

    last = parsed[-1]
    result["last_order_date"] = last.isoformat()
    days_since = (today - last).days
    result["days_since_last"] = days_since

    # Baseline: a customer with any order is never "new". "New" is
    # reserved for customers in mirror_customers that have no orders
    # in the mirror window at all.
    result["status"] = "inactive" if days_since > 365 else "active"

    if len(parsed) < 2:
        return result

    gaps = [(parsed[i + 1] - parsed[i]).days for i in range(len(parsed) - 1)]
    gaps = [g for g in gaps if g > 0]
    if not gaps:
        return result

    mean_gap = sum(gaps) / len(gaps)
    variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
    stdev = math.sqrt(variance)
    threshold = mean_gap + stdev

    result["avg_gap_days"] = round(mean_gap, 1)
    result["gap_stdev"] = round(stdev, 1)
    result["overdue_threshold"] = round(threshold, 1)

    if days_since > 365:
        result["status"] = "inactive"
    elif days_since > threshold:
        result["status"] = "overdue"
    else:
        result["status"] = "active"
    return result


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


def _salesline_stats_message(stats: dict[str, int] | None) -> str:
    if not stats:
        return ""
    skipped = (
        int(stats.get("skipped_missing_order") or 0)
        + int(stats.get("skipped_missing_date") or 0)
        + int(stats.get("skipped_outside_window") or 0)
    )
    return (
        "Salesline mirror: "
        f"{int(stats.get('rows_in') or 0):,} API rows, "
        f"{int(stats.get('inserted') or 0):,} inserted, "
        f"{int(stats.get('updated') or 0):,} updated, "
        f"{int(stats.get('unchanged') or 0):,} unchanged, "
        f"{skipped:,} skipped "
        f"({int(stats.get('skipped_missing_order') or 0):,} no order #, "
        f"{int(stats.get('skipped_missing_date') or 0):,} no date, "
        f"{int(stats.get('skipped_outside_window') or 0):,} outside {mirror.SALESLINE_WINDOW_DAYS} days)"
    )


def _last_salesline_stats_message() -> str:
    raw = get_app_setting(_LAST_ORDER_MIRROR_STATS_KEY)
    if not raw:
        return ""
    try:
        return _salesline_stats_message(json.loads(raw))
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

        _set_step(scope, f"Refreshing salesline mirror ({mirror.SALESLINE_WINDOW_DAYS} days)...")
        order_rows, order_source = _fetch_order_history(salesman_key)
        stats: dict[str, int] = {
            "rows_in": len(order_rows),
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "pruned": 0,
            "skipped_missing_order": 0,
            "skipped_missing_date": 0,
            "skipped_outside_window": 0,
        }
        if order_rows:
            stats = mirror.upsert_salesline(order_rows, trigger="dashboard")
            _set_step(
                scope,
                _salesline_stats_message(stats),
            )
        _refresh_state.setdefault(scope, {})["order_mirror_stats"] = stats
        _refresh_state.setdefault(scope, {})["order_source"] = order_source
        _set_step(scope, f"Received {len(order_rows):,} order lines")

        now = datetime.now().isoformat(timespec="seconds")
        _last_refresh = now
        set_app_setting(_LAST_COMPLETED_KEY, now)
        set_app_setting(_LAST_CUSTOMER_SOURCE_KEY, customer_source)
        set_app_setting(_LAST_ORDER_SOURCE_KEY, order_source)
        set_app_setting(_LAST_ORDER_MIRROR_STATS_KEY, json.dumps(stats))
        set_app_setting(_LAST_ERROR_KEY, "")
        _set_step(scope, f"Done - mirrors refreshed ({len(customer_rows):,} customers, {len(order_rows):,} order lines)")
        log.info("Dashboard mirror refresh complete (%s): %d customers, %d order lines",
                 scope_label, len(customer_rows), len(order_rows))
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
    return {
        "running": bool(state.get("running", False)),
        "step": state.get("step", ""),
        "last_requested": _last_refresh_requested or get_app_setting(_LAST_REQUESTED_KEY),
        "last_completed": get_last_refresh(),
        "cache_customers": counts["customers"],
        "cache_order_lines": counts["order_lines"],
        "dated_order_lines": counts["dated_order_lines"],
        "customers_with_last_order": counts["customers_with_last_order"],
        "order_customers": counts["order_customers"],
        "customer_source": state.get("customer_source") or get_app_setting(_LAST_CUSTOMER_SOURCE_KEY),
        "order_source": state.get("order_source") or get_app_setting(_LAST_ORDER_SOURCE_KEY),
        "order_mirror_stats": _salesline_stats_message(state.get("order_mirror_stats")) or _last_salesline_stats_message(),
        "last_error": get_app_setting(_LAST_ERROR_KEY),
        "salesline_window_days": mirror.SALESLINE_WINDOW_DAYS,
    }


def get_cache_counts() -> dict[str, int]:
    mirror.init_mirror_db()
    with connect() as conn:
        customers = conn.execute("SELECT COUNT(*) FROM mirror_customers").fetchone()[0]
        dated_order_lines = conn.execute(
            "SELECT COUNT(*) FROM mirror_salesline WHERE order_date <> ''"
        ).fetchone()[0]
        order_lines = conn.execute("SELECT COUNT(*) FROM mirror_salesline").fetchone()[0]
        order_customers = conn.execute(
            "SELECT COUNT(DISTINCT customer_account) FROM mirror_salesline WHERE order_date <> ''"
        ).fetchone()[0]
    return {
        "customers": int(customers or 0),
        "order_lines": int(order_lines or 0),
        "dated_order_lines": int(dated_order_lines or 0),
        "order_customers": int(order_customers or 0),
        "customers_with_last_order": int(order_customers or 0),
    }


def get_cache_quality_warning() -> str:
    counts = get_cache_counts()
    if counts["customers"] or counts["order_lines"]:
        return ""
    return (
        "No mirrored endpoint data is available yet. Run an ordered report or refresh "
        "the dashboard to populate the shared customer and salesline mirrors."
    )


def cache_needs_order_refresh() -> bool:
    """True when the shared endpoint mirrors are empty."""
    counts = get_cache_counts()
    return counts["customers"] <= 0 or counts["order_lines"] <= 0 or counts["dated_order_lines"] <= 0


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


def _read_mirror_customers() -> dict[str, dict[str, str]]:
    mirror.init_mirror_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT customer_account, customer_name, sales_group
            FROM mirror_customers
            """
        ).fetchall()
    customers: dict[str, dict[str, str]] = {}
    for row in rows:
        acct = _normalize_customer_account(row["customer_account"])
        if not acct:
            continue
        customers[acct] = {
            "customer_account": acct,
            "customer_name": (row["customer_name"] or "").strip() or acct,
            "sales_group": (row["sales_group"] or "").strip(),
        }
    return customers


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


def _build_dashboard_rows_from_mirror() -> list[dict[str, Any]]:
    lines = _read_mirror_lines()
    orders = _group_mirror_orders(lines)
    last_seen = (mirror.mirror_freshness().get("salesline") or {}).get("last_seen_utc") or ""

    order_dates_by_customer: dict[str, dict[str, str]] = {}
    customer_fallbacks: dict[str, dict[str, str]] = {}
    for order in orders:
        acct = _normalize_customer_account(order.get("customer_account"))
        if not acct:
            continue
        order_date = _date_only(order.get("order_date"))
        if order_date:
            order_dates_by_customer.setdefault(acct, {})[order["order_number"]] = order_date
        customer_fallbacks.setdefault(acct, {
            "customer_name": order.get("customer_name") or acct,
            "sales_group": order.get("salesman") or "",
        })

    customers_by_account = _read_mirror_customers()

    for acct, fallback in customer_fallbacks.items():
        existing = customers_by_account.get(acct)
        if existing:
            if not existing.get("sales_group") and fallback.get("sales_group"):
                existing["sales_group"] = fallback["sales_group"]
            if not existing.get("customer_name") and fallback.get("customer_name"):
                existing["customer_name"] = fallback["customer_name"]
        else:
            customers_by_account[acct] = {
                "customer_account": acct,
                "customer_name": fallback["customer_name"] or acct,
                "sales_group": fallback["sales_group"],
            }

    metrics: list[dict[str, Any]] = []
    for acct, customer in customers_by_account.items():
        dates = sorted(order_dates_by_customer.get(acct, {}).values())
        metric = _compute_customer_metrics(
            acct,
            customer["customer_name"],
            customer["sales_group"],
            dates,
        )
        metric["last_refreshed"] = last_seen
        metric["mirror_window_days"] = mirror.SALESLINE_WINDOW_DAYS
        metrics.append(metric)
    return metrics


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
    account = _normalize_customer_account(account)
    for row in _build_dashboard_rows_from_mirror():
        if row.get("customer_account") == account:
            return row
    return None


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
    """Start periodic dashboard refresh; initial refresh only runs on empty cache."""
    global _refresh_thread
    if _refresh_thread and _refresh_thread.is_alive():
        return

    counts = get_cache_counts()
    has_data = counts["customers"] > 0 and counts["order_lines"] > 0

    def _loop() -> None:
        if not has_data:
            try:
                mark_refresh_requested()
                refresh_cache()
            except Exception:
                log.exception("Initial dashboard background refresh failed")
        while True:
            time.sleep(REFRESH_INTERVAL_SECONDS)
            try:
                mark_refresh_requested()
                refresh_cache()
            except Exception:
                log.exception("Dashboard background refresh failed")

    _refresh_thread = threading.Thread(target=_loop, name="v2-dashboard-refresh", daemon=True)
    _refresh_thread.start()
