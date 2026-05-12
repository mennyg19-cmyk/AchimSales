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
from test.config.settings import USE_MOCK_DATA
from test.webapp.db import (
    connect,
    get_app_setting,
    get_user_salesman_access,
    normalize_key,
    set_app_setting,
)
from test.webapp.services import report_fixtures, reporting_api
from test.webapp.services.report_access import get_user_profile
from test.webapp.services.reports.ordered import _norm_row

log = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 4 * 3600
_DEFAULT_COMPANY = (os.environ.get("REPORTING_API_DEFAULT_COMPANY") or "ACHM").strip()
_SCOPE_ALL = "__all__"
_LAST_REQUESTED_KEY = "dashboard.last_refresh_requested"
_LAST_COMPLETED_KEY = "dashboard.last_refresh_completed"
_LAST_CUSTOMER_SOURCE_KEY = "dashboard.last_customer_source"
_LAST_ORDER_SOURCE_KEY = "dashboard.last_order_source"

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


def _customer_account(raw: dict) -> str:
    return str(
        raw.get("CustomerAccount")
        or raw.get("customeraccount")
        or raw.get("AccountNum")
        or raw.get("accountnum")
        or ""
    ).strip()


def _customer_name(raw: dict) -> str:
    return str(raw.get("CustomerName") or raw.get("customername") or "").strip()


def _sales_group(raw: dict) -> str:
    return str(raw.get("SalesGroup") or raw.get("salesgroup") or raw.get("sales_group") or "").strip()


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
    result["days_since_last"] = (today - last).days

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
    days_since = int(result["days_since_last"] or 0)

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
    # Include Company so the all-time refresh never sends an empty SP body.
    params: dict[str, Any] = {"period": "all_time"}
    if _DEFAULT_COMPANY:
        params["company"] = _DEFAULT_COMPANY
    if salesman_key:
        params["salesman"] = salesman_key
    try:
        rows = reporting_api.run("ordered", params)
        source = _source_label(reporting_api.last_run_source())
    except Exception as exc:
        rows = None
        source = "unavailable"
        if USE_MOCK_DATA or not reporting_api.is_configured():
            fixture_rows = report_fixtures.load_ordered_rows()
            if fixture_rows is not None:
                rows = report_fixtures.filter_ordered_rows(fixture_rows, params)
                source = "ordered fixture"
                log.warning(
                    "Dashboard order fetch failed; using ordered fixture rows (%d): %s",
                    len(rows),
                    exc,
                )
        if rows is None:
            raise
    return list(rows or []), source


def _cached_order_line(line: dict[str, Any], refreshed_at: str) -> tuple[Any, ...]:
    return (
        line.get("SalesOrderNumber") or "",
        int(_num(line.get("LineNumber"))),
        line.get("CustomerAccount") or "",
        line.get("CustomerName") or "",
        line.get("Salesman") or "",
        _date_only(line.get("OrderDate")),
        line.get("PO #") or "",
        line.get("Item#") or "",
        line.get("ItemName") or "",
        line.get("Status") or "",
        _num(line.get("QtyOrdered")),
        _num(line.get("QtyShipped")),
        _num(line.get("QtyCancelled")),
        _num(line.get("UnitPrice")),
        _num(line.get("Ordered $")),
        _num(line.get("Shipped $")),
        refreshed_at,
    )


def _row_to_order_line(row: Any) -> dict[str, Any]:
    return {
        "SalesOrderNumber": row["sales_order_number"],
        "LineNumber": row["line_number"],
        "CustomerAccount": row["customer_account"],
        "CustomerName": row["customer_name"],
        "Salesman": row["sales_group"],
        "OrderDate": row["order_date"],
        "PO #": row["customer_req"],
        "Item#": row["item_number"],
        "ItemName": row["item_name"],
        "Status": row["status"],
        "QtyOrdered": row["qty_ordered"],
        "QtyShipped": row["qty_shipped"],
        "QtyCancelled": row["qty_cancelled"],
        "UnitPrice": row["sales_price"],
        "Ordered $": row["ordered_dollars"],
        "Shipped $": row["shipped_dollars"],
    }


