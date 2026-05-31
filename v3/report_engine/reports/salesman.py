"""Monthly Salesman report builder (pure).

Same source as the invoiced report (`invoiced_order_charges` SP -> InvoiceChargeFact),
so it reuses `sources.invoiced`. Produces 12 month tabs (Jan-Dec); each tab compares
the current year to the prior year for every (customer, salesman) pair.

Core metric (matches LIVE `reports/salesman/builder.py`):
    Sales = Total Invoice - CC Charges - Freight Charges   (== SubTotal + Tariff)

Per month tab, per (customer, salesman):
    Sales <mon> <yr> / <prior>, $/% month diff,
    Sales <yr> Jan Thru <mon> / <prior>, $/% YTD diff,
    Sales Year to Date <yr> / <prior> (full-year totals), $/% full-year diff.
Active rows = any (customer, salesman) with sales in either year.
"""

from __future__ import annotations

import calendar
from typing import Iterable, Mapping

from report_engine.facts import InvoiceChargeFact, SalesmanFact
from report_engine.lib import num, salesman_key

_COMPARISON_FIELDS = (
    "Sales_Current", "Sales_Prior", "Sales_YTD_Current", "Sales_YTD_Prior",
    "Sales_FullYear_Current", "Sales_FullYear_Prior",
)


def _pad_salesman_number(number: str) -> str:
    """Zero-pad numeric salesman IDs to 4 chars for stable sort (LIVE pad_salesman_number)."""
    s = (number or "").strip()
    return s.zfill(4) if s.isdigit() else s


def _resolve(sales_group: str, salesmen: Mapping[str, SalesmanFact]) -> tuple[str, str]:
    """(label, number) for a SalesGroup. Empty group -> ('', '')."""
    sm = salesmen.get(salesman_key(sales_group)) if sales_group else None
    if sm:
        return (sm.display_name or sm.full_name or sales_group, sm.number)
    return (sales_group, "")


def _normalize(fact: InvoiceChargeFact, salesmen: Mapping[str, SalesmanFact]) -> dict | None:
    """Fact -> {year, month, customer, salesman, sales}; None if date unparseable."""
    d = fact.invoice_date
    if not (isinstance(d, str) and len(d) >= 7 and d[4] == "-"):
        return None
    try:
        year = int(d[:4])
        month = int(d[5:7])
    except ValueError:
        return None
    label, number = _resolve(fact.sales_group, salesmen)
    return {
        "year": year,
        "month": month,
        "CustomerAccount": fact.customer_account,
        "CustomerName": fact.customer_name,
        "Salesman": label,
        "SalesmanNumber": number,
        # LIVE: Sales = Total Invoice - CC - Freight.
        "Sales": round(fact.total - fact.cc - fact.freight, 2),
    }


def _columns(year: int, month: int) -> list[dict]:
    mon = calendar.month_name[month]
    prior = year - 1
    return [
        {"field": "Salesman", "header": "Salesman", "type": "text"},
        {"field": "SalesmanNumber", "header": "Salesman #", "type": "text"},
        {"field": "Cust. #", "header": "Cust. #", "type": "text"},
        {"field": "Customer Name", "header": "Customer Name", "type": "text"},
        {"field": f"Sales {mon} {year}", "header": f"Sales {mon} {year}", "type": "money"},
        {"field": f"Sales {mon} {prior}", "header": f"Sales {mon} {prior}", "type": "money"},
        {"field": "$ This Year to Last Year", "header": "$ This Year to Last Year", "type": "money"},
        {"field": "% This Year to Last Year", "header": "% This Year to Last Year", "type": "percent"},
        {"field": f"Sales {year} Jan Thru {mon}", "header": f"Sales {year} Jan Thru {mon}", "type": "money"},
        {"field": f"Sales {prior} Jan Thru {mon}", "header": f"Sales {prior} Jan Thru {mon}", "type": "money"},
        {"field": "$ YTD Diff", "header": "$ YTD Diff", "type": "money"},
        {"field": "% YTD Diff", "header": "% YTD Diff", "type": "percent"},
        {"field": f"Sales Year to Date {year}", "header": f"Sales Year to Date {year}", "type": "money"},
        {"field": f"Sales Year to Date {prior}", "header": f"Sales Year to Date {prior}", "type": "money"},
        {"field": "$ Full Year Diff", "header": "$ Full Year Diff", "type": "money"},
        {"field": "% Full Year Diff", "header": "% Full Year Diff", "type": "percent"},
    ]


