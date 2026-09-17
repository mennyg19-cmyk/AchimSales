"""Viewer filters -> Reporting API PascalCase body. Omit empties."""

from __future__ import annotations

from datetime import date

from period import resolve_period, sp_datetime, today_eastern


def _csv(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        items = [str(part).strip() for part in value if str(part).strip()]
        return ",".join(items) if items else None
    text = str(value).strip()
    return text or None


def _date_range(params: dict, from_key: str, to_key: str) -> dict:
    window = resolve_period(
        params.get("period") or "",
        params.get("from_date") or params.get("start_date") or "",
        params.get("to_date") or params.get("end_date") or "",
    )
    out = {}
    if window:
        out[from_key] = sp_datetime(window.start_date, end_of_day=False)
        out[to_key] = sp_datetime(window.end_date, end_of_day=True)
    return out


def _one_customer(params: dict) -> str | None:
    raw = params.get("customers")
    if isinstance(raw, (list, tuple, set)):
        items = [str(part).strip() for part in raw if str(part).strip()]
        return items[0] if len(items) == 1 else None
    return _csv(raw)


def translate_ordered(params: dict) -> dict:
    out = _date_range(params, "CreatedDateTimeFrom", "CreatedDateTimeTo")
    if acct := _one_customer(params):
        out["CustomerAccount"] = acct
    if group := _csv(params.get("salesman")):
        out["SalesGroup"] = group
    if status := _csv(params.get("status")):
        out["SalesStatus"] = status
    return out


def translate_invoiced(params: dict) -> dict:
    out = _date_range(params, "InvoiceDateFrom", "InvoiceDateTo")
    if acct := _one_customer(params):
        out["CustomerAccount"] = acct
    if salesman := _csv(params.get("salesman")):
        out["Salesman"] = salesman
    return out


def translate_salesman(params: dict) -> dict:
    try:
        year = int(params.get("year") or today_eastern().year)
    except (TypeError, ValueError):
        year = today_eastern().year
    today = today_eastern()
    through = today.month if year == today.year else 12
    return {"ReportYear": year, "ThroughMonth": through}


def translate_number_4(_params: dict) -> dict:
    return {"AsOfDate": today_eastern().isoformat(), "IncludeCurrentMonth": True}


def translate_customer_activity(params: dict) -> dict:
    out = {"OrderCount": 1}
    if salesman := _csv(params.get("salesman")):
        out["Salesman"] = salesman
    return out


def translate_sales_by_state(params: dict) -> dict:
    window = resolve_period(
        params.get("period") or "",
        params.get("from_date") or "",
        params.get("to_date") or "",
    )
    if window is None:
        try:
            year = int(params.get("year") or today_eastern().year)
        except (TypeError, ValueError):
            year = today_eastern().year
        start, end = date(year, 1, 1), date(year, 12, 31)
    else:
        start, end = window.start_date, window.end_date
    return {"FromDate": start.isoformat(), "ToDate": end.isoformat()}


def number_4_mode(params: dict | None) -> str:
    mode = str((params or {}).get("n4_mode") or (params or {}).get("mode") or "both").strip().lower()
    return mode if mode in {"both", "by_customer", "by_item"} else "both"


def translate_last_order(params: dict) -> dict:
    try:
        count = int(params.get("order_count") or 10)
    except (TypeError, ValueError):
        count = 10
    out = {"OrderCount": min(100, max(1, count))}
    if acct := _csv(params.get("customer_account") or params.get("account")):
        out["CustomerAccount"] = acct
    return out


def _flag_on(raw) -> bool:
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else ""
    return str(raw or "").strip().lower() in {"1", "true", "on", "yes"}


def translate_customer_transaction_detail(params: dict) -> dict:
    out = _date_range(params, "CreatedDateTimeFrom", "CreatedDateTimeTo")
    if acct := _one_customer(params):
        out["AccountNum"] = acct
    if invoice := _csv(params.get("invoice") or params.get("Invoice")):
        out["Invoice"] = invoice
    if _flag_on(params.get("open_balance")):
        out["RemainAmountCurMin"] = 0.01
    return out


REPORT_IDS = {
    "ordered": "ordered_report",
    "invoiced": "invoiced_report",
    "salesman": "monthly_salesman_yoy",
    "number_4": "customer_item_sales_rolling_12",
    "item_averages": "item_customer_sales_rolling_12",
    "customer_activity": "customer_activity",
    "customer_last_order": "customer_last_orders",
    "sales_by_state": "sales_by_state_summary",
    "customer_transaction_detail": "customertransactiondetail",
}

NUMBER_4_ITEM_SP = "item_customer_sales_rolling_12"
SALES_BY_STATE_NYC = "sales_by_state_new_york_city"
SALES_BY_STATE_DETAIL = "sales_by_state_filtered"
SALESMEN_MASTER = "salesmen_master"
CUSTOMER_MASTER = "customer_master"

_TRANSLATORS = {
    "ordered": translate_ordered,
    "invoiced": translate_invoiced,
    "salesman": translate_salesman,
    "number_4": translate_number_4,
    "item_averages": translate_number_4,
    "customer_activity": translate_customer_activity,
    "sales_by_state": translate_sales_by_state,
    "customer_last_order": translate_last_order,
    "customer_transaction_detail": translate_customer_transaction_detail,
}


def translate(report_key: str, params: dict | None) -> dict:
    fn = _TRANSLATORS.get(report_key)
    if fn is None:
        raise KeyError(report_key)
    return fn(params or {})
