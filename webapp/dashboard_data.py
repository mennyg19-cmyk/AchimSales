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

    # "new" = exactly 1 order. With 2+ orders we have at least 1 gap, which
    # is enough to compute a (rough) avg-frequency baseline. With 2 orders
    # stdev=0, so threshold=avg_gap; with 3+ orders we get a real spread.
    if len(parsed) < 2:
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
        from core.dates import D365_GO_LIVE, get_today_eastern

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

        all_time_start = D365_GO_LIVE
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
        log.info("Dashboard cache refreshed: %d customers (scope: %s)", len(metrics), scope_label)

        # Product / address / price caches were dropped along with the
        # disabled order-entry feature. Skip those refresh steps. If
        # order entry comes back, recreate the tables and re-enable
        # these calls.

        # -- Runbook history sync --
        try:
            _step("Syncing runbook history…")
            sync_runbook_history()
        except Exception:
            log.exception("Runbook history sync failed during refresh (non-fatal)")

        _step(f"Done — {len(metrics)} customers updated")

        _generate_overdue_notifications(metrics)

    except Exception:
        log.exception("Dashboard cache refresh failed")
        _step("Refresh failed — see server logs")
    finally:
        _refresh_state[scope_key]["running"] = False


def _refresh_product_cache(base_url, token, company, _step):
    """Fetch ReleasedProductsV2 + DVReleasedProducts descriptions and update the product_cache table."""
    from data.d365_entities import fetch_book_prices, fetch_product_names
    from webapp.db import upsert_product_cache
    try:
        _step("Fetching product catalog from D365…")
        products_df = fetch_book_prices(base_url, token, company_id=company)
        if products_df.empty:
            log.info("Product cache: no products returned from D365")
            return

        item_numbers = products_df["ItemNumber"].tolist()
        desc_map = {}
        try:
            _step("Fetching product descriptions from DVReleasedProducts…")
            desc_df = fetch_product_names(base_url, token, item_numbers, company_id=company)
            if not desc_df.empty:
                for _, r in desc_df.iterrows():
                    desc_map[str(r.get("ItemNumber", "")).strip()] = str(r.get("ProductName", "")).strip()
                log.info("Fetched %d product descriptions", len(desc_map))
        except Exception:
            log.exception("DVReleasedProducts fetch failed (non-fatal, descriptions will be empty)")

        rows = products_df.to_dict("records")
        for row in rows:
            row["Description"] = desc_map.get(row.get("ItemNumber", ""), "")
        upsert_product_cache(rows)
        log.info("Product cache refreshed: %d items", len(rows))
    except Exception:
        log.exception("Product cache refresh failed (non-fatal)")


def _refresh_address_cache(base_url, token, company, _step):
    """Fetch CustomerPostalAddresses and upsert into customer_addresses."""
    from data.d365_entities import fetch_customer_postal_addresses
    from webapp.db import upsert_d365_addresses
    try:
        _step("Fetching customer addresses from D365…")
        addr_df = fetch_customer_postal_addresses(base_url, token, company_id=company)
        if not addr_df.empty:
            rows = addr_df.to_dict("records")
            upsert_d365_addresses(rows)
            log.info("Address cache refreshed: %d addresses", len(rows))
        else:
            log.info("Address cache: no addresses returned from D365")
    except Exception:
        log.exception("Address cache refresh failed (non-fatal)")


def _refresh_price_cache(base_url, token, company, _step):
    """Fetch OpenSalesPriceJournalLinesV2 and update the price_cache table."""
    from data.d365_entities import fetch_trade_agreement_prices
    from webapp.db import upsert_price_cache
    try:
        _step("Fetching trade agreement prices from D365…")
        prices_df = fetch_trade_agreement_prices(base_url, token, company_id=company)
        if not prices_df.empty:
            rows = prices_df.to_dict("records")
            upsert_price_cache(rows)
            log.info("Price cache refreshed: %d trade agreements", len(rows))
        else:
            log.info("Price cache: no trade agreements returned from D365")
    except Exception:
        log.exception("Price cache refresh failed (non-fatal)")


