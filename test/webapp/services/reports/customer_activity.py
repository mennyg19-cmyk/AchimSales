"""Customer Activity Report builder.

Mirrors the live ``reports/customer_activity`` workbook: every customer
in D365 appears, joined to their most recent sales order so management
can see who hasn't ordered in a while.

The live report starts from the customer master and left-joins
all-time order headers. We do the same here, but the data comes from
two SP feeds:

* ``customer_master`` -- the universe of customers + their SalesGroup
* ``salesline_release`` (with a wide D365-go-live-to-today window) --
  every order line, from which we derive the most recent order date,
  PO #, and Sales Order Number per customer.

Output tabs (in order):
    1. "All"        -- every customer, with a Salesman column up front
    2. <Salesman>   -- one tab per assigned salesman (sorted by display
                       name); columns match the All tab minus Salesman
    3. "Unassigned" -- customers with no SalesGroup

Live-style "N/A" appears in the Last Order Date / PO # / Sales Order
columns for customers who have no orders on record at all.

Salesman scoping
----------------
``report_access.scope_params_for_user`` injects ``salesman`` /
``salesman_list`` for salesman + manager roles. We honor those at the
tab-emission stage: a salesman sees only their own tab + the All tab
filtered to their book, never another salesman's tab. Privileged
roles see the full multi-tab layout.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column schemas
# ---------------------------------------------------------------------------


_BASE_COLS = [
    {"field": "Customer Account",    "header": "Customer Account",    "type": "text"},
    {"field": "Customer Name",       "header": "Customer Name",       "type": "text"},
    {"field": "Last Order Date",     "header": "Last Order Date",     "type": "date"},
    {"field": "PO #",                "header": "PO #",                "type": "text"},
    {"field": "Sales Order Number",  "header": "Sales Order Number",  "type": "text"},
]

_ALL_COLS = [
    {"field": "Salesman",            "header": "Salesman",            "type": "text"},
] + _BASE_COLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _str(v: Any) -> str:
    if v is None or v == "NULL":
        return ""
    return str(v).strip()


def _first(raw: dict, *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", "NULL"):
            return value
    return None


def _date_only(v: Any) -> str:
    s = _str(v)
    return s[:10] if len(s) >= 10 else s


def _sm_key(sales_group: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (sales_group or "").strip().lower())


def _load_salesman_display() -> dict[str, str]:
    """SalesGroup -> display label (display_name > full_name > key)."""
    try:
        from test.webapp.db import list_salesman_map
        rows = list_salesman_map()
    except Exception:
        log.exception("customer_activity: failed to load app_salesmen")
        return {}
    out: dict[str, str] = {}
    for r in rows or []:
        key = (r.get("key") or "").strip().lower()
        if not key:
            continue
        out[key] = (r.get("display_name") or r.get("full_name") or r.get("key") or "").strip()
    return out


def _load_customer_master() -> list[dict]:
    """Pull the full customer list from the local mirror.

    The customer_master mirror is populated by the standard piggyback
    + nightly refresh job, and `reporting_api.list_customers` already
    relies on it. Hitting the mirror keeps this report cheap and
    avoids an extra round-trip when running the report interactively.
    """
    try:
        from test.webapp.db import connect as _conn
        with _conn() as c:
            cursor = c.execute(
                "SELECT customer_account, customer_name, sales_group "
                "FROM mirror_customers"
            )
            return [
                {
                    "CustomerAccount": (r["customer_account"] or "").strip(),
                    "CustomerName":    (r["customer_name"] or "").strip(),
                    "SalesGroup":      (r["sales_group"] or "").strip(),
                }
                for r in cursor
                if (r["customer_account"] or "").strip()
            ]
    except Exception:
        log.exception("customer_activity: customer-master mirror read failed")
        return []


def _last_order_per_customer(rows: Iterable[dict]) -> dict[str, dict]:
    """From salesline_release rows, return ``{customer_account: {date, po, so}}``
    holding only the most recent order per customer.
    """
    by_acct: dict[str, dict] = {}
    for r in rows:
        acct = _str(_first(r, "CustomerAccount", "customeraccount", "AccountNum"))
        if not acct:
            continue
        order_date = _date_only(_first(
            r,
            "OrderDate", "OrderCreationDateTime", "CreatedDateTime",
            "ShippingDateRequested", "RequestedShipDate",
        ))
        if not order_date:
            continue
        existing = by_acct.get(acct)
        if existing and existing["date"] >= order_date:
            continue
        by_acct[acct] = {
            "date": order_date,
            "po":   _str(_first(r, "CustomerRequisition", "CustomerReq", "PO #", "PONumber")),
            "so":   _str(_first(r, "SalesOrderNumber", "SalesId", "OrderNumber")),
        }
    return by_acct


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build(
    salesline_rows: Iterable[dict],
    *,
    params: dict | None = None,
) -> list[dict]:
    """Build the customer-activity multi-tab payload.

    ``salesline_rows`` is the raw output of the salesline_release SP
    over the all-time window. ``params`` may carry the runtime-scoped
    ``salesman`` / ``salesman_list`` keys produced by
    ``report_access.scope_params_for_user``; when present we restrict
    the per-salesman tabs to that subset (an empty ``salesman`` =
    privileged user, show everything).
    """
    params = params or {}
    sm_display = _load_salesman_display()
    customers = _load_customer_master()

    last_orders = _last_order_per_customer(salesline_rows)

    salesman_filter = (params.get("salesman") or "").strip()
    salesman_list = params.get("salesman_list") or []
    if salesman_filter:
        allowed = {salesman_filter.lower()}
    elif salesman_list:
        allowed = {str(s).strip().lower() for s in salesman_list if str(s).strip()}
    else:
        allowed = None  # privileged: every salesman

    rows_by_salesman: dict[str, list[dict]] = {}
    rows_unassigned: list[dict] = []
    rows_all: list[dict] = []

    for cust in customers:
        acct = cust["CustomerAccount"]
        sg = cust["SalesGroup"] or ""
        sg_key = _sm_key(sg)
        sg_label = sm_display.get(sg_key) or sg or "Unassigned"

        order = last_orders.get(acct)
        if order:
            last_date = order["date"]
            last_po = order["po"] or "N/A"
            last_so = order["so"] or "N/A"
        else:
            last_date = "N/A"
            last_po = "N/A"
            last_so = "N/A"

        row = {
            "Customer Account":   acct,
            "Customer Name":      cust["CustomerName"],
            "Last Order Date":    last_date,
            "PO #":               last_po,
            "Sales Order Number": last_so,
        }

        is_unassigned = not sg or sg.lower() == "unassigned"

        # Salesman-scoped users should not see other salesmen's rows
        # even in the All tab.
        if allowed is not None:
            if is_unassigned:
                continue
            if sg.lower() not in allowed and sg_key not in allowed:
                continue

        if is_unassigned:
            rows_unassigned.append(row)
            rows_all.append({"Salesman": "Unassigned", **row})
            continue

        rows_by_salesman.setdefault(sg_label, []).append(row)
        rows_all.append({"Salesman": sg_label, **row})

    def _sort_rows(rs: list[dict]) -> list[dict]:
        return sorted(rs, key=lambda r: (r["Customer Name"] or "").lower())

    tabs: list[dict] = []

    tabs.append({
        "key":     "all",
        "name":    "All",
        "columns": _ALL_COLS,
        "rows":    _sort_rows(rows_all),
    })

    for sm_name in sorted(rows_by_salesman.keys(), key=str.lower):
        tabs.append({
            "key":     "sm_" + re.sub(r"[^a-z0-9]+", "_", sm_name.lower()).strip("_") or "sm",
            "name":    sm_name[:31],
            "columns": _BASE_COLS,
            "rows":    _sort_rows(rows_by_salesman[sm_name]),
        })

    # Hide the Unassigned tab for scoped (salesman/manager) views --
    # they shouldn't be looking at other people's leads.
    if rows_unassigned and allowed is None:
        tabs.append({
            "key":     "unassigned",
            "name":    "Unassigned",
            "columns": _BASE_COLS,
            "rows":    _sort_rows(rows_unassigned),
        })

    return tabs
