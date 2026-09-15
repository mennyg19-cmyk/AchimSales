"""Thin tabs from doorway rows. Do not port v3/report_engine."""

from __future__ import annotations

from collections import defaultdict

import catalog
from doorway import ReportResult


def _cell(row: dict, *names, default=""):
    if not isinstance(row, dict):
        return default
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    lower = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = lower.get(name.lower())
        if value not in (None, ""):
            return value
    return default


def _slug(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_") or "tab"


def _tab(name: str, rows: list) -> dict:
    return {"name": name, "rows": list(rows)}


def _is_credit(row: dict) -> bool:
    flag = _cell(row, "IsCredit", "is_credit")
    if flag in (True, 1, "1", "true", "True", "Y", "yes"):
        return True
    if flag in (False, 0, "0", "false", "False", "N", "no", ""):
        amount = _cell(row, "Total Invoice", "amount", "Sales", default=0)
        try:
            return float(amount) < 0
        except (TypeError, ValueError):
            return False
    return bool(flag)


def _amount(row: dict):
    raw = _cell(row, "Total Invoice", "Open$", "Ordered$", "Sales", "amount", "YTD", default=0)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _group(rows: list[dict], *key_names: str, name_field: str = "") -> list[dict]:
    buckets: dict[str, dict] = {}
    for row in rows:
        key = str(_cell(row, *key_names) or "")
        if not key:
            continue
        bucket = buckets.setdefault(
            key,
            {
                key_names[0]: key,
                "Count": 0,
                "Total": 0.0,
            },
        )
        label = _cell(row, name_field) if name_field else ""
        if label and name_field not in bucket:
            bucket[name_field] = label
        bucket["Count"] += 1
        bucket["Total"] += _amount(row)
    return list(buckets.values())


def _tabs_dict(raw) -> dict:
    if isinstance(raw, dict):
        out = {}
        for key, tab in raw.items():
            if isinstance(tab, dict) and isinstance(tab.get("rows"), list):
                out[str(key)] = {"name": tab.get("name") or str(key), "rows": tab["rows"]}
            elif isinstance(tab, list):
                out[str(key)] = {"name": str(key), "rows": tab}
        return out
    if isinstance(raw, list):
        out = {}
        for index, tab in enumerate(raw):
            if not isinstance(tab, dict):
                continue
            key = str(tab.get("key") or _slug(tab.get("name") or f"tab_{index}"))
            rows = tab.get("rows") if isinstance(tab.get("rows"), list) else []
            out[key] = {"name": tab.get("name") or key, "rows": rows}
        return out
    return {}


def wrap(key: str, tabs: dict, raw: list, *, source: str = "reporting_api") -> dict:
    spec = catalog.spec(key)
    title = spec["title"] if spec else key
    return {
        "data": {
            "report_key": key,
            "title": title,
            "raw": list(raw),
            "tabs": tabs,
            "source": source,
        }
    }


def from_result(key: str, result: ReportResult) -> dict:
    body = result.body if isinstance(result.body, dict) else {}
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    tabs = _tabs_dict(data.get("tabs") or body.get("tabs"))
    raw = result.rows if isinstance(result.rows, list) else []
    if tabs:
        if not raw:
            raw = []
            for tab in tabs.values():
                raw.extend(tab.get("rows") or [])
        return wrap(key, tabs, raw)
    return wrap(key, thin_tabs(key, raw), raw)


def thin_tabs(key: str, rows: list[dict]) -> dict:
    rows = [row for row in rows if isinstance(row, dict)]
    builders = {
        "invoiced": _invoiced,
        "ordered": _ordered,
        "salesman": _salesman,
        "number_4": _number_4_customer,
        "item_averages": _item_averages,
        "customer_activity": _customer_activity,
        "sales_by_state": _sales_by_state_summary,
        "customer_last_order": lambda data: {"lines": _tab("Lines", data)},
    }
    builder = builders.get(key)
    if builder is None:
        return {"rows": _tab("Rows", rows)}
    return builder(rows)


def _invoiced(rows: list[dict]) -> dict:
    credits = [row for row in rows if _is_credit(row)]
    invoices = [row for row in rows if not _is_credit(row)]
    tabs = {
        "summary_by_customer": _tab(
            "Summary by Customer",
            _group(rows, "CustomerAccount", "Customer Account", name_field="CustomerName"),
        ),
        "full_details": _tab("Full Details", rows),
        "credits": _tab("Credits", credits),
        "invoices": _tab("Invoices", invoices),
        "audit_reversals": _tab("Audit - Reversals", credits),
        "totals_by_salesman": _tab(
            "Totals by Salesman",
            _group(rows, "Salesman", "SalesGroup", name_field="SalesmanName"),
        ),
    }
    commission_rows = [
        row
        for row in rows
        if _cell(row, "CommissionDollars", "NetCommission", "Commission") not in ("", None)
    ]
    if commission_rows:
        tabs["commissions"] = _tab("Commissions", commission_rows)
    return tabs


def _ordered(rows: list[dict]) -> dict:
    tabs = {
        "summary": _tab(
            "Summary",
            _group(rows, "CustomerAccount", "Customer Account", name_field="CustomerName"),
        ),
        "by_customer": _tab("By Customer", rows),
        "by_order": _tab("By Order", rows),
        "by_salesman": _tab("By Salesman", _group(rows, "Salesman", "SalesGroup")),
        "full_data": _tab("Full Data", rows),
    }
    if any(_cell(row, "Item #", "Item", "ItemId") for row in rows):
        tabs["by_item"] = _tab(
            "By Item",
            _group(rows, "Item #", "Item", "ItemId", name_field="Item Name"),
        )
    return tabs


def _salesman(rows: list[dict]) -> dict:
    return {
        "yoy": _tab("Year over Year", rows),
        "ytd": _tab("YTD", rows),
    }


def _number_4_customer(rows: list[dict]) -> dict:
    return {
        "by_customer": _tab("By Customer", rows),
        "by_customer_ytd": _tab("By Customer YTD", rows),
    }


def _number_4_item(rows: list[dict]) -> dict:
    return {
        "by_item": _tab("By Item", rows),
        "by_item_ytd": _tab("By Item YTD", rows),
    }


def _item_averages(rows: list[dict]) -> dict:
    return {"items": _tab("Item Averages", rows)}


def _customer_activity(rows: list[dict]) -> dict:
    tabs = {"all": _tab("All", rows)}
    grouped: dict[str, list] = defaultdict(list)
    unassigned = []
    for row in rows:
        salesman = str(_cell(row, "Salesman", "SalesGroup") or "")
        if not salesman:
            unassigned.append(row)
            continue
        grouped[salesman].append(row)
    for salesman, bucket in grouped.items():
        tabs[_slug(salesman)] = _tab(salesman, bucket)
    if unassigned:
        tabs["unassigned"] = _tab("Unassigned", unassigned)
    return tabs


def _sales_by_state_summary(rows: list[dict]) -> dict:
    return {"summary": _tab("Summary", rows)}


def number_4_tabs(customer_rows: list[dict], item_rows: list[dict]) -> dict:
    tabs = {}
    if customer_rows:
        tabs.update(_number_4_customer(customer_rows))
    if item_rows:
        tabs.update(_number_4_item(item_rows))
    return tabs or {"by_customer": _tab("By Customer", [])}


def sales_by_state_tabs(summary: list[dict], nyc: list[dict], detail: list[dict]) -> dict:
    return {
        "summary": _tab("Summary", summary),
        "new_york_city": _tab("New York City", nyc),
        "detail": _tab("Detail", detail),
    }


def last_order_view(account: str, rows: list[dict], customer: dict, recent_invoices: list[dict]) -> dict:
    """Newest Order Rank (or first order number) plus its lines. No ADDON rollup."""
    rows = [row for row in rows if isinstance(row, dict)]
    by_rank: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        raw_rank = _cell(row, "Order Rank", "OrderRank", default=1)
        try:
            rank = int(float(raw_rank))
        except (TypeError, ValueError):
            rank = 1
        by_rank[rank].append(row)
    chosen = by_rank[min(by_rank)] if by_rank else []
    first = chosen[0] if chosen else {}
    lines = []
    for row in chosen:
        qty = _cell(row, "Qty Ordered", "QtyOrdered", "Qty", default=0)
        price = _cell(row, "Sales Price", "SalesPrice", "Price", default=0)
        amount = _cell(row, "Total", "Amount", default="")
        if amount in ("", None):
            try:
                amount = round(float(qty or 0) * float(price or 0), 2)
            except (TypeError, ValueError):
                amount = 0
        lines.append(
            {
                "Item #": _cell(row, "Item #", "Item", "ItemId"),
                "Description": _cell(row, "Description", "Item Name", "ItemName"),
                "Qty": qty,
                "Price": price,
                "Amount": amount,
            }
        )
    return {
        "customer": customer,
        "primary": {
            "order_number": _cell(
                first, "Sales Order Number", "SalesOrderNumber", "order_number"
            ),
            "order_date": str(
                _cell(first, "Order Date", "OrderDate", "order_date")
            )[:10],
            "salesman": customer.get("salesman")
            or _cell(first, "Salesman", "SalesGroup"),
            "po": _cell(first, "PO #", "PO#", "CustomerRequisition"),
        },
        "lines": lines,
        "recent_invoices": recent_invoices,
        "source": "reporting_api",
        "account": account,
    }
