"""Filter-form params -> Reporting API stored-procedure params.

The viewer sends report-agnostic snake_case filters (period, start_date,
customers, salesman, ...). Each report maps to one SP (`report_id`) and a
translator that emits the PascalCase params that SP expects. This is the
external API contract, re-implemented cleanly for v3 (single source of truth
for the report-id map + translation - no per-call duplication).

Date params are Eastern wall-clock 'YYYY-MM-DD HH:MM:SS' (see report_engine.dates):
windows open at 00:00:00 and close at 23:59:59.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from report_engine.dates import (
    D365_GO_LIVE,
    parse_custom_range,
    parse_period,
    sp_datetime,
    today_eastern,
)

Translator = Callable[[dict], dict[str, Any]]


def _csv(value: Any) -> str | None:
    """List-or-scalar -> comma-separated string, or None when empty."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        items = [str(x).strip() for x in value if str(x).strip()]
        return ",".join(items) if items else None
    s = str(value).strip()
    return s or None


def _resolve_window(params: dict) -> tuple[date | None, date | None]:
    """Resolve the filter form's period/custom-range into (start, end) dates.

    Returns (None, None) for all_time / unset so the SP applies its own default.
    """
    period = (params.get("period") or "").strip().lower()
    start_raw = (params.get("start_date") or "").strip()
    end_raw = (params.get("end_date") or "").strip()

    # Blank / all_time -> no date filter (the SP applies its own default).
    # Matches the test-app contract: a named period is required to bound dates.
    if period in ("all_time", ""):
        return (None, None)
    if period == "custom":
        if not (start_raw and end_raw):
            return (None, None)
        try:
            p = parse_custom_range(start_raw, end_raw)
        except ValueError:
            # Unparseable custom dates -> omit the filter rather than 500.
            return (None, None)
        return p.start_date, p.end_date
    p = parse_period(period)
    return p.start_date, p.end_date


def resolve_window(params: dict) -> tuple[date | None, date | None]:
    """Public: the selected period's (start, end) dates, or (None, None) when
    open-ended. Callers that need to anchor a secondary window (e.g. the
    Invoiced commissions YTD pivot) to the selected period use this.
    """
    return _resolve_window(params or {})


def _date_range(params: dict, from_key: str, to_key: str) -> dict[str, Any]:
    start, end = _resolve_window(params)
    out: dict[str, Any] = {}
    if start:
        out[from_key] = sp_datetime(start, end_of_day=False)
    if end:
        out[to_key] = sp_datetime(end, end_of_day=True)
    return out


def _resolved_year(params: dict) -> int:
    raw = (params or {}).get("year")
    try:
        return int(raw) if raw not in (None, "") else today_eastern().year
    except (TypeError, ValueError):
        return today_eastern().year


# --- per-report translators ------------------------------------------------

def translate_ordered(p: dict) -> dict[str, Any]:
    """ordered -> rpt.usp_ordered_report.

    Maps the viewer's filters to the new SP's parameter names. The SP ignores any
    param passed as null/omitted. Two old salesline_release filters are dropped
    because the new SP doesn't have them: Company (no such param) and the
    shipped-quantity range (the new SP filters shipped by DOLLARS, not quantity -
    see ShippedDollarsMin/Max). The new SP's CustomerAccount is a single
    exact-match value, so only a single-customer selection is pushed down;
    multi-select is post-filtered by the orchestrator (same as invoiced).
    """
    out = _date_range(p, "CreatedDateTimeFrom", "CreatedDateTimeTo")
    customers = p.get("customers")
    if isinstance(customers, (list, tuple, set)):
        cust = [str(c).strip() for c in customers if str(c).strip()]
    elif customers:
        cust = [str(customers).strip()]
    else:
        cust = []
    if len(cust) == 1:
        out["CustomerAccount"] = cust[0]
    if v := _csv(p.get("salesman")):
        out["SalesGroup"] = v
    if v := _csv(p.get("status")):
        out["SalesStatus"] = v
    if v := _csv(p.get("order_no")):
        out["SalesOrderNumber"] = v
    if v := _csv(p.get("item")):
        out["Item"] = v
    return out