def refresh_cache(salesman_key: str | None = None) -> None:
    """Refresh dashboard_cache from reporting API data."""
    global _last_refresh
    scope = _scope_key(salesman_key)
    scope_label = f"salesman={salesman_key}" if salesman_key else "all"
    _refresh_state[scope] = {"running": True, "step": "Starting dashboard refresh..."}
    log.info("Dashboard refresh starting (%s)", scope_label)

    try:
        _set_step(scope, "Fetching customer master data...")
        customer_rows, customer_source = _fetch_customers(salesman_key)
        _refresh_state.setdefault(scope, {})["customer_source"] = customer_source
        _set_step(scope, f"Received {len(customer_rows):,} customers")

        _set_step(scope, "Fetching order history...")
        order_rows, order_source = _fetch_order_history(salesman_key)
        _refresh_state.setdefault(scope, {})["order_source"] = order_source
        _set_step(scope, f"Received {len(order_rows):,} order lines")

        now = datetime.now().isoformat(timespec="seconds")
        order_dates_by_customer: dict[str, dict[str, str]] = {}
        customer_fallbacks: dict[str, dict[str, str]] = {}
        normalized_lines: list[dict[str, Any]] = []
        for raw in order_rows:
            line = _norm_row(raw)
            normalized_lines.append(line)
            acct = (line.get("CustomerAccount") or "").strip()
            order_date = _date_only(line.get("OrderDate"))
            if not acct or not order_date:
                continue
            order_no = line.get("SalesOrderNumber") or f"{acct}:{order_date}:{line.get('LineNumber')}"
            order_dates_by_customer.setdefault(acct, {})[order_no] = order_date
            customer_fallbacks.setdefault(acct, {
                "customer_name": line.get("CustomerName") or acct,
                "sales_group": line.get("Salesman") or "",
            })

        _set_step(scope, "Computing customer activity metrics...")
        customers_by_account: dict[str, dict[str, str]] = {}
        for raw in customer_rows:
            acct = _customer_account(raw)
            if not acct:
                continue
            customers_by_account[acct] = {
                "customer_account": acct,
                "customer_name": _customer_name(raw) or acct,
                "sales_group": _sales_group(raw),
            }

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
            metric["last_refreshed"] = now
            metrics.append(metric)

        _set_step(scope, "Saving dashboard cache...")
        with connect() as conn:
            if salesman_key:
                norm = normalize_key(salesman_key)
                rows = conn.execute(
                    "SELECT customer_account, sales_group FROM dashboard_cache"
                ).fetchall()
                stale_accounts = [
                    r["customer_account"]
                    for r in rows
                    if normalize_key(r["sales_group"]) == norm
                ]
                if stale_accounts:
                    conn.executemany(
                        "DELETE FROM dashboard_cache WHERE customer_account = ?",
                        [(a,) for a in stale_accounts],
                    )
            else:
                conn.execute("DELETE FROM dashboard_cache")
                conn.execute("DELETE FROM dashboard_order_cache")

            conn.executemany(
                """
                INSERT INTO dashboard_cache (
                    customer_account, customer_name, sales_group, last_order_date,
                    order_dates, avg_gap_days, gap_stdev, overdue_threshold,
                    days_since_last, status, last_refreshed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        m["customer_account"],
                        m["customer_name"],
                        m["sales_group"],
                        m["last_order_date"],
                        json.dumps(m["order_dates"]),
                        m["avg_gap_days"],
                        m["gap_stdev"],
                        m["overdue_threshold"],
                        m["days_since_last"],
                        m["status"],
                        m["last_refreshed"],
                    )
                    for m in metrics
                ],
            )

            if salesman_key:
                existing_order_rows = conn.execute(
                    "SELECT sales_order_number, line_number, item_number, sales_group "
                    "FROM dashboard_order_cache"
                ).fetchall()
                stale_order_keys = [
                    (r["sales_order_number"], r["line_number"], r["item_number"])
                    for r in existing_order_rows
                    if normalize_key(r["sales_group"]) == norm
                ]
                if stale_order_keys:
                    conn.executemany(
                        """
                        DELETE FROM dashboard_order_cache
                        WHERE sales_order_number = ? AND line_number = ? AND item_number = ?
                        """,
                        stale_order_keys,
                    )

            conn.executemany(
                """
                INSERT OR REPLACE INTO dashboard_order_cache (
                    sales_order_number, line_number, customer_account, customer_name,
                    sales_group, order_date, customer_req, item_number, item_name,
                    status, qty_ordered, qty_shipped, qty_cancelled, sales_price,
                    ordered_dollars, shipped_dollars, last_refreshed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    _cached_order_line(line, now)
                    for line in normalized_lines
                    if line.get("SalesOrderNumber")
                ],
            )

        _last_refresh = now
        set_app_setting(_LAST_COMPLETED_KEY, now)
        set_app_setting(_LAST_CUSTOMER_SOURCE_KEY, customer_source)
        set_app_setting(_LAST_ORDER_SOURCE_KEY, order_source)
        _set_step(scope, f"Done - {len(metrics):,} customers updated")
        log.info("Dashboard refresh complete (%s): %d customers", scope_label, len(metrics))
    except Exception:
        log.exception("Dashboard refresh failed (%s)", scope_label)
        _set_step(scope, "Refresh failed - see server logs")
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
        with connect() as conn:
            row = conn.execute(
                "SELECT last_refreshed FROM dashboard_cache ORDER BY last_refreshed DESC LIMIT 1"
            ).fetchone()
        if row:
            _last_refresh = row["last_refreshed"]
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
        "customer_source": state.get("customer_source") or get_app_setting(_LAST_CUSTOMER_SOURCE_KEY),
        "order_source": state.get("order_source") or get_app_setting(_LAST_ORDER_SOURCE_KEY),
    }


