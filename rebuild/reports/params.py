"""Turns the viewer's filter choices into stored-procedure parameters."""

# === What's in this file ===
# The viewer sends simple filters (a named period, optional custom dates, a
# customer, a salesman). The stored procedure wants specific PascalCase
# parameters. This is the one place that translates between the two, per report.
#
# resolve_window() -- a named period (or custom dates) -> (start_date, end_date)
# translate() -- filter choices -> the SP params for a report (raises if unknown)
# force_salesman_scope() -- pin the salesman param to a person's allowed numbers

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from .lib import text


def _today() -> date:
    return date.today()


def resolve_window(filters: dict) -> tuple[Optional[date], Optional[date]]:
    period = (filters.get("period") or "ytd").strip().lower()
    today = _today()
    if period in ("all_time", ""):
        return (None, None)
    if period == "custom":
        start = _parse_date(filters.get("start_date"))
        end = _parse_date(filters.get("end_date"))
        return (start, end)
    if period == "ytd":
        return (date(today.year, 1, 1), today)
    if period == "this_year":
        return (date(today.year, 1, 1), date(today.year, 12, 31))
    if period == "last_year":
        return (date(today.year - 1, 1, 1), date(today.year - 1, 12, 31))
    if period == "this_month":
        return (date(today.year, today.month, 1), today)
    if period == "last_month":
        first_this = date(today.year, today.month, 1)
        last_prev = first_this.fromordinal(first_this.toordinal() - 1)
        return (date(last_prev.year, last_prev.month, 1), last_prev)
    # Unknown period: behave like YTD rather than failing the run.
    return (date(today.year, 1, 1), today)


def _parse_date(value: Any) -> Optional[date]:
    date_text = text(value)
    if len(date_text) >= 10 and date_text[4] == "-" and date_text[7] == "-":
        try:
            return date.fromisoformat(date_text[:10])
        except ValueError:
            return None
    return None


def _translate_invoiced(filters: dict) -> dict[str, Any]:
    start, end = resolve_window(filters)
    sp_params: dict[str, Any] = {}
    if start:
        sp_params["InvoiceDateFrom"] = start.isoformat()
    if end:
        sp_params["InvoiceDateTo"] = end.isoformat()
    customers = filters.get("customers")
    if isinstance(customers, (list, tuple, set)):
        accounts = [text(c) for c in customers if text(c)]
    elif customers:
        accounts = [text(customers)]
    else:
        accounts = []
    if len(accounts) == 1:
        sp_params["CustomerAccount"] = accounts[0]
    salesman = filters.get("salesman")
    if salesman:
        sp_params["Salesman"] = ",".join(text(number) for number in salesman) if isinstance(salesman, (list, tuple, set)) else text(salesman)
    return sp_params


def _translate_ordered(filters: dict) -> dict[str, Any]:
    sp_params: dict[str, Any] = {}
    start, end = resolve_window(filters)
    if start:
        sp_params["CreatedDateTimeFrom"] = start.isoformat()
    if end:
        sp_params["CreatedDateTimeTo"] = end.isoformat()

    _pass_if_present = (
        "SalesOrderNumber", "CustomerAccount", "Item", "SalesStatus", "LineNumber",
        "CustomerNameContains", "ItemDescriptionContains", "SalesmanNameContains",
        "SalesPriceMin", "SalesPriceMax",
        "QuantityOrderedMin", "QuantityOrderedMax",
        "QuantityReservedMin", "QuantityReservedMax",
        "ReleasedQuantityMin", "ReleasedQuantityMax",
        "DeliveryRemainderMin", "DeliveryRemainderMax",
        "CancelledQTYMin", "CancelledQTYMax",
        "OrderedDollarsMin", "OrderedDollarsMax",
        "ShippedDollarsMin", "ShippedDollarsMax",
        "CancelledDollarsMin", "CancelledDollarsMax",
        "CommissionMin", "CommissionMax",
    )
    for key in _pass_if_present:
        value = filters.get(key)
        if value is not None and value != "":
            sp_params[key] = value

    salesman = filters.get("salesman")
    if salesman:
        sp_params["SalesGroup"] = ",".join(text(number) for number in salesman) if isinstance(salesman, (list, tuple, set)) else text(salesman)

    return sp_params


_TRANSLATORS = {
    "invoiced": _translate_invoiced,
    "ordered": _translate_ordered,
}

# The SP parameter that filters by salesman, per report. Scoping a report to a
# person requires its query to take a salesman filter; a report missing here
# can't be scoped (so a scoped person can't run it -- safe by default).
_SALESMAN_PARAM = {
    "invoiced": "Salesman",
    "ordered": "SalesGroup",
}

# The column in the CLEANED snapshot rows that holds the salesman number, per
# report. This is the backstop the runner filters on after the SP returns, so a
# scoped person never sees another salesman's rows even if the SP ignored the
# filter. It's separate from _SALESMAN_PARAM (what we SEND the SP) because the
# returned column name is a different thing from the input parameter name.
_SCOPE_ROW_FIELD = {
    "invoiced": "Salesman",
    "ordered": "SalesGroup",
}


def translate(report_key: str, filters: Optional[dict]) -> dict[str, Any]:
    translator = _TRANSLATORS.get(report_key)
    if translator is None:
        raise KeyError(f"No parameter translator for report {report_key!r}")
    return translator(filters or {})


def scope_row_field(report_key: str) -> str:
    """The cleaned-row column the runner filters on to enforce salesman scope."""
    field = _SCOPE_ROW_FIELD.get(report_key)
    if field is None:
        raise KeyError(f"Report {report_key!r} has no salesman column to scope by")
    return field


def force_salesman_scope(
    report_key: str, sp_params: dict[str, Any], salesmen: Optional[list[str]]
) -> dict[str, Any]:
    """Pin the salesman parameter to the numbers a person is allowed to see.

    ``salesmen=None`` means "all" (privileged) and leaves the params untouched.
    Otherwise the salesman param is overwritten, so a scoped person can never
    request data outside their numbers regardless of what filters they sent.
    """
    if salesmen is None:
        return sp_params
    param = _SALESMAN_PARAM.get(report_key)
    if param is None:
        raise KeyError(f"Report {report_key!r} can't be scoped by salesman")
    scoped = dict(sp_params)
    scoped[param] = ",".join(salesmen)
    return scoped