def translate_invoiced(p: dict) -> dict[str, Any]:
    """invoiced -> invoiced_report.

    The new SP's CustomerAccount is a single exact-match value, so only a
    single-customer selection is pushed down; multi-select is post-filtered
    by the caller.
    """
    start, end = _resolve_window(p)
    out: dict[str, Any] = {}
    if start:
        out["InvoiceDateFrom"] = start.isoformat()
    if end:
        out["InvoiceDateTo"] = end.isoformat()
    customers = p.get("customers")
    if isinstance(customers, (list, tuple, set)):
        cust = [str(c).strip() for c in customers if str(c).strip()]
    elif customers:
        cust = [str(customers).strip()]
    else:
        cust = []
    if len(cust) == 1:
        out["CustomerAccount"] = cust[0]
    if v := _csv(p.get("salesman")):
        out["Salesman"] = v
    return out


def translate_salesman(p: dict) -> dict[str, Any]:
    """salesman -> invoiced_order_charges over prior+current full years.

    The Monthly Salesman report compares each month to the same month last
    year, so it needs Jan 1 (prior year) .. Dec 31 (selected year).
    """
    year = _resolved_year(p)
    return {
        "InvoiceDateFrom": sp_datetime(date(year - 1, 1, 1), end_of_day=False),
        "InvoiceDateTo": sp_datetime(date(year, 12, 31), end_of_day=True),
    }


# Number 4's two rolling-12 SPs: same rows, one ordered customer-first and one
# item-first. The mode filter (By Customer / By Item / Both) decides which get
# called; "both" calls each and shows two tabs (owner directive, 2026-07-08).
NUMBER_4_BY_CUSTOMER_SP = "customer_item_sales_rolling_12"
NUMBER_4_BY_ITEM_SP = "item_customer_sales_rolling_12"
_NUMBER_4_MODES = ("both", "by_customer", "by_item")


def number_4_mode(p: dict | None) -> str:
    mode = str((p or {}).get("mode") or "").strip().lower()
    return mode if mode in _NUMBER_4_MODES else "both"


def translate_number_4(p: dict) -> dict[str, Any]:
    """number_4 -> the rolling-12 SPs (customer_item / item_customer).

    The SPs pivot server-side (a Qty and $ column per month) and take AsOfDate +
    IncludeCurrentMonth instead of a date range. IncludeCurrentMonth is always
    true: the old Number 4's rolling window ended at today, so keeping the
    current month keeps the familiar numbers.
    """
    return {
        "AsOfDate": today_eastern().isoformat(),
        "IncludeCurrentMonth": True,
    }


def translate_item_averages(p: dict) -> dict[str, Any]:
    """item_averages -> same window as Number 4 By Item (rolling 12)."""
    return translate_number_4(p)


def translate_customer_activity(p: dict) -> dict[str, Any]:
    """customer_activity -> rpt.usp_customer_activity."""
    try:
        order_count = int(p.get("order_count") or 1)
    except (TypeError, ValueError):
        order_count = 1
    out: dict[str, Any] = {"OrderCount": min(100, max(1, order_count))}
    if as_of_date := _csv(p.get("as_of_date")):
        out["AsOfDate"] = as_of_date
    for form_key, parameter in (
        ("salesman", "Salesman"),
        ("customer_account", "CustomerAccount"),
        ("customer_name", "CustomerName"),
    ):
        if value := _csv(p.get(form_key)):
            out[parameter] = value
    return out


# (report_id, translator) keyed by in-app report key. Single source of truth.
REPORT_ID_MAP: dict[str, tuple[str, Translator]] = {
    "ordered": ("ordered_report", translate_ordered),
    "invoiced": ("invoiced_report", translate_invoiced),
    "salesman": ("invoiced_order_charges", translate_salesman),
    # number_4 runs one or two SPs depending on the mode filter; the primary
    # (By Customer) is listed here for the dev API preview. The orchestrator
    # picks the actual SP(s) via NUMBER_4_BY_CUSTOMER_SP / NUMBER_4_BY_ITEM_SP.
    "number_4": (NUMBER_4_BY_CUSTOMER_SP, translate_number_4),
    "item_averages": (NUMBER_4_BY_ITEM_SP, translate_item_averages),
    "customer_activity": ("customer_activity", translate_customer_activity),
}


def report_id_for(report_key: str) -> str:
    entry = REPORT_ID_MAP.get(report_key)
    if entry is None:
        raise KeyError(f"No reporting-API mapping for report {report_key!r}")
    return entry[0]


def translate(report_key: str, params: dict | None) -> dict[str, Any]:
    """Translate filter params to SP params for `report_key`."""
    entry = REPORT_ID_MAP.get(report_key)
    if entry is None:
        raise KeyError(f"No reporting-API mapping for report {report_key!r}")
    return entry[1](params or {})