def _send_overdue_for_user(email: str, custs: list[dict],
                           *, dry_run: bool = False) -> dict:
    """Generate overdue-customer notifications for a single *email*.

    Returns a dict that always reports counts, plus -- for dry runs --
    the per-customer skip reasons so the diagnostic page can show why
    a notification didn't get created. Real (non-dry) runs only return
    the counts; we don't need the audit trail in the hot path.
    """
    from webapp.db import (
        get_notifications, get_recently_dismissed_accounts,
    )

    excluded = set(get_excluded_customers(email) or [])
    existing_notifs = get_notifications(email, dismissed=False)
    existing_accts = {
        n.get("data", {}).get("customer_account")
        for n in existing_notifs
        if n["type"] == "overdue_customer"
    }
    cooldown_accts = get_recently_dismissed_accounts(email, days=7)

    created = 0
    skipped: list[dict] = []

    for c in custs:
        acct = c["customer_account"]
        if acct in excluded:
            if dry_run:
                skipped.append({"customer_account": acct,
                                "customer_name": c.get("customer_name"),
                                "reason": "excluded"})
            continue
        if acct in existing_accts:
            if dry_run:
                skipped.append({"customer_account": acct,
                                "customer_name": c.get("customer_name"),
                                "reason": "already_has_unread_notification"})
            continue
        if acct in cooldown_accts:
            if dry_run:
                skipped.append({"customer_account": acct,
                                "customer_name": c.get("customer_name"),
                                "reason": "dismissed_within_7_days"})
            continue

        if not dry_run:
            avg = c.get("avg_gap_days") or 0
            days = c.get("days_since_last") or 0
            avg_weeks = round(avg / 7, 1)
            days_weeks = round(days / 7, 1)

            title = f"{c['customer_name'] or acct} is overdue"
            message = (
                f"Usually orders every ~{avg_weeks} weeks, "
                f"but it has been {days_weeks} weeks since their last order."
            )

            add_notification(
                user_email=email,
                ntype="overdue_customer",
                title=title,
                message=message,
                data={"customer_account": acct,
                      "customer_name": c.get("customer_name")},
            )
        created += 1

    return {"created": created, "skipped": skipped,
            "candidate_count": len(custs)}


def _group_overdue_by_sales_group(metrics: list[dict]) -> dict[str, list[dict]]:
    """Bucket overdue customers by their raw sales_group string."""
    by_group: dict[str, list[dict]] = {}
    for m in metrics:
        if m.get("status") != "overdue":
            continue
        sg = m.get("sales_group")
        if sg:
            by_group.setdefault(sg, []).append(m)
    return by_group


