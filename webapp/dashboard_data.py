"""
Dashboard data layer -- background D365 fetch, frequency analysis, caching.

Fetches customer + order header data from D365 on a background thread,
computes per-customer ordering frequency metrics, and stores results in
the SQLite dashboard_cache table.
"""

import json
import logging
import math
import os
import sys
import threading
import time
from datetime import date, datetime, timedelta

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from webapp.db import get_db, add_notification, get_excluded_customers, get_setting, set_setting

log = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 4 * 3600  # 4 hours
_SYSTEM_EMAIL = "_system_"
_refresh_thread: threading.Thread | None = None
_last_refresh: str | None = None
_last_refresh_requested: str | None = None

_SCOPE_ALL = "__all__"
_refresh_state: dict[str, dict] = {}
# keyed by scope string ("__all__" for full, or salesman_key for salesman)
# value: {"running": bool, "step": str}


def _load_persisted_timestamps():
    """Load persisted refresh timestamps from SQLite on startup."""
    global _last_refresh_requested, _last_refresh
    try:
        val = get_setting(_SYSTEM_EMAIL, "last_refresh_requested")
        if val:
            _last_refresh_requested = val
        val = get_setting(_SYSTEM_EMAIL, "last_refresh_completed")
        if val:
            _last_refresh = val
    except Exception:
        pass


_load_persisted_timestamps()


def _compute_customer_metrics(customer_account: str, customer_name: str,
                              sales_group: str, order_dates: list[str]) -> dict:
    """Compute ordering frequency stats for a single customer."""
    today = date.today()
    result = {
        "customer_account": customer_account,
        "customer_name": customer_name,
        "sales_group": sales_group,
        "order_dates": json.dumps(order_dates),
        "last_order_date": None,
        "avg_gap_days": None,
        "gap_stdev": None,
        "overdue_threshold": None,
        "days_since_last": None,
        "status": "new",
    }

    if not order_dates:
        return result

    parsed = sorted(
        datetime.strptime(d[:10], "%Y-%m-%d").date()
        for d in order_dates if d and len(d) >= 10
    )
    if not parsed:
        return result

    last = parsed[-1]
    result["last_order_date"] = last.isoformat()
    result["days_since_last"] = (today - last).days

    if len(parsed) < 3:
        result["status"] = "new"
        return result

    gaps = [(parsed[i + 1] - parsed[i]).days for i in range(len(parsed) - 1)]
    gaps = [g for g in gaps if g > 0]

    if not gaps:
        result["status"] = "new"
        return result

    mean_gap = sum(gaps) / len(gaps)
    variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
    stdev = math.sqrt(variance)

    threshold = mean_gap + stdev
    days_since = result["days_since_last"]

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


