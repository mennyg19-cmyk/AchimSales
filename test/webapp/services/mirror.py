"""Local SQLite mirror for the on-prem reporting API.

This module is the test app's offline safety net. Whenever the
reporting API succeeds, every row that came back is upserted into a
local SQLite table here. If the API is later unreachable, lookups,
dropdowns, and the Customer's Last Order viewer can keep working from
the mirror with a clear "showing cached data" badge.

Tables:

* ``mirror_customers``      -- full customer master snapshot.
* ``mirror_salesline``      -- order-line rows from salesline_release.
* ``mirror_invoice``        -- invoice rows from invoiced_order_charges.
* ``mirror_sales_header``   -- materialized per-order aggregation
                               rebuilt at the end of every salesline
                               upsert (dashboard hot path).
* ``mirror_refresh_runs``   -- audit trail of every snapshot refresh
                               (manual button or daily 00:00 ET cron).

Retention model (no window):

    The salesline and invoice mirrors *never* delete rows. Every row
    that's ever been upserted is kept forever. There used to be a
    rolling 60-day window that pruned old rows on every refresh; that
    was removed because the dashboard and reports need history back to
    D365 go-live and the cost of carrying ~85k salesline rows in
    SQLite is trivial.

    The "refresh window" you see in :data:`SALESLINE_REFRESH_WINDOW_DAYS`
    and :data:`INVOICE_REFRESH_WINDOW_DAYS` is a *fetch* setting: it's
    how far back the daily cron pulls from the API. Older history is
    loaded once via the admin "Backfill since D365 go-live" job (see
    :mod:`test.webapp.services.mirror_refresh`) and then sits in the
    mirror forever.

Upsert semantics:
    * Match incoming rows on a stable key (CustomerAccount for
      customers, SalesOrderNumber+LineNumber for salesline,
      InvoiceNumber for invoices).
    * If the row exists and the snapshot's data differs from the
      mirror, UPDATE.
    * If the row doesn't exist, INSERT.
    * Rows in the mirror that the API didn't return are LEFT ALONE.

Read-back (fallback) semantics:
    * Customer / salesman lookups: return whatever's in
      ``mirror_customers``.
    * salesline / invoice fallback for the Ordered, Invoiced, and
      Customer's Last Order reports: serve whatever's in the table.
      If the caller asks for a date range starting before the earliest
      row we actually have, raise :class:`MirrorWindowExceeded` so the
      UI can show a plain-English "ask an admin to backfill" message
      instead of silently returning a too-small slice.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from test.webapp.db import connect

log = logging.getLogger(__name__)


# Refresh window for the salesline and invoice mirrors (in days).
#
# This is what the daily cron / dashboard refresh button pulls from the
# API on every run. It is NOT a retention cap -- the mirror keeps every
# row that was ever upserted, forever. A separate admin "Backfill since
# D365 go-live" job populates rows older than this window.
SALESLINE_REFRESH_WINDOW_DAYS = 180
INVOICE_REFRESH_WINDOW_DAYS   = 180

# Back-compat aliases. Callers should migrate to the *_REFRESH_WINDOW_DAYS
# names; these still resolve to the same value.
SALESLINE_WINDOW_DAYS = SALESLINE_REFRESH_WINDOW_DAYS
INVOICE_WINDOW_DAYS   = INVOICE_REFRESH_WINDOW_DAYS


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_MIRROR_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS mirror_customers (
        customer_account TEXT PRIMARY KEY,
        company          TEXT,
        account_num      TEXT,
        customer_name    TEXT,
        cust_group       TEXT,
        currency         TEXT,
        sales_group      TEXT,
        party_state      TEXT,
        markup_group     TEXT,
        dlv_mode         TEXT,
        dlv_term         TEXT,
        invent_site_id   TEXT,
        credit_max       REAL,
        created_at       TEXT,
        raw_json         TEXT NOT NULL,
        first_seen_utc   TEXT NOT NULL,
        last_seen_utc    TEXT NOT NULL,
        row_hash         TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_mirror_customers_sales_group ON mirror_customers(sales_group)",
    "CREATE INDEX IF NOT EXISTS idx_mirror_customers_name ON mirror_customers(customer_name)",
    """
    CREATE TABLE IF NOT EXISTS mirror_salesline (
        sales_order_number TEXT NOT NULL,
        line_number        INTEGER NOT NULL,
        customer_account   TEXT,
        customer_name      TEXT,
        sales_group        TEXT,
        order_date         TEXT,         -- YYYY-MM-DD (Eastern)
        created_datetime   TEXT,         -- raw CreatedDateTime from SP
        po_number          TEXT,
        item_number        TEXT,
        item_name          TEXT,
        unit_price         REAL,
        order_status       TEXT,
        status             TEXT,
        qty_ordered        REAL,
        qty_shipped        REAL,
        qty_cancelled      REAL,
        ordered_dollars    REAL,
        shipped_dollars    REAL,
        cancelled_dollars  REAL,
        raw_json           TEXT NOT NULL,
        first_seen_utc     TEXT NOT NULL,
        last_seen_utc      TEXT NOT NULL,
        row_hash           TEXT NOT NULL,
        keep_forever       INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (sales_order_number, line_number)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_mirror_salesline_customer ON mirror_salesline(customer_account)",
    "CREATE INDEX IF NOT EXISTS idx_mirror_salesline_orderdate ON mirror_salesline(order_date)",
    "CREATE INDEX IF NOT EXISTS idx_mirror_salesline_status ON mirror_salesline(status)",
    # Covers the dashboard's GROUP BY (sales_order_number,
    # customer_account, MAX(order_date)) so SQLite can walk the index
    # in-order instead of full-scanning 86k rows + sorting. Still
    # useful for ad-hoc queries even after mirror_sales_header was
    # added.
    "CREATE INDEX IF NOT EXISTS idx_mirror_salesline_dash "
    "ON mirror_salesline(sales_order_number, customer_account, order_date)",
    # Materialized header aggregation: one row per (order, customer)
    # derived from mirror_salesline. The dashboard queries this table
    # directly, so opening the page is a small table scan over
    # ~5-10k header rows instead of a GROUP BY over 86k line rows.
    # Rebuilt at the end of every salesline upsert.
    """
    CREATE TABLE IF NOT EXISTS mirror_sales_header (
        sales_order_number TEXT NOT NULL,
        customer_account   TEXT NOT NULL,
        customer_name      TEXT,
        sales_group        TEXT,
        order_date         TEXT,
        order_status       TEXT,
        po_number          TEXT,
        line_count         INTEGER NOT NULL DEFAULT 0,
        last_seen_utc      TEXT NOT NULL,
        keep_forever       INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (sales_order_number, customer_account)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_mirror_sales_header_customer ON mirror_sales_header(customer_account)",
    "CREATE INDEX IF NOT EXISTS idx_mirror_sales_header_order_date ON mirror_sales_header(order_date)",
    "CREATE INDEX IF NOT EXISTS idx_mirror_sales_header_sales_group ON mirror_sales_header(sales_group)",
    # Invoiced-order-charges mirror: one row per invoice. Same
    # no-window model as mirror_salesline -- the daily cron pulls the
    # last INVOICE_REFRESH_WINDOW_DAYS days and the admin "Backfill"
    # button covers everything older. raw_json holds the full SP
    # payload so callers reading the mirror see the same shape they'd
    # see from the live endpoint.
    """
    CREATE TABLE IF NOT EXISTS mirror_invoice (
        invoice_number              TEXT NOT NULL PRIMARY KEY,
        invoice_account             TEXT,
        customer_name               TEXT,
        invoice_date                TEXT,          -- YYYY-MM-DD
        sales_order                 TEXT,
        amount                      REAL,
        sh_processing_fees          TEXT,
        sh_processing_fees_charges  REAL,
        sh_freight                  TEXT,
        sh_freight_charges          REAL,
        sh_tariff                   TEXT,
        sh_tariff_charges           REAL,
        sales_group                 TEXT,
        raw_json                    TEXT NOT NULL,
        first_seen_utc              TEXT NOT NULL,
        last_seen_utc               TEXT NOT NULL,
        row_hash                    TEXT NOT NULL,
        keep_forever                INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_mirror_invoice_account ON mirror_invoice(invoice_account)",
    "CREATE INDEX IF NOT EXISTS idx_mirror_invoice_date ON mirror_invoice(invoice_date)",
    "CREATE INDEX IF NOT EXISTS idx_mirror_invoice_sales_group ON mirror_invoice(sales_group)",
    "CREATE INDEX IF NOT EXISTS idx_mirror_invoice_sales_order ON mirror_invoice(sales_order)",
    """
    CREATE TABLE IF NOT EXISTS mirror_refresh_runs (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        scope            TEXT    NOT NULL,    -- 'customers' | 'salesline' | 'piggyback'
        trigger          TEXT    NOT NULL,    -- 'manual' | 'cron' | 'piggyback'
        started_utc      TEXT    NOT NULL,
        finished_utc     TEXT,
        status           TEXT    NOT NULL,    -- 'running' | 'success' | 'failed'
        rows_in          INTEGER,
        rows_inserted    INTEGER,
        rows_updated     INTEGER,
        rows_pruned      INTEGER,
        error_message    TEXT,
        triggered_by     TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_mirror_refresh_runs_started ON mirror_refresh_runs(started_utc DESC)",
    # Precomputed per-customer dashboard metrics. Built once at the
    # end of every salesline upsert (and bootstrapped on first boot)
    # so the dashboard read path is a flat SELECT * with no GROUP BY
    # and no Python aggregation. This is the live app's pattern --
    # the cost of the status/gap math is paid once on refresh, not
    # per-render.
    """
    CREATE TABLE IF NOT EXISTS mirror_dashboard_cache (
        customer_account   TEXT PRIMARY KEY,
        customer_name      TEXT,
        sales_group        TEXT,
        last_order_date    TEXT,
        order_count        INTEGER NOT NULL DEFAULT 0,
        avg_gap_days       REAL,
        gap_stdev          REAL,
        overdue_threshold  REAL,
        days_since_last    INTEGER,
        status             TEXT NOT NULL,
        last_refreshed     TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_mirror_dashboard_cache_status ON mirror_dashboard_cache(status)",
    "CREATE INDEX IF NOT EXISTS idx_mirror_dashboard_cache_sales_group ON mirror_dashboard_cache(sales_group)",
    # Admin "Backfill since D365 go-live" job registry. Has to be in
    # SQLite (not a per-process dict) because gunicorn runs >1 worker:
    # the POST that kicks the job lands on worker A and creates the
    # row; the polling GET load-balances to worker B and reads it.
    # Also survives worker restarts so a mid-run crash doesn't orphan
    # a job the admin is still watching.
    """
    CREATE TABLE IF NOT EXISTS mirror_backfill_jobs (
        job_id        TEXT PRIMARY KEY,
        scope         TEXT NOT NULL,
        state         TEXT NOT NULL,       -- 'running' | 'done' | 'failed'
        started_utc   TEXT NOT NULL,
        finished_utc  TEXT,
        triggered_by  TEXT,
        chunks_done   INTEGER NOT NULL DEFAULT 0,
        chunks_total  INTEGER NOT NULL DEFAULT 0,
        rows_in       INTEGER NOT NULL DEFAULT 0,
        current_json  TEXT,
        errors_json   TEXT NOT NULL DEFAULT '[]',
        result_json   TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_mirror_backfill_jobs_started ON mirror_backfill_jobs(started_utc DESC)",
]


_init_lock = threading.Lock()
_init_done = False

_MIRROR_COLUMN_MIGRATIONS = [
    ("mirror_salesline", "order_status", "TEXT"),
    ("mirror_salesline", "created_datetime", "TEXT"),
    # keep_forever = 1 means "this row was inserted by the
    # last-order-per-customer backfill; do not prune even if it's
    # outside the rolling window".
    ("mirror_salesline", "keep_forever", "INTEGER NOT NULL DEFAULT 0"),
]


def init_mirror_db() -> None:
    """Idempotent: ensure mirror tables exist. Safe on every boot.

    Wrapped in :func:`test.webapp.db._retry_transient_db` so a stale
    SMB write lease or a brief lock from another worker doesn't crash
    boot. See the 2026-05-19 incident notes in db.py.
    """
    global _init_done
    from test.webapp.db import _retry_transient_db

    def _do_init() -> None:
        with connect() as conn:
            for stmt in _MIRROR_SCHEMA:
                conn.execute(stmt)
            _ensure_mirror_columns(conn)
            # One-time bootstrap of the materialized header table.
            # On the first boot after the header-table change,
            # mirror_salesline already has 86k rows but
            # mirror_sales_header is empty -- meaning the dashboard
            # would render blank until the next manual refresh.
            # Populate it from the existing lines so the dashboard
            # has its data immediately.
            try:
                header_empty = conn.execute(
                    "SELECT 1 FROM mirror_sales_header LIMIT 1"
                ).fetchone() is None
                salesline_has_rows = conn.execute(
                    "SELECT 1 FROM mirror_salesline LIMIT 1"
                ).fetchone() is not None
                if header_empty and salesline_has_rows:
                    rebuilt = _rebuild_sales_header(conn)
                    log.info(
                        "mirror_sales_header bootstrapped from existing "
                        "mirror_salesline: %d header rows", rebuilt,
                    )
            except Exception:
                log.warning("header bootstrap failed (non-fatal)", exc_info=True)
            # Bootstrap mirror_dashboard_cache on the first boot after
            # the schema landed (empty cache + existing data). Without
            # this the dashboard render would hit an empty table until
            # the next refresh.
            try:
                cache_empty = conn.execute(
                    "SELECT 1 FROM mirror_dashboard_cache LIMIT 1"
                ).fetchone() is None
                customers_have_rows = conn.execute(
                    "SELECT 1 FROM mirror_customers LIMIT 1"
                ).fetchone() is not None
                if cache_empty and customers_have_rows:
                    rebuilt = _rebuild_dashboard_cache(conn)
                    log.info(
                        "mirror_dashboard_cache bootstrapped: %d customer rows",
                        rebuilt,
                    )
            except Exception:
                log.warning("dashboard cache bootstrap failed (non-fatal)", exc_info=True)
            # Refresh sqlite_stat1 so the planner picks the right
            # index for each table after any schema/data changes. If
            # ANALYZE itself reports "database disk image is malformed"
            # we treat sqlite_stat1 as corrupt (it's a hint table, not
            # data) and rebuild it from scratch -- this clears the
            # malformed-stats warnings that linger after an OOM kill.
            try:
                conn.execute("ANALYZE")
            except sqlite3.DatabaseError as exc:
                if "malformed" in str(exc).lower():
                    log.warning(
                        "ANALYZE reported malformed sqlite_stat1; "
                        "rebuilding stats from scratch"
                    )
                    try:
                        conn.execute("DROP TABLE IF EXISTS sqlite_stat1")
                        conn.execute("DROP TABLE IF EXISTS sqlite_stat4")
                        conn.execute("ANALYZE")
                        log.info("sqlite_stat1 rebuilt cleanly")
                    except Exception:
                        log.warning("stat1 rebuild also failed (non-fatal)", exc_info=True)
                else:
                    log.warning("ANALYZE failed (non-fatal)", exc_info=True)
            except Exception:
                log.warning("ANALYZE failed (non-fatal)", exc_info=True)

    with _init_lock:
        if _init_done:
            return
        _retry_transient_db("init_mirror_db", _do_init)
        _init_done = True
    log.info("mirror tables ready")


def _ensure_mirror_columns(conn) -> None:
    for table, column, coldef in _MIRROR_COLUMN_MIGRATIONS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")
            log.info("%s: added %s column", table, column)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MirrorWindowExceeded(RuntimeError):
    """Raised when a fallback request asks for data older than the
    mirror window. Caller is expected to show this verbatim to the user.
    """


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_row(payload: dict) -> str:
    """Stable digest of the payload so we can skip writes when the row
    hasn't changed. (Hashing is much cheaper than writing.)"""
    import hashlib
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def _to_float(v: Any) -> float | None:
    if v in (None, "", "NULL"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    if v in (None, "", "NULL"):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_str(v: Any) -> str:
    if v in (None, "NULL"):
        return ""
    return str(v).strip()


def _customer_account(v: Any) -> str:
    return _to_str(v).upper()


def _date_only(v: Any) -> str:
    """Extract a canonical YYYY-MM-DD string from a variety of date
    formats. Returns "" if the value can't be parsed -- callers MUST
    treat empty as "skip this row" rather than storing garbage.

    Handles:
        * ISO 8601 / SQL: "2024-05-01", "2024-05-01T00:00:00", "2024-05-01 00:00:00..."
        * US dates:       "5/1/2024", "05/01/24", "20240501"
        * .NET / OData:   "/Date(1714521600000)/"
        * HTTP / RFC-822: "Fri, 01 May 2024 00:00:00 GMT" (.NET's default
                           DateTime.ToString("R") and what some reporting
                           APIs hand back through JSON)
    """
    s = _to_str(v)
    if not s:
        return ""

    head = s[:10]
    try:
        return datetime.strptime(head, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass

    token = s.split()[0]
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y%m%d"):
        try:
            return datetime.strptime(token, fmt).date().isoformat()
        except ValueError:
            continue

    # RFC-822 / HTTP-date: "Fri, 01 May 2024 00:00:00 GMT"
    # Accept both 4- and 2-digit years, and skip the optional weekday.
    rfc_candidates = (
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S",
        "%a, %d %b %Y",
        "%d %b %Y %H:%M:%S %Z",
        "%d %b %Y %H:%M:%S",
        "%d %b %Y",
    )
    for fmt in rfc_candidates:
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue

    # .NET "/Date(epoch_ms)/" form.
    if s.startswith("/Date(") and s.endswith(")/"):
        try:
            epoch_ms = int(s[6:-2].split("+")[0].split("-")[0])
            return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).date().isoformat()
        except (ValueError, OverflowError, OSError):
            pass

    return ""


def _key_id(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _first(raw: dict, *keys: str) -> Any:
    """Return first non-empty value, accepting case/punctuation variants."""
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", "NULL"):
            return value
    casefold = {str(k).lower(): v for k, v in raw.items()}
    for key in keys:
        value = casefold.get(str(key).lower())
        if value not in (None, "", "NULL"):
            return value
    normalized = {_key_id(k): v for k, v in raw.items()}
    for key in keys:
        value = normalized.get(_key_id(key))
        if value not in (None, "", "NULL"):
            return value
    return None


def _within_window(date_str: str, days: int) -> bool:
    """``date_str`` is YYYY-MM-DD. True iff within the past *days* days."""
    if not date_str:
        return False
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return False
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    return d >= cutoff


def _parse_date(date_str: str) -> date | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Customer master upsert
# ---------------------------------------------------------------------------


def _normalize_customer_row(raw: dict) -> dict:
    """Pull the columns we care about out of an SP customer-master row."""
    acct = _customer_account(raw.get("CustomerAccount") or raw.get("AccountNum"))
    return {
        "customer_account": acct,
        "company":          _to_str(raw.get("Company")),
        "account_num":      _customer_account(raw.get("AccountNum")) or acct,
        "customer_name":    _to_str(raw.get("CustomerName")),
        "cust_group":       _to_str(raw.get("CustGroup")),
        "currency":         _to_str(raw.get("Currency")),
        "sales_group":      _to_str(raw.get("SalesGroup")),
        "party_state":      _to_str(raw.get("PartyState")),
        "markup_group":     _to_str(raw.get("MarkupGroup")),
        "dlv_mode":         _to_str(raw.get("DlvMode")),
        "dlv_term":         _to_str(raw.get("DlvTerm")),
        "invent_site_id":   _to_str(raw.get("InventSiteId")),
        "credit_max":       _to_float(raw.get("CreditMax")),
        "created_at":       _to_str(raw.get("CreatedDateTime")),
    }


def upsert_customers(rows: Iterable[dict], *, trigger: str = "piggyback",
                     triggered_by: str | None = None,
                     rebuild_dashboard_cache: bool = True) -> dict[str, int]:
    """Mirror a batch of customer-master rows.

    Returns ``{rows_in, inserted, updated, unchanged}`` for logging.
    """
    init_mirror_db()
    rows = list(rows or [])
    run_id = _start_refresh_run(scope="customers", trigger=trigger,
                                triggered_by=triggered_by)

    inserted = updated = unchanged = 0
    now = _utcnow()
    err: str | None = None
    try:
        with connect() as conn:
            for raw in rows:
                norm = _normalize_customer_row(raw)
                if not norm["customer_account"]:
                    continue
                row_hash = _hash_row(norm)
                existing = conn.execute(
                    "SELECT row_hash FROM mirror_customers WHERE customer_account = ?",
                    (norm["customer_account"],),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO mirror_customers (
                            customer_account, company, account_num, customer_name,
                            cust_group, currency, sales_group, party_state,
                            markup_group, dlv_mode, dlv_term, invent_site_id,
                            credit_max, created_at, raw_json,
                            first_seen_utc, last_seen_utc, row_hash
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            norm["customer_account"], norm["company"],
                            norm["account_num"], norm["customer_name"],
                            norm["cust_group"], norm["currency"],
                            norm["sales_group"], norm["party_state"],
                            norm["markup_group"], norm["dlv_mode"],
                            norm["dlv_term"], norm["invent_site_id"],
                            norm["credit_max"], norm["created_at"],
                            json.dumps(raw, default=str),
                            now, now, row_hash,
                        ),
                    )
                    inserted += 1
                elif existing["row_hash"] != row_hash:
                    conn.execute(
                        """
                        UPDATE mirror_customers SET
                            company=?, account_num=?, customer_name=?,
                            cust_group=?, currency=?, sales_group=?, party_state=?,
                            markup_group=?, dlv_mode=?, dlv_term=?, invent_site_id=?,
                            credit_max=?, created_at=?, raw_json=?,
                            last_seen_utc=?, row_hash=?
                        WHERE customer_account = ?
                        """,
                        (
                            norm["company"], norm["account_num"],
                            norm["customer_name"], norm["cust_group"],
                            norm["currency"], norm["sales_group"],
                            norm["party_state"], norm["markup_group"],
                            norm["dlv_mode"], norm["dlv_term"],
                            norm["invent_site_id"], norm["credit_max"],
                            norm["created_at"], json.dumps(raw, default=str),
                            now, row_hash, norm["customer_account"],
                        ),
                    )
                    updated += 1
                else:
                    conn.execute(
                        "UPDATE mirror_customers SET last_seen_utc=? WHERE customer_account=?",
                        (now, norm["customer_account"]),
                    )
                    unchanged += 1
            # Rebuild the dashboard cache so customer-master changes
            # (new accounts, renames, sales-group reassignments) show
            # up on the dashboard without waiting for the next
            # salesline refresh. Chunked refresh paths skip this and
            # call ``rebuild_dashboard_cache_now()`` once at the end.
            if rebuild_dashboard_cache and (inserted or updated):
                try:
                    cache_rows = _rebuild_dashboard_cache(conn)
                    log.info(
                        "mirror_dashboard_cache rebuilt after customer upsert: %d rows",
                        cache_rows,
                    )
                except Exception:
                    log.exception("dashboard cache rebuild failed (non-fatal)")
    except Exception as exc:
        err = str(exc)
        log.exception("upsert_customers failed")
    finally:
        _finish_refresh_run(
            run_id,
            status="failed" if err else "success",
            rows_in=len(rows),
            rows_inserted=inserted,
            rows_updated=updated,
            error_message=err,
        )

    return {
        "rows_in":   len(rows),
        "inserted":  inserted,
        "updated":   updated,
        "unchanged": unchanged,
    }


# ---------------------------------------------------------------------------
# Salesline upsert
# ---------------------------------------------------------------------------


def _normalize_salesline_row(raw: dict) -> dict:
    """Pull the columns we care about out of an SP salesline_release row."""
    so = _to_str(_first(raw, "SalesOrderNumber", "SalesId", "OrderNumber", "OrderNo"))
    ln = _to_int(_first(raw, "LineNumber", "LineNum", "LineNo")) or 0
    created_datetime = _to_str(_first(raw, "CreatedDateTime", "OrderCreationDateTime", "OrderDate"))
    # The ordered endpoint is filtered by CreatedDateTimeFrom/To. Use that
    # same date as the mirror window date so a valid 60-day API response is
    # not rejected just because the sales order's business OrderDate is older.
    order_date = _date_only(_first(
        raw,
        "CreatedDateTime",
        "OrderCreationDateTime",
        "OrderDate",
        "ShippingDateRequested",
        "RequestedShipDate",
        "ReceiptDateRequested",
        "RequestedReceiptDate",
    ))
    return {
        "sales_order_number": so,
        "line_number":        ln,
        "customer_account":   _customer_account(_first(raw, "CustomerAccount", "AccountNum")),
        "customer_name":      _to_str(_first(raw, "customername", "CustomerName", "Name")),
        "sales_group":        _to_str(_first(raw, "SalesGroup", "salesgroup", "Salesman")),
        "order_date":         order_date,
        "created_datetime":   created_datetime,
        "po_number":          _to_str(_first(raw, "CustomerRequisition", "CustomerReq", "PONumber", "PO #")),
        "item_number":        _to_str(_first(raw, "Item", "ItemId", "ItemNumber", "Item#")),
        "item_name":          _to_str(_first(raw, "ItemDescription", "ItemName", "LineDescription")),
        "unit_price":         _to_float(_first(raw, "SalesPrice", "UnitPrice")),
        "order_status":       _to_str(_first(raw, "OrderStatus", "orderstatus", "HeaderStatus")),
        "status":             _to_str(_first(raw, "SalesStatus", "Status")),
        "qty_ordered":        _to_float(_first(raw, "QuantityOrdered", "QtyOrdered")),
        "qty_shipped":        _to_float(_first(raw, "QuantityShipped", "QtyShipped")),
        "qty_cancelled":      _to_float(_first(raw, "QuantityCancelled", "QtyCancelled")),
        "ordered_dollars":    _to_float(_first(raw, "Ordered $", "OrderedDollars", "OrderedAmount")),
        "shipped_dollars":    _to_float(_first(raw, "Shipped $", "ShippedDollars", "ShippedAmount")),
        "cancelled_dollars":  _to_float(_first(raw, "Cancelled $", "CancelledDollars", "CancelledAmount")),
    }


def _is_malformed_db_error(exc: BaseException) -> bool:
    return (
        isinstance(exc, sqlite3.DatabaseError)
        and "malformed" in str(exc).lower()
    )


def _recreate_aggregation_table(conn, table_name: str) -> None:
    """Drop and re-create a derived table from ``_MIRROR_SCHEMA``.

    Used as the recovery path when an aggregation table reports
    ``database disk image is malformed`` (we hit this after the
    2026-05-19 OOM kill corrupted materialized pages on
    ``mirror_sales_header`` and ``mirror_dashboard_cache``). Both
    tables are derived from ``mirror_salesline`` + ``mirror_customers``,
    so dropping them loses no source data -- the caller rebuilds the
    contents immediately after.
    """
    log.warning("%s malformed -- dropping and recreating from schema", table_name)
    conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    for stmt in _MIRROR_SCHEMA:
        if table_name in stmt and ("CREATE TABLE" in stmt or "CREATE INDEX" in stmt):
            try:
                conn.execute(stmt)
            except Exception:
                log.warning("recreating %s DDL failed (non-fatal): %s",
                            table_name, stmt.split("\n")[0], exc_info=True)


def _rebuild_sales_header(conn) -> int:
    """Recompute mirror_sales_header from the current mirror_salesline.

    Run inside an existing connection / transaction (so it's atomic
    with whatever salesline mutations just happened). Returns the
    number of header rows written.

    The implementation deliberately rebuilds the whole table rather
    than trying to update individual headers per-line. SQLite can
    chew through a 86k-row GROUP-BY into a 5-10k-row INSERT in
    well under a second, and rebuilding-from-scratch removes any
    chance of drift between the line table and the header
    aggregation.

    If the existing table is corrupt (``database disk image is
    malformed``) we drop and recreate it once, then continue. The
    underlying salesline data is untouched.
    """
    try:
        conn.execute("DELETE FROM mirror_sales_header")
    except sqlite3.DatabaseError as exc:
        if not _is_malformed_db_error(exc):
            raise
        _recreate_aggregation_table(conn, "mirror_sales_header")
    cur = conn.execute(
        """
        INSERT INTO mirror_sales_header (
            sales_order_number,
            customer_account,
            customer_name,
            sales_group,
            order_date,
            order_status,
            po_number,
            line_count,
            last_seen_utc,
            keep_forever
        )
        SELECT
            sales_order_number,
            customer_account,
            MAX(customer_name),
            MAX(sales_group),
            MAX(order_date),
            MAX(order_status),
            MAX(po_number),
            COUNT(*),
            MAX(last_seen_utc),
            MAX(keep_forever)
        FROM mirror_salesline
        WHERE sales_order_number IS NOT NULL
          AND sales_order_number <> ''
          AND customer_account IS NOT NULL
          AND customer_account <> ''
        GROUP BY sales_order_number, customer_account
        """
    )
    return cur.rowcount or 0


def _rebuild_dashboard_cache(conn) -> int:
    """Recompute ``mirror_dashboard_cache`` from customers + sales header.

    Runs inside an existing connection so it's atomic with whatever
    salesline mutation just happened. Pays the per-customer cadence
    math (mean gap, stdev, overdue threshold, status) once and stores
    the result so the dashboard read path is a flat ``SELECT *``
    instead of a 2,500-customer Python aggregation per render.

    Status definitions match the original app's
    ``webapp.dashboard_data._compute_customer_metrics`` exactly. Keep
    them in lock-step or the test dashboard's bucket counts will
    diverge from the live one:

    * ``new``      -- no orders in the mirror, OR exactly one distinct
                      order, OR multiple orders all on the same day
                      (no real cadence to learn from).
    * ``active``   -- 2+ orders with a real cadence, latest within
                      ``mean_gap + stdev`` AND within the last 365 days.
    * ``overdue``  -- 2+ orders with a real cadence, latest beyond
                      ``mean_gap + stdev`` but <= 365 days old.
    * ``inactive`` -- 2+ orders with a real cadence, latest > 365 days
                      old.
    """
    import math
    from core.dates import get_today_eastern

    today = get_today_eastern()
    now = _utcnow()

    customers: dict[str, dict] = {}

    for row in conn.execute(
        "SELECT customer_account, customer_name, sales_group FROM mirror_customers"
    ):
        acct = (row["customer_account"] or "").strip().upper()
        if not acct:
            continue
        customers[acct] = {
            "customer_account": acct,
            "customer_name":    (row["customer_name"] or "").strip() or acct,
            "sales_group":      (row["sales_group"] or "").strip(),
            "dates":            [],
        }

    # Distinct order-date list per customer in one SQL pass.
    # mirror_sales_header already has at most one date per order so
    # GROUP_CONCAT(order_date) is the customer's order-date history.
    for row in conn.execute(
        """
        SELECT customer_account,
               MAX(customer_name)       AS customer_name,
               MAX(sales_group)         AS sales_group,
               GROUP_CONCAT(order_date) AS dates_csv
        FROM mirror_sales_header
        WHERE customer_account IS NOT NULL
          AND customer_account <> ''
          AND order_date IS NOT NULL
          AND order_date <> ''
        GROUP BY customer_account
        """
    ):
        acct = (row["customer_account"] or "").strip().upper()
        if not acct:
            continue
        dates = [d.strip() for d in (row["dates_csv"] or "").split(",") if d.strip()]
        existing = customers.get(acct)
        if existing:
            existing["dates"] = dates
        else:
            customers[acct] = {
                "customer_account": acct,
                "customer_name":    (row["customer_name"] or "").strip() or acct,
                "sales_group":      (row["sales_group"] or "").strip(),
                "dates":            dates,
            }

    rows_out: list[tuple] = []
    for cust in customers.values():
        parsed: list[date] = []
        for raw in cust["dates"]:
            try:
                parsed.append(date.fromisoformat(raw[:10]))
            except (ValueError, TypeError):
                continue
        parsed.sort()
        order_count = len(parsed)
        last_order = parsed[-1].isoformat() if parsed else None
        days_since = (today - parsed[-1]).days if parsed else None
        avg_gap: float | None = None
        stdev: float | None = None
        threshold: float | None = None
        # Default matches the live app: a customer with no order history
        # in the mirror is treated as "new", not "inactive".
        status = "new"
        if parsed and len(parsed) >= 2:
            gaps = [(parsed[i + 1] - parsed[i]).days for i in range(len(parsed) - 1)]
            gaps = [g for g in gaps if g > 0]
            if gaps:
                avg_gap = sum(gaps) / len(gaps)
                variance = sum((g - avg_gap) ** 2 for g in gaps) / len(gaps)
                stdev = math.sqrt(variance)
                threshold = avg_gap + stdev
                if days_since is not None and days_since > 365:
                    status = "inactive"
                elif days_since is not None and days_since > threshold:
                    status = "overdue"
                else:
                    status = "active"
            # else: all orders on the same day -> no cadence to learn,
            # leave status="new" to match the live app.
        rows_out.append((
            cust["customer_account"],
            cust["customer_name"],
            cust["sales_group"],
            last_order,
            order_count,
            round(avg_gap, 1)   if avg_gap   is not None else None,
            round(stdev, 1)     if stdev     is not None else None,
            round(threshold, 1) if threshold is not None else None,
            days_since,
            status,
            now,
        ))

    try:
        conn.execute("DELETE FROM mirror_dashboard_cache")
    except sqlite3.DatabaseError as exc:
        if not _is_malformed_db_error(exc):
            raise
        _recreate_aggregation_table(conn, "mirror_dashboard_cache")
    conn.executemany(
        """
        INSERT INTO mirror_dashboard_cache (
            customer_account, customer_name, sales_group,
            last_order_date, order_count, avg_gap_days, gap_stdev,
            overdue_threshold, days_since_last, status, last_refreshed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows_out,
    )
    return len(rows_out)


def rebuild_dashboard_cache_now() -> int:
    """Rebuild ``mirror_dashboard_cache`` from current data.

    Public entry-point for callers that batched many salesline /
    customer upserts with ``rebuild_dashboard_cache=False`` and now
    want a single rebuild at the end. Also runs ``PRAGMA
    wal_checkpoint(PASSIVE)`` so the WAL doesn't keep growing across
    a long-running backfill.
    """
    init_mirror_db()
    with connect() as conn:
        rows = _rebuild_dashboard_cache(conn)
        try:
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception:
            log.warning("checkpoint after dashboard rebuild failed (non-fatal)",
                        exc_info=True)
    log.info("mirror_dashboard_cache rebuilt (deferred): %d rows", rows)
    return rows


def checkpoint_wal(*, label: str = "manual") -> None:
    """Flush WAL pages back to the main DB file.

    Called between chunks of a long backfill so the WAL never grows
    big enough that an OOM mid-write leaves an unrecoverable journal.
    Uses ``PASSIVE`` (won't block readers/writers); if the WAL is
    still busy we'll catch it on the next chunk boundary.
    """
    init_mirror_db()
    try:
        with connect() as conn:
            r = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        log.info("wal_checkpoint(%s): busy=%s log_pages=%s checkpointed=%s",
                 label, r[0] if r else "?", r[1] if r else "?", r[2] if r else "?")
    except Exception:
        log.warning("wal_checkpoint(%s) failed (non-fatal)", label, exc_info=True)


def upsert_salesline(rows: Iterable[dict], *, trigger: str = "piggyback",
                     prune_window_days: int | None = None,
                     triggered_by: str | None = None,
                     keep_forever: bool = False,
                     rebuild_dashboard_cache: bool = True) -> dict[str, int]:
    """Mirror a batch of salesline_release rows.

    Every well-formed row (has a sales order number and a parseable
    order date) is stored as-is and kept forever. There is no retention
    window: a daily cron pulls the last
    ``SALESLINE_REFRESH_WINDOW_DAYS`` days and an admin can run a
    "backfill since D365 go-live" job to populate older rows. The
    ``prune_window_days`` argument is accepted for back-compat with
    older callers but is ignored.
    """
    del prune_window_days  # kept in the signature for back-compat only
    init_mirror_db()
    rows = list(rows or [])
    run_id = _start_refresh_run(scope="salesline", trigger=trigger,
                                triggered_by=triggered_by)

    inserted = updated = unchanged = pruned = 0
    skipped_missing_order = skipped_missing_date = skipped_outside_window = 0
    row_errors = 0
    now = _utcnow()
    err: str | None = None
    # Commit every N rows so the writer lock isn't held for the full
    # 85k-row ingest. Without this, any other write on the DB --
    # mark_refresh_requested() from a page render, a piggyback upsert
    # from a report run, etc. -- has to wait for the entire ingest
    # to finish, which produces 25+ second page hangs on slow disks.
    _COMMIT_BATCH = 2000
    pending = 0
    t_start = time.monotonic()
    try:
        with connect() as conn:
            for raw in rows:
                # Defensive per-row try/except: previously a single
                # malformed row (or a transient SQLite lock on a
                # single SELECT) would raise out of the whole loop and
                # leave the stats dict showing "0 inserted, 0 updated,
                # 0 unchanged, 0 skipped" for 80k+ input rows. Now bad
                # rows are counted and the rest of the batch keeps
                # going.
                try:
                    norm = _normalize_salesline_row(raw)
                    if not norm["sales_order_number"]:
                        skipped_missing_order += 1
                        continue
                    if not norm["order_date"]:
                        skipped_missing_date += 1
                        continue
                    # The mirror has no retention window: every well-
                    # formed row is kept forever. Older data is loaded
                    # via the admin "Backfill since D365 go-live" job.
                    row_hash = _hash_row(norm)
                    existing = conn.execute(
                        "SELECT row_hash FROM mirror_salesline "
                        "WHERE sales_order_number=? AND line_number=?",
                        (norm["sales_order_number"], norm["line_number"]),
                    ).fetchone()
                    kf = 1 if keep_forever else 0
                    if existing is None:
                        conn.execute(
                            """
                            INSERT INTO mirror_salesline (
                                sales_order_number, line_number, customer_account,
                                customer_name, sales_group, order_date, created_datetime,
                                po_number, item_number, item_name, unit_price,
                                order_status, status, qty_ordered, qty_shipped, qty_cancelled,
                                ordered_dollars, shipped_dollars, cancelled_dollars,
                                raw_json, first_seen_utc, last_seen_utc, row_hash,
                                keep_forever
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                norm["sales_order_number"], norm["line_number"],
                                norm["customer_account"], norm["customer_name"],
                                norm["sales_group"], norm["order_date"],
                                norm["created_datetime"], norm["po_number"],
                                norm["item_number"], norm["item_name"],
                                norm["unit_price"], norm["order_status"],
                                norm["status"], norm["qty_ordered"], norm["qty_shipped"],
                                norm["qty_cancelled"], norm["ordered_dollars"],
                                norm["shipped_dollars"], norm["cancelled_dollars"],
                                json.dumps(raw, default=str), now, now, row_hash, kf,
                            ),
                        )
                        inserted += 1
                    elif existing["row_hash"] != row_hash:
                        # Never *clear* keep_forever in an update --
                        # once a row is pinned, leave it pinned. Pin it
                        # now if this batch is a backfill batch.
                        conn.execute(
                            """
                            UPDATE mirror_salesline SET
                                customer_account=?, customer_name=?, sales_group=?,
                                order_date=?, created_datetime=?, po_number=?,
                                item_number=?, item_name=?, unit_price=?,
                                order_status=?, status=?, qty_ordered=?, qty_shipped=?, qty_cancelled=?,
                                ordered_dollars=?, shipped_dollars=?, cancelled_dollars=?,
                                raw_json=?, last_seen_utc=?, row_hash=?,
                                keep_forever = MAX(keep_forever, ?)
                            WHERE sales_order_number=? AND line_number=?
                            """,
                            (
                                norm["customer_account"], norm["customer_name"],
                                norm["sales_group"], norm["order_date"],
                                norm["created_datetime"], norm["po_number"],
                                norm["item_number"], norm["item_name"],
                                norm["unit_price"], norm["order_status"],
                                norm["status"], norm["qty_ordered"], norm["qty_shipped"],
                                norm["qty_cancelled"], norm["ordered_dollars"],
                                norm["shipped_dollars"], norm["cancelled_dollars"],
                                json.dumps(raw, default=str), now, row_hash, kf,
                                norm["sales_order_number"], norm["line_number"],
                            ),
                        )
                        updated += 1
                    else:
                        conn.execute(
                            "UPDATE mirror_salesline SET last_seen_utc=?, "
                            "keep_forever = MAX(keep_forever, ?) "
                            "WHERE sales_order_number=? AND line_number=?",
                            (now, kf, norm["sales_order_number"], norm["line_number"]),
                        )
                        unchanged += 1

                    pending += 1
                    if pending >= _COMMIT_BATCH:
                        conn.commit()
                        pending = 0
                except Exception:
                    row_errors += 1
                    if row_errors <= 5:
                        log.exception(
                            "upsert_salesline: row failed (so=%r ln=%r)",
                            (raw or {}).get("SalesOrderNumber"),
                            (raw or {}).get("LineNumber"),
                        )
                    elif row_errors == 6:
                        log.warning(
                            "upsert_salesline: further per-row errors will be "
                            "counted but not logged"
                        )

            # Rebuild the materialized header aggregation. Doing this
            # once at the end of the salesline upsert collapses the
            # dashboard's hottest query from a GROUP BY over ~86k
            # line rows into a small table scan over ~5-10k header
            # rows. It also keeps callers (the dashboard, customer
            # detail, last-order) on a single source of truth.
            _rebuild_sales_header(conn)
            # Optionally rebuild the per-customer dashboard cache from
            # the fresh headers. Chunked refresh paths set this False
            # and call ``rebuild_dashboard_cache_now()`` exactly once
            # after the last chunk -- rebuilding after every chunk
            # used to load ~2,500 customers + every order date into
            # Python on each call and was the OOM trigger on B1.
            if rebuild_dashboard_cache:
                try:
                    cache_rows = _rebuild_dashboard_cache(conn)
                    log.info("mirror_dashboard_cache rebuilt: %d customer rows", cache_rows)
                except Exception:
                    log.exception("dashboard cache rebuild failed (non-fatal)")
    except Exception as exc:
        err = str(exc)
        log.exception("upsert_salesline failed")
    finally:
        _finish_refresh_run(
            run_id,
            status="failed" if err else "success",
            rows_in=len(rows),
            rows_inserted=inserted,
            rows_updated=updated,
            rows_pruned=pruned,
            error_message=err,
        )

    log.info(
        "upsert_salesline: rows_in=%d inserted=%d updated=%d unchanged=%d "
        "skipped_missing_order=%d skipped_missing_date=%d row_errors=%d "
        "pruned=%d duration=%.2fs",
        len(rows), inserted, updated, unchanged,
        skipped_missing_order, skipped_missing_date, row_errors,
        pruned, time.monotonic() - t_start,
    )

    return {
        "rows_in":                 len(rows),
        "inserted":                inserted,
        "updated":                 updated,
        "unchanged":               unchanged,
        "pruned":                  pruned,
        "skipped_missing_order":   skipped_missing_order,
        "skipped_missing_date":    skipped_missing_date,
        "skipped_outside_window":  skipped_outside_window,
        "row_errors":              row_errors,
    }


# ---------------------------------------------------------------------------
# Invoice upsert
# ---------------------------------------------------------------------------


def _normalize_invoice_row(raw: dict) -> dict:
    """Pull the columns we care about out of an invoiced_order_charges row."""
    invoice_no = _to_str(_first(raw, "Invoice", "InvoiceNumber", "InvoiceNo"))
    return {
        "invoice_number":             invoice_no,
        "invoice_account":            _customer_account(
            _first(raw, "InvoiceAccount", "CustomerAccount", "AccountNum")
        ),
        "customer_name":              _to_str(
            _first(raw, "CustomerName", "customername", "Name")
        ),
        "invoice_date":               _date_only(
            _first(raw, "InvoiceDate", "Invoice Date", "DocumentDate")
        ),
        "sales_order":                _to_str(
            _first(raw, "SalesOrder", "SalesOrderNumber", "SalesId")
        ),
        "amount":                     _to_float(
            _first(raw, "Amount", "SubTotal", "SubTotalAmount")
        ),
        "sh_processing_fees":         _to_str(
            _first(raw, "SH_ProcessingFees", "ProcessingFees")
        ),
        "sh_processing_fees_charges": _to_float(
            _first(raw, "SH_ProcessingFeesCharges", "ProcessingFeesCharges",
                   "CCCharges", "CC Charges")
        ),
        "sh_freight":                 _to_str(
            _first(raw, "SH_Freight", "Freight")
        ),
        "sh_freight_charges":         _to_float(
            _first(raw, "SH_FreightCharges", "FreightCharges", "Freight Charges")
        ),
        "sh_tariff":                  _to_str(
            _first(raw, "SH_Tariff", "Tariff")
        ),
        "sh_tariff_charges":          _to_float(
            _first(raw, "SH_TariffCharges", "TariffCharges", "Tariff Charges")
        ),
        "sales_group":                _to_str(
            _first(raw, "SalesGroup", "salesgroup", "Salesman")
        ),
    }


def upsert_invoice(rows: Iterable[dict], *, trigger: str = "piggyback",
                   prune_window_days: int | None = None,
                   triggered_by: str | None = None,
                   keep_forever: bool = False) -> dict[str, int]:
    """Mirror a batch of invoiced_order_charges rows.

    Same shape as :func:`upsert_salesline`: every well-formed row (has
    an invoice number and a parseable invoice date) is stored and kept
    forever. The daily cron pulls the last
    ``INVOICE_REFRESH_WINDOW_DAYS`` days and an admin can run a
    "backfill since D365 go-live" job to populate older rows.
    ``prune_window_days`` is accepted for back-compat with older
    callers but is ignored.
    """
    del prune_window_days  # kept in the signature for back-compat only
    init_mirror_db()
    rows = list(rows or [])
    run_id = _start_refresh_run(scope="invoice", trigger=trigger,
                                triggered_by=triggered_by)

    inserted = updated = unchanged = pruned = 0
    skipped_missing_invoice = skipped_missing_date = 0
    row_errors = 0
    now = _utcnow()
    err: str | None = None
    _COMMIT_BATCH = 2000
    pending = 0
    t_start = time.monotonic()
    try:
        with connect() as conn:
            for raw in rows:
                try:
                    norm = _normalize_invoice_row(raw)
                    if not norm["invoice_number"]:
                        skipped_missing_invoice += 1
                        continue
                    if not norm["invoice_date"]:
                        skipped_missing_date += 1
                        continue
                    row_hash = _hash_row(norm)
                    existing = conn.execute(
                        "SELECT row_hash FROM mirror_invoice "
                        "WHERE invoice_number = ?",
                        (norm["invoice_number"],),
                    ).fetchone()
                    kf = 1 if keep_forever else 0
                    if existing is None:
                        conn.execute(
                            """
                            INSERT INTO mirror_invoice (
                                invoice_number, invoice_account, customer_name,
                                invoice_date, sales_order, amount,
                                sh_processing_fees, sh_processing_fees_charges,
                                sh_freight, sh_freight_charges,
                                sh_tariff, sh_tariff_charges,
                                sales_group, raw_json,
                                first_seen_utc, last_seen_utc, row_hash,
                                keep_forever
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                norm["invoice_number"], norm["invoice_account"],
                                norm["customer_name"], norm["invoice_date"],
                                norm["sales_order"], norm["amount"],
                                norm["sh_processing_fees"],
                                norm["sh_processing_fees_charges"],
                                norm["sh_freight"], norm["sh_freight_charges"],
                                norm["sh_tariff"], norm["sh_tariff_charges"],
                                norm["sales_group"],
                                json.dumps(raw, default=str),
                                now, now, row_hash, kf,
                            ),
                        )
                        inserted += 1
                    elif existing["row_hash"] != row_hash:
                        conn.execute(
                            """
                            UPDATE mirror_invoice SET
                                invoice_account=?, customer_name=?,
                                invoice_date=?, sales_order=?, amount=?,
                                sh_processing_fees=?, sh_processing_fees_charges=?,
                                sh_freight=?, sh_freight_charges=?,
                                sh_tariff=?, sh_tariff_charges=?,
                                sales_group=?, raw_json=?,
                                last_seen_utc=?, row_hash=?,
                                keep_forever = MAX(keep_forever, ?)
                            WHERE invoice_number=?
                            """,
                            (
                                norm["invoice_account"], norm["customer_name"],
                                norm["invoice_date"], norm["sales_order"],
                                norm["amount"],
                                norm["sh_processing_fees"],
                                norm["sh_processing_fees_charges"],
                                norm["sh_freight"], norm["sh_freight_charges"],
                                norm["sh_tariff"], norm["sh_tariff_charges"],
                                norm["sales_group"],
                                json.dumps(raw, default=str),
                                now, row_hash, kf,
                                norm["invoice_number"],
                            ),
                        )
                        updated += 1
                    else:
                        conn.execute(
                            "UPDATE mirror_invoice SET last_seen_utc=?, "
                            "keep_forever = MAX(keep_forever, ?) "
                            "WHERE invoice_number=?",
                            (now, kf, norm["invoice_number"]),
                        )
                        unchanged += 1

                    pending += 1
                    if pending >= _COMMIT_BATCH:
                        conn.commit()
                        pending = 0
                except Exception:
                    row_errors += 1
                    if row_errors <= 5:
                        log.exception(
                            "upsert_invoice: row failed (invoice=%r)",
                            (raw or {}).get("Invoice"),
                        )
                    elif row_errors == 6:
                        log.warning(
                            "upsert_invoice: further per-row errors will be "
                            "counted but not logged"
                        )

    except Exception as exc:
        err = str(exc)
        log.exception("upsert_invoice failed")
    finally:
        _finish_refresh_run(
            run_id,
            status="failed" if err else "success",
            rows_in=len(rows),
            rows_inserted=inserted,
            rows_updated=updated,
            rows_pruned=pruned,
            error_message=err,
        )

    log.info(
        "upsert_invoice: rows_in=%d inserted=%d updated=%d unchanged=%d "
        "skipped_missing_invoice=%d skipped_missing_date=%d row_errors=%d "
        "pruned=%d duration=%.2fs",
        len(rows), inserted, updated, unchanged,
        skipped_missing_invoice, skipped_missing_date, row_errors,
        pruned, time.monotonic() - t_start,
    )

    return {
        "rows_in":                  len(rows),
        "inserted":                 inserted,
        "updated":                  updated,
        "unchanged":                unchanged,
        "pruned":                   pruned,
        "skipped_missing_invoice":  skipped_missing_invoice,
        "skipped_missing_date":     skipped_missing_date,
        "row_errors":               row_errors,
    }


# ---------------------------------------------------------------------------
# Read-back / fallback
# ---------------------------------------------------------------------------


def get_customers_fallback(salesman: str | None = None) -> list[dict]:
    """Customer dropdown rows from the mirror.

    Returns the same shape ``reporting_api.list_customers`` returns:
    ``[{key, name, salesman}, ...]`` where ``name`` is the clean
    customer name (no ID prefix). Sorted by name.
    """
    init_mirror_db()
    sql = ("SELECT customer_account, customer_name, sales_group "
           "FROM mirror_customers")
    params: tuple = ()
    if salesman:
        sql += " WHERE sales_group = ?"
        params = (salesman.strip(),)
    out = []
    with connect() as conn:
        for r in conn.execute(sql, params):
            acct = r["customer_account"]
            cname = (r["customer_name"] or "").strip()
            out.append({
                "key":      acct,
                "name":     cname or acct,
                "salesman": r["sales_group"] or "",
            })
    out.sort(key=lambda c: c["name"].lower())
    return out


def get_salesmen_fallback() -> list[dict]:
    """Distinct salesmen (SalesGroup) from the customer mirror."""
    init_mirror_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT sales_group FROM mirror_customers "
            "WHERE sales_group IS NOT NULL AND sales_group != '' "
            "ORDER BY sales_group"
        ).fetchall()
    return [{"key": r["sales_group"], "name": r["sales_group"]} for r in rows]


def get_customer_rows() -> list[dict]:
    """Raw mirrored customer-master rows for app surfaces."""
    init_mirror_db()
    out: list[dict] = []
    with connect() as conn:
        for r in conn.execute("SELECT raw_json FROM mirror_customers ORDER BY customer_name"):
            try:
                out.append(json.loads(r["raw_json"]))
            except Exception:
                pass
    return out


def _salesline_raw_from_row(row: Any) -> dict:
    try:
        raw = json.loads(row["raw_json"] or "{}")
    except Exception:
        raw = {}
    # Overlay canonical mirror columns so app readers work even when the
    # endpoint changes field aliases between OrderDate/CreatedDateTime/etc.
    raw.setdefault("SalesOrderNumber", row["sales_order_number"])
    raw.setdefault("LineNumber", row["line_number"])
    raw.setdefault("CustomerAccount", row["customer_account"])
    raw.setdefault("CustomerName", row["customer_name"])
    raw.setdefault("customername", row["customer_name"])
    raw.setdefault("SalesGroup", row["sales_group"])
    raw.setdefault("OrderDate", row["order_date"])
    raw.setdefault("CreatedDateTime", row["created_datetime"] or row["order_date"])
    raw.setdefault("CustomerRequisition", row["po_number"])
    raw.setdefault("Item", row["item_number"])
    raw.setdefault("ItemDescription", row["item_name"])
    raw.setdefault("SalesPrice", row["unit_price"])
    raw.setdefault("OrderStatus", row["order_status"])
    raw.setdefault("SalesStatus", row["status"])
    raw.setdefault("QuantityOrdered", row["qty_ordered"])
    raw.setdefault("QuantityShipped", row["qty_shipped"])
    raw.setdefault("QuantityCancelled", row["qty_cancelled"])
    raw.setdefault("Ordered $", row["ordered_dollars"])
    raw.setdefault("Shipped $", row["shipped_dollars"])
    raw.setdefault("Cancelled $", row["cancelled_dollars"])
    return raw


def get_salesline_fallback(*, customer_account: str | None = None,
                           date_from: str | None = None,
                           date_to: str | None = None,
                           status: str | None = None,
                           order_number: str | None = None) -> list[dict]:
    """Serve salesline rows from the mirror.

    Filters mirror the ones the SP supports. Returns rows in roughly the
    same shape the SP would (raw_json is replayed verbatim) so callers
    can run them through the existing _norm_row helper.

    Raises ``MirrorWindowExceeded`` if the caller asks for data older
    than the earliest row in the mirror. The mirror has no retention
    window: this check just reflects "what we actually have offline".
    An admin can run the "Backfill since D365 go-live" job to pull in
    older rows.
    """
    init_mirror_db()
    if date_from:
        with connect() as conn:
            earliest = conn.execute(
                "SELECT MIN(order_date) FROM mirror_salesline"
            ).fetchone()[0]
        if earliest and date_from[:10] < str(earliest)[:10]:
            raise MirrorWindowExceeded(
                "We're showing cached data because the live data source is "
                f"unreachable, and the cache only goes back to {earliest}. "
                "Please pick a date range starting on or after that date, "
                "or ask an admin to run the 'Backfill since D365 go-live' "
                "job."
            )

    where: list[str] = []
    params: list[Any] = []
    if customer_account:
        where.append("customer_account = ?")
        params.append(_customer_account(customer_account))
    if order_number:
        where.append("sales_order_number = ?")
        params.append(str(order_number).strip())
    if date_from:
        where.append("order_date >= ?")
        params.append(date_from[:10])
    if date_to:
        where.append("order_date <= ?")
        params.append(date_to[:10])
    if status:
        where.append("status = ?")
        params.append(status.strip())

    sql = "SELECT * FROM mirror_salesline"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY order_date DESC, sales_order_number, line_number"

    out: list[dict] = []
    with connect() as conn:
        for r in conn.execute(sql, params):
            out.append(_salesline_raw_from_row(r))
    return out


def _invoice_raw_from_row(row: Any) -> dict:
    """Reconstruct an invoiced_order_charges API row from a mirror row."""
    try:
        raw = json.loads(row["raw_json"] or "{}")
    except Exception:
        raw = {}
    raw.setdefault("Invoice", row["invoice_number"])
    raw.setdefault("InvoiceAccount", row["invoice_account"])
    raw.setdefault("CustomerName", row["customer_name"])
    raw.setdefault("InvoiceDate", row["invoice_date"])
    raw.setdefault("SalesOrder", row["sales_order"])
    raw.setdefault("Amount", row["amount"])
    raw.setdefault("SH_ProcessingFees", row["sh_processing_fees"])
    raw.setdefault("SH_ProcessingFeesCharges", row["sh_processing_fees_charges"])
    raw.setdefault("SH_Freight", row["sh_freight"])
    raw.setdefault("SH_FreightCharges", row["sh_freight_charges"])
    raw.setdefault("SH_Tariff", row["sh_tariff"])
    raw.setdefault("SH_TariffCharges", row["sh_tariff_charges"])
    raw.setdefault("SalesGroup", row["sales_group"])
    return raw


def get_invoice_fallback(*, invoice_account: str | None = None,
                         invoice_accounts: Iterable[str] | None = None,
                         date_from: str | None = None,
                         date_to: str | None = None,
                         sales_group: str | None = None,
                         invoice_number: str | None = None,
                         sales_order: str | None = None) -> list[dict]:
    """Serve invoice rows from the mirror.

    Same contract as :func:`get_salesline_fallback`. The mirror keeps
    every row forever; ``MirrorWindowExceeded`` is raised when the
    caller asks for data older than the earliest invoice we have.
    Accepts either a single ``invoice_account`` or a list
    (``invoice_accounts``) for multi-customer filtering.
    """
    init_mirror_db()
    if date_from:
        with connect() as conn:
            earliest = conn.execute(
                "SELECT MIN(invoice_date) FROM mirror_invoice"
            ).fetchone()[0]
        if earliest and date_from[:10] < str(earliest)[:10]:
            raise MirrorWindowExceeded(
                "We're showing cached data because the live data source is "
                f"unreachable, and the cache only goes back to {earliest}. "
                "Please pick a date range starting on or after that date, "
                "or ask an admin to run the 'Backfill since D365 go-live' "
                "job."
            )

    where: list[str] = []
    params: list[Any] = []
    accts: list[str] = []
    if invoice_account:
        accts.append(_customer_account(invoice_account))
    if invoice_accounts:
        for a in invoice_accounts:
            norm = _customer_account(a)
            if norm and norm not in accts:
                accts.append(norm)
    if len(accts) == 1:
        where.append("invoice_account = ?")
        params.append(accts[0])
    elif accts:
        placeholders = ",".join("?" for _ in accts)
        where.append(f"invoice_account IN ({placeholders})")
        params.extend(accts)
    if invoice_number:
        where.append("invoice_number = ?")
        params.append(str(invoice_number).strip())
    if sales_order:
        where.append("sales_order = ?")
        params.append(str(sales_order).strip())
    if date_from:
        where.append("invoice_date >= ?")
        params.append(date_from[:10])
    if date_to:
        where.append("invoice_date <= ?")
        params.append(date_to[:10])
    if sales_group:
        where.append("sales_group = ?")
        params.append(sales_group.strip())

    sql = "SELECT * FROM mirror_invoice"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY invoice_date DESC, invoice_number"

    out: list[dict] = []
    with connect() as conn:
        for r in conn.execute(sql, params):
            out.append(_invoice_raw_from_row(r))
    return out


def mirror_freshness() -> dict[str, Any]:
    """Quick diagnostic snapshot for the admin diag page + UI badge."""
    init_mirror_db()
    with connect() as conn:
        cust = conn.execute(
            "SELECT COUNT(*) AS n, MAX(last_seen_utc) AS latest "
            "FROM mirror_customers"
        ).fetchone()
        sal = conn.execute(
            "SELECT COUNT(*) AS n, MAX(last_seen_utc) AS latest, "
            "MIN(order_date) AS earliest_date, MAX(order_date) AS latest_date "
            "FROM mirror_salesline"
        ).fetchone()
        inv = conn.execute(
            "SELECT COUNT(*) AS n, MAX(last_seen_utc) AS latest, "
            "MIN(invoice_date) AS earliest_date, MAX(invoice_date) AS latest_date "
            "FROM mirror_invoice"
        ).fetchone()
        last_run = conn.execute(
            "SELECT scope, status, started_utc, finished_utc, error_message "
            "FROM mirror_refresh_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return {
        "customers": {
            "rows":            cust["n"] if cust else 0,
            "last_seen_utc":   (cust["latest"] if cust else None),
        },
        "salesline": {
            "rows":            sal["n"] if sal else 0,
            "last_seen_utc":   (sal["latest"] if sal else None),
            "earliest_date":   (sal["earliest_date"] if sal else None),
            "latest_date":     (sal["latest_date"] if sal else None),
            "window_days":     SALESLINE_WINDOW_DAYS,
        },
        "invoice": {
            "rows":            inv["n"] if inv else 0,
            "last_seen_utc":   (inv["latest"] if inv else None),
            "earliest_date":   (inv["earliest_date"] if inv else None),
            "latest_date":     (inv["latest_date"] if inv else None),
            "window_days":     INVOICE_WINDOW_DAYS,
        },
        "last_run": dict(last_run) if last_run else None,
    }


def list_recent_refresh_runs(limit: int = 25) -> list[dict]:
    """For admin debugging: most recent refresh runs."""
    init_mirror_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM mirror_refresh_runs "
            "ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Refresh-run audit trail
# ---------------------------------------------------------------------------


def _start_refresh_run(*, scope: str, trigger: str,
                       triggered_by: str | None = None) -> int:
    init_mirror_db()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO mirror_refresh_runs "
            "(scope, trigger, started_utc, status, triggered_by) "
            "VALUES (?,?,?,?,?)",
            (scope, trigger, _utcnow(), "running", triggered_by),
        )
        return int(cur.lastrowid)


def _finish_refresh_run(run_id: int, *, status: str,
                        rows_in: int = 0, rows_inserted: int = 0,
                        rows_updated: int = 0, rows_pruned: int = 0,
                        error_message: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE mirror_refresh_runs SET "
            "finished_utc=?, status=?, rows_in=?, rows_inserted=?, "
            "rows_updated=?, rows_pruned=?, error_message=? "
            "WHERE id=?",
            (_utcnow(), status, rows_in, rows_inserted,
             rows_updated, rows_pruned, error_message, run_id),
        )