def _generate_overdue_notifications(metrics: list[dict]):
    """Create overdue-customer notifications for real app users."""
    from webapp.db import get_users_by_salesman_key, get_all_users

    by_group = _group_overdue_by_sales_group(metrics)
    if not by_group:
        return

    all_users = get_all_users()
    admin_emails = [
        u["email"] for u in all_users
        if u["role"] in ("admin", "developer")
    ]

    all_overdue_custs = []
    for sg_key, custs in by_group.items():
        all_overdue_custs.extend(custs)
        matched_users = get_users_by_salesman_key(sg_key)
        for u in matched_users:
            _send_overdue_for_user(u["email"], custs)

    for admin_email in admin_emails:
        _send_overdue_for_user(admin_email, all_overdue_custs)


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
    new = sum(1 for d in included if d.get("status") == "new")
    active = sum(1 for d in included if d.get("status") == "active")
    overdue = sum(1 for d in included if d.get("status") == "overdue")
    inactive = sum(1 for d in included if d.get("status") == "inactive")

    avg_gaps = [d["avg_gap_days"] for d in included
                if d.get("avg_gap_days") and d["avg_gap_days"] > 0]
    avg_freq = round(sum(avg_gaps) / len(avg_gaps), 1) if avg_gaps else 0

    return {
        "total_customers": total,
        "new": new,
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


# ---------------------------------------------------------------------------
# Runbook history sync (Azure Automation jobs + SharePoint run_log.csv)
# ---------------------------------------------------------------------------

def sync_runbook_history():
    """Download run_log.csv from SharePoint, fetch Azure Automation jobs,
    merge them, and upsert into local DB.

    Azure jobs provide job_id and status but often lack report_name/args for
    schedule-triggered runs.  run_log.csv (written by the runbook itself)
    always has report_name, args, and error.  We match them by timestamp
    proximity and merge the best data from each source.
    """
    from webapp.db import upsert_runbook_history
    from datetime import datetime, timedelta
    import csv
    import io

    azure_jobs: list[dict] = []
    csv_rows_list: list[dict] = []

    # 1) Fetch from Azure Automation job API
    try:
        from webapp.services.azure_automation import list_jobs
        jobs = list_jobs(limit=500)
        for j in jobs:
            start = j.get("start_time") or j.get("creation_time") or ""
            end = j.get("end_time") or ""
            duration = None
            if start and end:
                try:
                    s = datetime.fromisoformat(start)
                    e = datetime.fromisoformat(end)
                    duration = round((e - s).total_seconds(), 1)
                except Exception:
                    pass

            azure_jobs.append({
                "job_id": j.get("job_id", ""),
                "timestamp": start[:19].replace("T", " ") if start else "",
                "report_name": j.get("report_name", ""),
                "status": j.get("status", ""),
                "duration_sec": duration,
                "args": j.get("extra_args", ""),
                "error": j.get("error", ""),
                "runbook_name": j.get("runbook_name", ""),
                "start_time": start,
                "end_time": end,
                "source": "azure_api",
            })
        log.info("Fetched %d jobs from Azure Automation API", len(azure_jobs))
    except Exception:
        log.exception("Failed to fetch Azure Automation jobs")

    # 2) Download run_log.csv from SharePoint
    try:
        from webapp.services.sharepoint import download_file_by_path

        csv_path = "D365 F&O/scripts/logs/run_log.csv"
        csv_bytes = download_file_by_path(csv_path)
        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        for row in reader:
            ts = row.get("timestamp", "").strip()
            rn = row.get("report_name", "").strip()
            status = row.get("status", "").strip()
            if not ts or not rn:
                continue
            if status == "STARTED":
                continue

            def _safe_float(v):
                try:
                    return float(v) if v and v.strip() else None
                except ValueError:
                    return None

            def _safe_int(v):
                try:
                    return int(v) if v and v.strip() else None
                except ValueError:
                    return None

            csv_rows_list.append({
                "timestamp": ts,
                "report_name": rn,
                "status": status,
                "duration_sec": _safe_float(row.get("duration_sec", "")),
                "rows_output": _safe_int(row.get("rows_output", "")),
                "files_uploaded": _safe_int(row.get("files_uploaded", "")),
                "args": row.get("args", "").strip(),
                "error": row.get("error", "").strip(),
            })
        log.info("Parsed %d rows from run_log.csv", len(csv_rows_list))
    except Exception:
        log.exception("Failed to download run_log.csv from SharePoint")

    # 3) Merge: enrich Azure jobs with run_log data by matching timestamps
    #    A CSV row matches an Azure job if the timestamps are within 5 minutes
    #    and the status is compatible.
    MAX_DELTA = timedelta(minutes=5)
    used_csv_indices: set[int] = set()

    def _parse_ts(ts_str: str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(ts_str[:19], fmt)
            except (ValueError, TypeError):
                continue
        return None

    all_rows: list[dict] = []

    for aj in azure_jobs:
        aj_ts = _parse_ts(aj.get("timestamp", ""))
        best_match = None
        best_idx = -1
        best_delta = MAX_DELTA

        if aj_ts:
            for idx, cr in enumerate(csv_rows_list):
                if idx in used_csv_indices:
                    continue
                cr_ts = _parse_ts(cr.get("timestamp", ""))
                if not cr_ts:
                    continue
                delta = abs(aj_ts - cr_ts)
                if delta < best_delta:
                    best_delta = delta
                    best_match = cr
                    best_idx = idx

        merged = dict(aj)
        if best_match and best_idx >= 0:
            used_csv_indices.add(best_idx)
            if not merged.get("report_name"):
                merged["report_name"] = best_match.get("report_name", "")
            if not merged.get("args"):
                merged["args"] = best_match.get("args", "")
            if not merged.get("error"):
                merged["error"] = best_match.get("error", "")
            if not merged.get("duration_sec") and best_match.get("duration_sec"):
                merged["duration_sec"] = best_match["duration_sec"]
            if best_match.get("rows_output"):
                merged["rows_output"] = best_match["rows_output"]
            if best_match.get("files_uploaded"):
                merged["files_uploaded"] = best_match["files_uploaded"]

        all_rows.append(merged)

    # 4) Add unmatched CSV rows (e.g. older history not in Azure job list)
    for idx, cr in enumerate(csv_rows_list):
        if idx in used_csv_indices:
            continue
        all_rows.append({
            "job_id": None,
            "timestamp": cr["timestamp"],
            "report_name": cr["report_name"],
            "status": cr["status"],
            "duration_sec": cr.get("duration_sec"),
            "rows_output": cr.get("rows_output"),
            "files_uploaded": cr.get("files_uploaded"),
            "args": cr.get("args", ""),
            "error": cr.get("error", ""),
            "source": "run_log",
        })

    if all_rows:
        upsert_runbook_history(all_rows)
        log.info("Runbook history sync complete: %d total rows (%d azure, %d csv, %d merged)",
                 len(all_rows), len(azure_jobs), len(csv_rows_list), len(used_csv_indices))