def get_cache_counts() -> dict[str, int]:
    with connect() as conn:
        customers = conn.execute("SELECT COUNT(*) FROM dashboard_cache").fetchone()[0]
        order_lines = conn.execute("SELECT COUNT(*) FROM dashboard_order_cache").fetchone()[0]
        dated_order_lines = conn.execute(
            "SELECT COUNT(*) FROM dashboard_order_cache WHERE order_date <> ''"
        ).fetchone()[0]
        customers_with_last_order = conn.execute(
            "SELECT COUNT(*) FROM dashboard_cache WHERE last_order_date IS NOT NULL AND last_order_date <> ''"
        ).fetchone()[0]
    return {
        "customers": int(customers or 0),
        "order_lines": int(order_lines or 0),
        "dated_order_lines": int(dated_order_lines or 0),
        "customers_with_last_order": int(customers_with_last_order or 0),
    }


def cache_needs_order_refresh() -> bool:
    """True when customer rows exist but order/date data was not populated."""
    counts = get_cache_counts()
    if counts["customers"] <= 0:
        return True
    return counts["order_lines"] <= 0 or counts["dated_order_lines"] <= 0 or counts["customers_with_last_order"] <= 0


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
    """Read dashboard rows from cache with salesman/exclusion scoping."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM dashboard_cache ORDER BY customer_name").fetchall()

    salesman_norm = normalize_key(salesman_key)
    allowed_norm = {normalize_key(k) for k in (allowed_salesman_keys or []) if normalize_key(k)}
    excluded = set(exclude_accounts or [])

    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        group_norm = normalize_key(item.get("sales_group"))
        if salesman_norm and group_norm != salesman_norm:
            continue
        if allowed_norm and group_norm not in allowed_norm:
            continue
        item["excluded"] = item["customer_account"] in excluded
        try:
            item["order_dates"] = json.loads(item.get("order_dates") or "[]")
        except json.JSONDecodeError:
            item["order_dates"] = []
        out.append(item)
    return out


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
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM dashboard_cache WHERE customer_account = ?",
            (account,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["order_dates"] = json.loads(item.get("order_dates") or "[]")
    except json.JSONDecodeError:
        item["order_dates"] = []
    return item


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


def _summarize_order_status(lines: list[dict[str, Any]]) -> str:
    statuses = sorted({(ln.get("Status") or "").strip() for ln in lines if (ln.get("Status") or "").strip()})
    if not statuses:
        return ""
    return statuses[0] if len(statuses) == 1 else "Mixed"


def _group_order_headers(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for line in lines:
        order_no = line.get("SalesOrderNumber") or ""
        if order_no:
            grouped.setdefault(order_no, []).append(line)

    headers: list[dict[str, Any]] = []
    for order_no, order_lines in grouped.items():
        first = order_lines[0]
        headers.append({
            "order_number": order_no,
            "order_date": _date_only(first.get("OrderDate")),
            "status": _summarize_order_status(order_lines),
            "processing_status": "",
            "customer_req": first.get("PO #") or "",
            "order_name": "",
            "salesman": first.get("Salesman") or "",
            "customer_account": first.get("CustomerAccount") or "",
            "customer_name": first.get("CustomerName") or "",
            "order_total": round(sum(_num(ln.get("Ordered $")) for ln in order_lines), 2),
        })
    headers.sort(key=lambda h: (h["order_date"] or "0000-00-00", h["order_number"]), reverse=True)
    return headers


def _cached_lines_for_customer(account: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM dashboard_order_cache
            WHERE customer_account = ?
            ORDER BY order_date DESC, sales_order_number DESC, line_number
            """,
            (account,),
        ).fetchall()
    return [_row_to_order_line(r) for r in rows]


