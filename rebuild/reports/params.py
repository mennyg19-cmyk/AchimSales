"""Turns the viewer's filter choices into stored-procedure parameters."""

# === What's in this file ===
# The viewer sends simple filters (a named period, optional custom dates, a
# customer, a salesman). The stored procedure wants specific PascalCase
# parameters. This is the one place that translates between the two, per report.
#
# resolve_window() -- a named period (or custom dates) -> (start_date, end_date)
# translate() -- filter choices -> the SP params for a report (raises if unknown)

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
    s = text(value)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None


def _translate_invoiced(filters: dict) -> dict[str, Any]:
    start, end = resolve_window(filters)
    out: dict[str, Any] = {}
    if start:
        out["InvoiceDateFrom"] = start.isoformat()
    if end:
        out["InvoiceDateTo"] = end.isoformat()
    customers = filters.get("customers")
    if isinstance(customers, (list, tuple, set)):
        accounts = [text(c) for c in customers if text(c)]
    elif customers:
        accounts = [text(customers)]
    else:
        accounts = []
    if len(accounts) == 1:
        out["CustomerAccount"] = accounts[0]
    salesman = filters.get("salesman")
    if salesman:
        out["Salesman"] = ",".join(text(s) for s in salesman) if isinstance(salesman, (list, tuple, set)) else text(salesman)
    return out


_TRANSLATORS = {
    "invoiced": _translate_invoiced,
}


def translate(report_key: str, filters: Optional[dict]) -> dict[str, Any]:
    translator = _TRANSLATORS.get(report_key)
    if translator is None:
        raise KeyError(f"No parameter translator for report {report_key!r}")
    return translator(filters or {})
