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
    parse_custom_month,
    parse_custom_range,
    parse_period,
    sp_datetime,
    today_eastern,
)

Translator = Callable[[dict], dict[str, Any]]


def _int_param(params: dict, *keys: str) -> int | None:
    for key in keys:
        raw = params.get(key)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return None


def period_selection_error(params: dict) -> str | None:
    """Why this period cannot run, or None if it is complete enough.

    Call only for reports that expose a period filter. Explicit all_time is
    allowed (saved views / schedules); a blank period is not.
    """
    period = (params.get("period") or "").strip().lower()
    if not period:
        return "Choose a period before running this report."
    if period == "custom":
        start_raw = (params.get("start_date") or "").strip()
        end_raw = (params.get("end_date") or "").strip()
        if not (start_raw and end_raw):
            return "Custom Date Range needs a From date and a To date."
        try:
            parse_custom_range(start_raw, end_raw)
        except ValueError:
            return "Custom range dates are not valid."
        return None
    if period == "custom_month":
        year = _int_param(params, "custom_year", "year")
        month = _int_param(params, "month")
        if year is None or month is None:
            return "Custom Month and Year needs both a month and a year."
        try:
            parse_custom_month(year, month)
        except ValueError:
            return "Pick a valid month and year."
        return None
    if period == "all_time":
        return None
    try:
        parse_period(period)
    except ValueError:
        return "Unknown period. Choose one from the list."
    return None


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
    if period == "custom_month":
        year = _int_param(params, "custom_year", "year")
        month = _int_param(params, "month")
        if year is None or month is None:
            return (None, None)
        try:
            p = parse_custom_month(year, month)
        except ValueError:
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
    out = _date_range(p, "InvoiceDateFrom", "InvoiceDateTo")
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
    """salesman -> rpt.usp_monthly_salesman_yoy (catalog monthly_salesman_yoy).

    Sales basis is Total Invoice, computed in SQL from rpt.vw_Invoiced_Report.
    """
    year = _resolved_year(p)
    today = today_eastern()
    through = 12
    raw_through = p.get("through_month") if p.get("through_month") not in (None, "") else p.get("ThroughMonth")
    try:
        if raw_through not in (None, ""):
            through = max(1, min(12, int(raw_through)))
        elif year == today.year:
            through = today.month
    except (TypeError, ValueError):
        through = today.month if year == today.year else 12

    out: dict[str, Any] = {"ReportYear": year, "ThroughMonth": through}
    if sid := _csv(p.get("salesman_id") or p.get("SalesmanId")):
        out["SalesmanId"] = sid
    if sname := _csv(p.get("salesman") or p.get("SalesmanName")):
        out["SalesmanName"] = sname
    if acct := _csv(p.get("customer_account") or p.get("CustomerAccount") or p.get("customers")):
        # Single account only; multi-select is post-filtered if needed later.
        if "," not in acct:
            out["CustomerAccount"] = acct
    if cname := _csv(p.get("customer_name") or p.get("CustomerName")):
        out["CustomerName"] = cname
    return out



# Number 4's two rolling-12 SPs: same rows, one ordered customer-first and one
# item-first. The mode filter (By Customer / By Item / Both) decides which get
# called; each view becomes a 12-month tab plus a YTD tab.
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


SALES_BY_STATE_SUMMARY_SP = "sales_by_state_summary"
SALES_BY_STATE_NYC_SP = "sales_by_state_new_york_city"
SALES_BY_STATE_DETAIL_SP = "sales_by_state_filtered"


def translate_sales_by_state(p: dict) -> dict[str, Any]:
    """sales_by_state -> the three sales-by-state SPs (same FromDate/ToDate).

    The catalog wants calendar dates (YYYY-MM-DD), not datetime. A year filter
    becomes Jan 1..Dec 31 of that year. A custom period still wins if both
    start and end are set.
    """
    start, end = _resolve_window(p)
    if not (start and end):
        year = _resolved_year(p)
        start, end = date(year, 1, 1), date(year, 12, 31)
    out: dict[str, Any] = {
        "FromDate": start.isoformat(),
        "ToDate": end.isoformat(),
    }
    if company := _csv(p.get("company") or p.get("Company")):
        out["Company"] = company
    return out


def translate_customer_last_orders(p: dict) -> dict[str, Any]:
    """customer_last_order page -> customer_last_orders (rpt.usp_customer_last_orders)."""
    try:
        order_count = int(p.get("order_count") or 10)
    except (TypeError, ValueError):
        order_count = 10
    out: dict[str, Any] = {"OrderCount": min(100, max(1, order_count))}
    if acct := _csv(p.get("customer_account") or p.get("CustomerAccount")):
        out["CustomerAccount"] = acct
    if as_of_date := _csv(p.get("as_of_date")):
        out["AsOfDate"] = as_of_date
    return out


# (report_id, translator) keyed by in-app report key. Single source of truth.
REPORT_ID_MAP: dict[str, tuple[str, Translator]] = {
    "ordered": ("ordered_report", translate_ordered),
    "invoiced": ("invoiced_report", translate_invoiced),
    "salesman": ("monthly_salesman_yoy", translate_salesman),

    # number_4 runs one or two SPs depending on the mode filter; the primary
    # (By Customer) is listed here for the dev API preview. The orchestrator
    # picks the actual SP(s) via NUMBER_4_BY_CUSTOMER_SP / NUMBER_4_BY_ITEM_SP.
    "number_4": (NUMBER_4_BY_CUSTOMER_SP, translate_number_4),
    "item_averages": (NUMBER_4_BY_ITEM_SP, translate_item_averages),
    "customer_activity": ("customer_activity", translate_customer_activity),
    # In-app page key stays customer_last_order; catalog/SP id is plural.
    "customer_last_order": ("customer_last_orders", translate_customer_last_orders),
    # Three SPs share this translator; the orchestrator calls all three.
    "sales_by_state": (SALES_BY_STATE_SUMMARY_SP, translate_sales_by_state),
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
