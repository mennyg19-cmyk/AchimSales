"""Customer Activity report builder (pure).

Format follows LIVE (reports/customer_activity): start from the customer
universe and left-join each customer's most-recent order so management can see
who has gone quiet. On-screen multi-tab layout follows the test app.

Inputs (facts; the web layer owns fetching + the customer_master/mirror
fallback):
    * customers -- CustomerFact universe (customer_master SP, mirror fallback)
    * orders    -- OrderLineFact over the all-time window (salesline_release)

Tabs: "All" (Salesman column up front), one tab per assigned salesman, then
"Unassigned". Customers with no orders show LIVE-style "N/A". Salesman/manager
scope (scope.salesman / scope.salesman_list) restricts the per-salesman tabs
and the All tab to that book; privileged users see everything.
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping

from report_engine.facts import CustomerFact, OrderLineFact, SalesmanFact
from report_engine.lib import salesman_key

_NA = "N/A"

_BASE_COLS = [
    {"field": "Customer Account",   "header": "Customer Account",   "type": "text"},
    {"field": "Customer Name",      "header": "Customer Name",      "type": "text"},
    {"field": "Last Order Date",    "header": "Last Order Date",    "type": "date"},
    {"field": "PO #",               "header": "PO #",               "type": "text"},
    {"field": "Sales Order Number", "header": "Sales Order Number", "type": "text"},
]
_ALL_COLS = [{"field": "Salesman", "header": "Salesman", "type": "text"}] + _BASE_COLS


def _last_order_per_customer(orders: Iterable[OrderLineFact]) -> dict[str, dict]:
    by_acct: dict[str, dict] = {}
    for o in orders:
        acct = o.customer_account
        if not acct or not o.order_date:
            continue
        existing = by_acct.get(acct)
        if existing and existing["date"] >= o.order_date:
            continue
        by_acct[acct] = {"date": o.order_date, "po": o.po_number,
                         "so": o.sales_order_number}
    return by_acct


def _resolve_label(sales_group: str, salesmen: Mapping[str, SalesmanFact]) -> str:
    sm = salesmen.get(salesman_key(sales_group)) if sales_group else None
    if sm:
        return sm.display_name or sm.full_name or sales_group
    return sales_group or "Unassigned"


def _allowed_set(scope: Mapping) -> set[str] | None:
    """Lower-cased SalesGroups the viewer may see, or None for privileged."""
    one = (scope.get("salesman") or "").strip()
    if one:
        return {one.lower()}
    many = scope.get("salesman_list") or []
    keys = {str(s).strip().lower() for s in many if str(s).strip()}
    return keys or None


def build(
    customers: Iterable[CustomerFact],
    orders: Iterable[OrderLineFact],
    *,
    salesmen: Mapping[str, SalesmanFact] | None = None,
    scope: Mapping | None = None,
) -> list[dict]:
    salesmen = salesmen or {}
    allowed = _allowed_set(scope or {})
    last_orders = _last_order_per_customer(orders)

    rows_all: list[dict] = []
    rows_unassigned: list[dict] = []
    by_salesman: dict[str, list[dict]] = {}

    for cust in customers:
        acct = cust.customer_account
        if not acct:
            continue
        sg = cust.sales_group or ""
        label = _resolve_label(sg, salesmen)
        is_unassigned = (not sg) or sg.lower() == "unassigned"

        order = last_orders.get(acct)
        row = {
            "Customer Account":   acct,
            "Customer Name":      cust.customer_name,
            "Last Order Date":    order["date"] if order else _NA,
            "PO #":               (order["po"] or _NA) if order else _NA,
            "Sales Order Number": (order["so"] or _NA) if order else _NA,
        }

        if allowed is not None:
            if is_unassigned:
                continue
            if sg.lower() not in allowed and salesman_key(sg) not in allowed:
                continue

        if is_unassigned:
            rows_unassigned.append(row)
            rows_all.append({"Salesman": "Unassigned", **row})
        else:
            by_salesman.setdefault(label, []).append(row)
            rows_all.append({"Salesman": label, **row})

    def _sorted(rs: list[dict]) -> list[dict]:
        return sorted(rs, key=lambda r: (r["Customer Name"] or "").lower())

    tabs: list[dict] = [{"key": "all", "name": "All", "columns": _ALL_COLS,
                         "rows": _sorted(rows_all)}]
    for name in sorted(by_salesman, key=str.lower):
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "sm"
        tabs.append({"key": "sm_" + slug, "name": name[:31],
                     "columns": _BASE_COLS, "rows": _sorted(by_salesman[name])})
    if rows_unassigned and allowed is None:
        tabs.append({"key": "unassigned", "name": "Unassigned",
                     "columns": _BASE_COLS, "rows": _sorted(rows_unassigned)})
    return tabs