def _cached_lines_for_order(order_number: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM dashboard_order_cache
            WHERE sales_order_number = ?
            ORDER BY line_number, item_number
            """,
            (order_number,),
        ).fetchall()
    return [_row_to_order_line(r) for r in rows]


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

    try:
        rows = reporting_api.run("customer_master", {"customer_account": account})
    except Exception:
        log.exception("dashboard customer lookup failed: %s", account)
        rows = []
    if rows:
        raw = rows[0]
        return {
            "account": _customer_account(raw) or account,
            "name": _customer_name(raw) or account,
            "sales_group": _sales_group(raw),
            "status": "",
            "days_since_last": None,
            "avg_gap_days": None,
            "overdue_threshold": None,
        }
    return {"account": account, "name": account, "sales_group": "", "status": ""}


def fetch_customer_orders(account: str, *, days: int | None = 7, last_n: int | None = None) -> list[dict[str, Any]]:
    lines = _cached_lines_for_customer(account)
    if not last_n and days and days < 9999:
        today = get_today_eastern()
        start = max(D365_GO_LIVE, today - timedelta(days=days))
        lines = [
            line for line in lines
            if (parsed := _parse_date(_date_only(line.get("OrderDate")))) is not None
            and start <= parsed <= today
        ]
    headers = _group_order_headers(lines)
    if last_n:
        return headers[:last_n]
    return headers


def fetch_order_detail(order_number: str) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    lines = _cached_lines_for_order(order_number)
    if not lines:
        return {"order_number": order_number}, [], ""

    first = lines[0]
    customer_account = first.get("CustomerAccount") or ""
    header = {
        "order_number": order_number,
        "order_date": _date_only(first.get("OrderDate")),
        "status": _summarize_order_status(lines),
        "processing_status": "",
        "customer_req": first.get("PO #") or "",
        "order_name": "",
        "customer_name": first.get("CustomerName") or "",
        "salesman": first.get("Salesman") or "",
    }

    detail_lines: list[dict[str, Any]] = []
    for line in sorted(lines, key=lambda ln: _num(ln.get("LineNumber"))):
        detail_lines.append({
            "order_number": line.get("SalesOrderNumber") or order_number,
            "line_number": int(_num(line.get("LineNumber"))),
            "item": line.get("Item#") or "",
            "description": line.get("ItemName") or "",
            "qty_ordered": _num(line.get("QtyOrdered")),
            "qty_shipped": _num(line.get("QtyShipped")),
            "qty_cancelled": _num(line.get("QtyCancelled")),
            "sales_price": _num(line.get("UnitPrice")),
            "total_ordered": _num(line.get("Ordered $")),
            "total_shipped": _num(line.get("Shipped $")),
            "total": _num(line.get("Shipped $")),
            "status": line.get("Status") or "",
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
