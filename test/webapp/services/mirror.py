"""Local SQLite mirror for the on-prem reporting API.

This module is the test app's offline safety net. Whenever the
reporting API succeeds, every row that came back is upserted into a
local SQLite table here. If the API is later unreachable, lookups,
dropdowns, and the Customer's Last Order viewer can keep working from
the mirror with a clear "showing cached data" badge.

Scope (matches the user's spec):

* ``mirror_customers``      -- full customer master snapshot (every row
                               is small, so we keep them all and never
                               prune).
* ``mirror_salesline``      -- order-line rows from salesline_release,
                               capped to a rolling 60-day window. Old
                               rows get pruned on every refresh so the
                               mirror stays small.
* ``mirror_refresh_runs``   -- audit trail of every snapshot refresh
                               (manual button or daily 00:00 ET cron).

Upsert semantics:
    * Match incoming rows on a stable key (CustomerAccount for
      customers, SalesOrderNumber+LineNumber for order lines).
    * If the row exists and the snapshot's data differs from the
      mirror, UPDATE.
    * If the row doesn't exist, INSERT.
    * Rows in the mirror that the API didn't return are LEFT ALONE
      (we don't know if they were deleted upstream or if the caller
      just used a narrower filter). The daily full-snapshot refresh
      is what cleans up genuinely stale rows.

Read-back (fallback) semantics:
    * Customer / salesman lookups: return whatever's in
      ``mirror_customers`` -- the master list never expires.
    * salesline fallback for the Ordered Report and Customer's Last
      Order: only the past 60 days. If a request needs older data we
      raise ``MirrorWindowExceeded`` so the caller can show a clear
      plain-English error instead of silently lying.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from test.webapp.db import connect

log = logging.getLogger(__name__)


# Rolling window for salesline mirror (in days). The dashboard and
# customer/order pages intentionally describe their data as this window.
SALESLINE_WINDOW_DAYS = 60


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
    """Idempotent: ensure mirror tables exist. Safe on every boot."""
    global _init_done
    with _init_lock:
        if _init_done:
            return
        with connect() as conn:
            for stmt in _MIRROR_SCHEMA:
                conn.execute(stmt)
            _ensure_mirror_columns(conn)
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
                     triggered_by: str | None = None) -> dict[str, int]:
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


def upsert_salesline(rows: Iterable[dict], *, trigger: str = "piggyback",
                     prune_window_days: int = SALESLINE_WINDOW_DAYS,
                     triggered_by: str | None = None,
                     keep_forever: bool = False) -> dict[str, int]:
    """Mirror a batch of salesline_release rows.

    Every well-formed row (has a sales order number and a parseable
    order date) is stored as-is. After ingest, if the trigger is a
    full-snapshot refresh (not a piggyback from a report run) and the
    mirror still has data within the rolling ``prune_window_days``
    window, anything older than the window is pruned. Sandbox /
    historical batches whose newest row is already older than the
    window are kept verbatim so the dashboard has something to show.
    """
    init_mirror_db()
    rows = list(rows or [])
    run_id = _start_refresh_run(scope="salesline", trigger=trigger,
                                triggered_by=triggered_by)

    inserted = updated = unchanged = pruned = 0
    skipped_missing_order = skipped_missing_date = skipped_outside_window = 0
    now = _utcnow()
    err: str | None = None
    try:
        with connect() as conn:
            for raw in rows:
                norm = _normalize_salesline_row(raw)
                if not norm["sales_order_number"]:
                    skipped_missing_order += 1
                    continue
                if not norm["order_date"]:
                    skipped_missing_date += 1
                    continue
                # Intentionally NO window filter at ingest time. Whatever
                # the API returns is what we mirror -- the dashboard reads
                # everything from this table, and a defensive prune below
                # narrows to the rolling window only when it's safe to do
                # so (i.e. there's still recent data after pruning). This
                # avoids the "0 inserted, all skipped" failure mode when
                # the API returns sandbox/historical data whose OrderDate
                # is older than today minus the window.
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
                    # Never *clear* keep_forever in an update -- once a
                    # row is pinned, leave it pinned. Pin it now if this
                    # batch is a backfill batch.
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

            # Defensive prune. Only when we're doing an explicit
            # full-snapshot refresh (not a piggyback from a report run),
            # and only if there's *still* data within the rolling window
            # after the prune. If every row in the mirror is older than
            # the cutoff (sandbox/historical), we leave it alone so the
            # dashboard has something to show.
            if trigger != "piggyback" and prune_window_days:
                today = datetime.now(timezone.utc).date()
                cutoff = (today - timedelta(days=prune_window_days)).isoformat()
                latest = conn.execute(
                    "SELECT MAX(order_date) FROM mirror_salesline "
                    "WHERE keep_forever = 0"
                ).fetchone()[0]
                if latest and str(latest) >= cutoff:
                    cur = conn.execute(
                        "DELETE FROM mirror_salesline "
                        "WHERE order_date < ? AND keep_forever = 0",
                        (cutoff,),
                    )
                    pruned = cur.rowcount or 0
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

    return {
        "rows_in":                 len(rows),
        "inserted":                inserted,
        "updated":                 updated,
        "unchanged":               unchanged,
        "pruned":                  pruned,
        "skipped_missing_order":   skipped_missing_order,
        "skipped_missing_date":    skipped_missing_date,
        "skipped_outside_window":  skipped_outside_window,
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

    Raises ``MirrorWindowExceeded`` if the request reaches outside the
    mirror's rolling window. The error message is plain English so the
    caller can surface it to the user without rewording.
    """
    init_mirror_db()
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=SALESLINE_WINDOW_DAYS)).date().isoformat()
    if date_from and date_from[:10] < cutoff:
        raise MirrorWindowExceeded(
            "We're showing cached data because the live data source is "
            "unreachable, and the cache only goes back "
            f"{SALESLINE_WINDOW_DAYS} days (to {cutoff}). "
            "Please pick a date range starting on or after that date, or "
            "try again later when the live data source is back."
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