def refresh_cache(salesman_key: str | None = None):
    """Fetch data from D365 and update the dashboard_cache table.

    If salesman_key is provided, only fetches and updates that salesman's
    customers — much faster than a full refresh.
    """
    global _last_refresh
    scope_key = salesman_key or _SCOPE_ALL
    scope_label = f"salesman={salesman_key}" if salesman_key else "all"
    log.info("Dashboard cache refresh starting (scope: %s)...", scope_label)
    _refresh_state[scope_key] = {"running": True, "step": "Authenticating with D365…"}

    def _step(msg: str):
        _refresh_state[scope_key]["step"] = msg

    try:
        from config.settings import (
            get_client_id, get_client_secret, get_company_id,
            get_d365_env_url, get_tenant_id, validate_d365_config,
        )
        from core.auth import get_d365_token
        from data.d365_entities import fetch_customers, fetch_sales_order_headers
        from core.dates import get_today_eastern

        validate_d365_config()
        env_url = get_d365_env_url().rstrip("/")
        base_url = (
            f"{env_url}/data/"
            if "/data" not in env_url.lower()
            else (env_url if env_url.endswith("/") else f"{env_url}/")
        )
        token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), env_url)
        company = get_company_id() or None
        today = get_today_eastern()

        if salesman_key:
            _step(f"Fetching customers for {salesman_key} from D365…")
            customers_df = fetch_customers(
                base_url, token, company_id=company, sales_group=salesman_key)
        else:
            _step("Fetching all customers from D365…")
            customers_df = fetch_customers(base_url, token, company_id=company)

        log.info("Dashboard: fetched %d customers", len(customers_df))
        _step(f"Received {len(customers_df):,} customers")

        if customers_df.empty:
            log.info("Dashboard: no customers to process")
            _step("No customers found")
            return

        customers_df["CustomerAccount"] = customers_df["CustomerAccount"].astype(str).str.strip()
        cust_accounts = list(customers_df["CustomerAccount"].unique())

        all_time_start = date(2025, 1, 1)
        if salesman_key:
            _step(f"Fetching order history for {len(cust_accounts)} customers…")
            headers_df = fetch_sales_order_headers(
                base_url, token, all_time_start, today,
                company_id=company, customer_account=cust_accounts)
        else:
            _step("Fetching all order history from D365… (this may take a while)")
            headers_df = fetch_sales_order_headers(
                base_url, token, all_time_start, today, company_id=company)

        log.info("Dashboard: fetched %d order headers", len(headers_df))
        _step(f"Received {len(headers_df):,} order headers")

        import pandas as pd
        from core.dates import convert_d365_dates_to_eastern

        _step("Processing order dates…")
        if "OrderDate" in headers_df.columns and not headers_df.empty:
            headers_df["OrderDate"] = convert_d365_dates_to_eastern(headers_df["OrderDate"])

        headers_df["CustomerAccount"] = headers_df["CustomerAccount"].astype(str).str.strip()

        order_dates_by_cust: dict[str, list[str]] = {}
        if not headers_df.empty and "OrderDate" in headers_df.columns:
            for acct, grp in headers_df.groupby("CustomerAccount"):
                dates = grp["OrderDate"].dropna()
                order_dates_by_cust[str(acct)] = sorted(
                    d.strftime("%Y-%m-%d") for d in dates if pd.notna(d)
                )

        _step(f"Computing metrics for {len(customers_df)} customers…")
        now_str = datetime.now().isoformat(timespec="seconds")
        metrics = []
        for _, row in customers_df.iterrows():
            acct = str(row.get("CustomerAccount", "")).strip()
            name = str(row.get("CustomerName", "")).strip()
            sg = str(row.get("SalesGroup", "")).strip()
            dates = order_dates_by_cust.get(acct, [])
            m = _compute_customer_metrics(acct, name, sg, dates)
            m["last_refreshed"] = now_str
            metrics.append(m)

        _step("Saving results to database…")
        conn = get_db()
        try:
            if salesman_key:
                acct_list = [m["customer_account"] for m in metrics]
                placeholders = ",".join("?" * len(acct_list))
                conn.execute(
                    f"DELETE FROM dashboard_cache WHERE customer_account IN ({placeholders})",
                    acct_list,
                )
            else:
                conn.execute("DELETE FROM dashboard_cache")

            conn.executemany(
                """INSERT INTO dashboard_cache
                   (customer_account, customer_name, sales_group, last_order_date,
                    order_dates, avg_gap_days, gap_stdev, overdue_threshold,
                    days_since_last, status, last_refreshed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (m["customer_account"], m["customer_name"], m["sales_group"],
                     m["last_order_date"], m["order_dates"],
                     m["avg_gap_days"], m["gap_stdev"], m["overdue_threshold"],
                     m["days_since_last"], m["status"], m["last_refreshed"])
                    for m in metrics
                ],
            )
            conn.commit()
        finally:
            conn.close()

        _last_refresh = now_str
        try:
            set_setting(_SYSTEM_EMAIL, "last_refresh_completed", _last_refresh)
        except Exception:
            pass
        _step(f"Done — {len(metrics)} customers updated")
        log.info("Dashboard cache refreshed: %d customers (scope: %s)", len(metrics), scope_label)

        _generate_overdue_notifications(metrics)

    except Exception:
        log.exception("Dashboard cache refresh failed")
        _step("Refresh failed — see server logs")
    finally:
        _refresh_state[scope_key]["running"] = False


def _generate_overdue_notifications(metrics: list[dict]):
    """Create overdue-customer notifications for real app users."""
    from webapp.db import (
        get_notifications, get_users_by_salesman_key, get_all_users,
    )

    overdue = [m for m in metrics if m["status"] == "overdue"]
    if not overdue:
        return

    by_group: dict[str, list[dict]] = {}
    for m in overdue:
        sg = m["sales_group"]
        if sg:
            by_group.setdefault(sg, []).append(m)

    all_users = get_all_users()
    admin_emails = [
        u["email"] for u in all_users
        if u["role"] in ("admin", "developer")
    ]

    def _send_for_user(email: str, custs: list[dict]):
        excluded = get_excluded_customers(email)
        existing_notifs = get_notifications(email, dismissed=False)
        existing_accts = {
            n.get("data", {}).get("customer_account")
            for n in existing_notifs
            if n["type"] == "overdue_customer"
        }

        for c in custs:
            if c["customer_account"] in excluded:
                continue
            if c["customer_account"] in existing_accts:
                continue

            avg = c.get("avg_gap_days") or 0
            days = c.get("days_since_last") or 0
            avg_weeks = round(avg / 7, 1)
            days_weeks = round(days / 7, 1)

            title = f"{c['customer_name'] or c['customer_account']} is overdue"
            message = (
                f"Usually orders every ~{avg_weeks} weeks, "
                f"but it has been {days_weeks} weeks since their last order."
            )

            add_notification(
                user_email=email,
                ntype="overdue_customer",
                title=title,
                message=message,
                data={"customer_account": c["customer_account"],
                      "customer_name": c["customer_name"]},
            )

    all_overdue_custs = []
    for sg_key, custs in by_group.items():
        all_overdue_custs.extend(custs)
        matched_users = get_users_by_salesman_key(sg_key)
        for u in matched_users:
            _send_for_user(u["email"], custs)

    for admin_email in admin_emails:
        _send_for_user(admin_email, all_overdue_custs)


def get_dashboard_data(salesman_key: str | None = None,
                       exclude_accounts: list[str] | None = None) -> list[dict]:
    """Query the cached dashboard data, optionally filtered."""
    from webapp.db import normalize_key
    conn = get_db()
    try:
        if salesman_key:
            norm = normalize_key(salesman_key)
            rows = conn.execute(
                "SELECT * FROM dashboard_cache ORDER BY customer_name"
            ).fetchall()
            rows = [r for r in rows if normalize_key(r["sales_group"] or "") == norm]
        else:
            rows = conn.execute(
                "SELECT * FROM dashboard_cache ORDER BY customer_name"
            ).fetchall()

        result = []
        exclude_set = set(exclude_accounts or [])
        for r in rows:
            d = dict(r)
            d["excluded"] = d["customer_account"] in exclude_set
            d["order_dates"] = json.loads(d["order_dates"]) if d["order_dates"] else []
            result.append(d)
        return result
    finally:
        conn.close()


def get_dashboard_summary(data: list[dict]) -> dict:
    """Compute summary stats from cached dashboard data (excluding excluded)."""
    included = [d for d in data if not d.get("excluded")]
    total = len(included)
    active = sum(1 for d in included if d.get("status") == "active")
    overdue = sum(1 for d in included if d.get("status") == "overdue")
    inactive = sum(1 for d in included if d.get("status") == "inactive")

    avg_gaps = [d["avg_gap_days"] for d in included
                if d.get("avg_gap_days") and d["avg_gap_days"] > 0]
    avg_freq = round(sum(avg_gaps) / len(avg_gaps), 1) if avg_gaps else 0

    return {
        "total_customers": total,
        "active": active,
        "overdue": overdue,
        "inactive": inactive,
        "avg_frequency_days": avg_freq,
    }


def get_last_refresh() -> str | None:
    """Return the timestamp of the last cache refresh."""
    global _last_refresh
    if _last_refresh:
        return _last_refresh
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT last_refreshed FROM dashboard_cache LIMIT 1"
        ).fetchone()
        if row:
            _last_refresh = row["last_refreshed"]
            return _last_refresh
    finally:
        conn.close()
    return None


def mark_refresh_requested() -> str:
    """Record when a refresh was requested. Persists to SQLite."""
    global _last_refresh_requested
    _last_refresh_requested = datetime.now().isoformat(timespec="seconds")
    try:
        set_setting(_SYSTEM_EMAIL, "last_refresh_requested", _last_refresh_requested)
    except Exception:
        pass
    return _last_refresh_requested


def get_refresh_status(salesman_key: str | None = None) -> dict:
    """Return a snapshot of refresh timing and running state for a scope.

    Salesmen only see their own refresh state. Admins (salesman_key=None)
    see the global full-refresh state.
    """
    scope_key = salesman_key or _SCOPE_ALL
    state = _refresh_state.get(scope_key, {})
    return {
        "running": state.get("running", False),
        "step": state.get("step", ""),
        "last_requested": _last_refresh_requested,
        "last_completed": get_last_refresh(),
    }


def start_background_refresh():
    """Start the periodic background refresh thread.

    Only runs an immediate refresh if the cache is completely empty.
    Otherwise waits the full interval before the first scheduled refresh.
    """
    global _refresh_thread
    if _refresh_thread and _refresh_thread.is_alive():
        return

    has_data = get_last_refresh() is not None

    def _loop():
        if not has_data:
            log.info("Dashboard cache is empty — running initial refresh")
            try:
                mark_refresh_requested()
                refresh_cache()
            except Exception:
                log.exception("Background refresh error (initial)")
        while True:
            time.sleep(REFRESH_INTERVAL_SECONDS)
            try:
                mark_refresh_requested()
                refresh_cache()
            except Exception:
                log.exception("Background refresh error")

    _refresh_thread = threading.Thread(target=_loop, daemon=True, name="dashboard-refresh")
    _refresh_thread.start()
    log.info("Dashboard background refresh thread started (interval: %ds, immediate: %s)",
             REFRESH_INTERVAL_SECONDS, not has_data)
