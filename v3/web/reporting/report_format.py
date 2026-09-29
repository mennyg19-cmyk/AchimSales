"""Report format tabs and columns without running a report.

The explorer edits group / sort / filter on the company Default or any named
company format (``views`` kind ``default`` or ``company``).
"""

from __future__ import annotations

import calendar
from datetime import date

from report_engine.registry import built_reports, get as registry_get
from report_engine.reports import customer_activity, customer_transaction_detail
from report_engine.reports import invoiced, item_averages, number_4, ordered, salesman
from report_engine.reports import sales_by_state

FILTER_OPS = (
    "contains", "equals", "starts", "ends", "empty", "notEmpty",
    "gt", "lt", "between", "on", "before", "after",
)

_CLO_COLS = (
    "Item#", "ItemName", "QtyOrdered", "QtyShipped", "QtyCancelled",
    "UnitPrice", "Total", "SalesOrderNumber",
)


def report_choices() -> list[dict]:
    return [{"key": spec.key, "title": spec.title} for spec in built_reports()]


def tabs_for(report_key: str) -> list[dict]:
    spec = registry_get(report_key)
    if spec is None or spec.status.value != "built":
        return []
    raw = _raw_tabs(report_key)
    out = []
    for tab in raw:
        cols = []
        for col in tab.get("columns") or []:
            if isinstance(col, dict):
                field = str(col.get("field") or col.get("header") or "").strip()
                header = str(col.get("header") or field)
            else:
                field = header = str(col).strip()
            if field:
                cols.append({"field": field, "header": header})
        if tab.get("key"):
            out.append({
                "key": str(tab["key"]),
                "name": str(tab.get("name") or tab["key"]),
                "columns": cols,
            })
    return out


def _raw_tabs(report_key: str) -> list[dict]:
    if report_key == "ordered":
        return ordered.build([])
    if report_key == "invoiced":
        tabs = invoiced.build([], salesmen={})
        keys = {t.get("key") for t in tabs}
        if "totals_by_salesman" not in keys:
            tabs.append({
                "key": "totals_by_salesman",
                "name": "Totals by Salesman",
                "columns": invoiced.SALESMAN_TOTALS_COLS,
            })
        return tabs
    if report_key == "salesman":
        return salesman.build([], year=date.today().year)
    if report_key == "number_4":
        by_customer = (_number4_headers(("Customer #", "Customer Name", "Item #", "Item Name")), [])
        by_item = (_number4_headers(("Item #", "Item Name", "Customer #", "Customer Name")), [])
        return number_4.build(by_customer=by_customer, by_item=by_item)
    if report_key == "customer_activity":
        return customer_activity.build([])
    if report_key == "item_averages":
        return item_averages.build([])
    if report_key == "sales_by_state":
        return sales_by_state.build(summary=[], nyc=[], detail=[])
    if report_key == "customer_transaction_detail":
        return customer_transaction_detail.build([])
    if report_key == "customer_last_order":
        return [{
            "key": "lines",
            "name": "Lines",
            "columns": [{"field": field, "header": field, "type": "text"} for field in _CLO_COLS],
        }]
    return []


def _number4_headers(lead: tuple[str, ...]) -> list[str]:
    today = date.today()
    y, m = today.year, today.month
    months: list[tuple[int, int]] = []
    for _ in range(12):
        months.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    months.reverse()
    headers = list(lead)
    for year, month in months:
        label = f"{calendar.month_abbr[month]}-{str(year)[2:]}"
        headers.append(f"{label} Qty")
        headers.append(f"{label} $")
    headers.extend(("Total Qty", "Total $", "Avg Price", "Book Price", "Salesman"))
    return headers


def apply_format(layout: dict | None, tabs_in: list) -> dict:
    """Merge explorer group/sort/filter into a layout. Other keys stay."""
    base = dict(layout or {})
    views = dict(base.get("views") or {})
    for tab in tabs_in or []:
        if not isinstance(tab, dict):
            continue
        key = str(tab.get("key") or "").strip()
        if not key:
            continue
        prev = dict(views.get(key) or {})
        if tab.get("set_group"):
            prev["group"] = [
                str(col).strip() for col in (tab.get("group") or []) if str(col).strip()
            ]
        else:
            prev.pop("group", None)
        sorters = []
        for sorter in tab.get("sorters") or []:
            if not isinstance(sorter, dict):
                continue
            column = str(sorter.get("column") or "").strip()
            if not column:
                continue
            direction = "desc" if str(sorter.get("dir") or "").lower() == "desc" else "asc"
            sorters.append({"column": column, "dir": direction})
        if sorters:
            prev["sorters"] = sorters
        else:
            prev.pop("sorters", None)
        filters: dict = {}
        for spec in tab.get("filters") or []:
            if not isinstance(spec, dict):
                continue
            column = str(spec.get("column") or "").strip()
            op = str(spec.get("op") or "contains")
            if not column or op not in FILTER_OPS:
                continue
            filters[column] = {
                "op": op,
                "v": "" if spec.get("v") is None else str(spec.get("v")),
                "v2": "" if spec.get("v2") is None else str(spec.get("v2")),
            }
        if filters:
            prev["columnFilters"] = filters
        else:
            prev.pop("columnFilters", None)
        if prev:
            views[key] = prev
        else:
            views.pop(key, None)
    if views:
        base["views"] = views
    elif "views" in base:
        base.pop("views")
    return base