def _build_month_tab(lines: list[dict], year: int, month: int) -> dict:
    prior = year - 1
    mon = calendar.month_name[month]
    buckets: dict[tuple, dict] = {}

    for ln in lines:
        iyear = ln["year"]
        if iyear not in (year, prior):
            continue
        key = (ln["CustomerAccount"], ln["CustomerName"],
               ln["SalesmanNumber"], ln["Salesman"])
        b = buckets.get(key)
        if b is None:
            b = {
                "CustomerAccount": ln["CustomerAccount"],
                "CustomerName": ln["CustomerName"],
                "SalesmanNumber": ln["SalesmanNumber"],
                "Salesman": ln["Salesman"],
                **{f: 0.0 for f in _COMPARISON_FIELDS},
            }
            buckets[key] = b
        s = ln["Sales"]
        imonth = ln["month"]
        if iyear == year:
            b["Sales_FullYear_Current"] += s
            if imonth == month:
                b["Sales_Current"] += s
            if imonth <= month:
                b["Sales_YTD_Current"] += s
        else:
            b["Sales_FullYear_Prior"] += s
            if imonth == month:
                b["Sales_Prior"] += s
            if imonth <= month:
                b["Sales_YTD_Prior"] += s

    rows: list[dict] = []
    for b in buckets.values():
        for f in _COMPARISON_FIELDS:
            b[f] = round(b[f], 2)
        month_diff = round(b["Sales_Current"] - b["Sales_Prior"], 2)
        ytd_diff = round(b["Sales_YTD_Current"] - b["Sales_YTD_Prior"], 2)
        full_diff = round(b["Sales_FullYear_Current"] - b["Sales_FullYear_Prior"], 2)
        rows.append({
            "Salesman": b["Salesman"],
            "SalesmanNumber": b["SalesmanNumber"],
            "Cust. #": b["CustomerAccount"],
            "Customer Name": b["CustomerName"],
            f"Sales {mon} {year}": b["Sales_Current"],
            f"Sales {mon} {prior}": b["Sales_Prior"],
            "$ This Year to Last Year": month_diff,
            "% This Year to Last Year": (month_diff / b["Sales_Prior"]) if b["Sales_Prior"] else 0.0,
            f"Sales {year} Jan Thru {mon}": b["Sales_YTD_Current"],
            f"Sales {prior} Jan Thru {mon}": b["Sales_YTD_Prior"],
            "$ YTD Diff": ytd_diff,
            "% YTD Diff": (ytd_diff / b["Sales_YTD_Prior"]) if b["Sales_YTD_Prior"] else 0.0,
            f"Sales Year to Date {year}": b["Sales_FullYear_Current"],
            f"Sales Year to Date {prior}": b["Sales_FullYear_Prior"],
            "$ Full Year Diff": full_diff,
            "% Full Year Diff": (full_diff / b["Sales_FullYear_Prior"]) if b["Sales_FullYear_Prior"] else 0.0,
            "_sort": _pad_salesman_number(b["SalesmanNumber"]) or (b["Salesman"] or "").lower(),
        })

    rows.sort(key=lambda r: (r["_sort"], r["Cust. #"] or ""))
    for r in rows:
        r.pop("_sort", None)

    return {
        "key": calendar.month_abbr[month].lower(),
        "name": calendar.month_abbr[month],
        "columns": _columns(year, month),
        "rows": rows,
    }


def build(facts: Iterable[InvoiceChargeFact], *,
          salesmen: Mapping[str, SalesmanFact], year: int) -> list[dict]:
    """Build 12 month tabs (Jan-Dec) for the given report year."""
    lines = [n for n in (_normalize(f, salesmen) for f in facts) if n is not None]
    return [_build_month_tab(lines, year, m) for m in range(1, 13)]
