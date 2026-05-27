"""Monthly Salesman Report builder.

Mirrors the live ``reports/salesman/builder.py`` row schema so the test
sandbox shows the same per-(customer, salesman) comparison columns the
users already trust. Source data is the ``invoiced_order_charges`` SP
(HTTP Reporting API) -- one flat row per invoice header. We do the
month bucketing in-process, the same way the live builder does, and
emit one tab per calendar month.

Live mapping (live -> test column / field):

    Sales = Total Invoice - CC Charges - Freight Charges
    Grouping = (CustomerAccount, CustomerName, SalesmanNumber, Salesman)

Each month tab has the live's 12 columns:
    Sort Number, Cust. #, Customer Name,
    Sales <month> <year>, Sales <month> <last_year>,
    $ This Year to Last Year, % This Year to Last Year,
    Sales <year> Jan Thru <month>, Sales <last_year> Jan Thru <month>,
    $ YTD Diff, % YTD Diff,
    Sales YTD <year>, Sales YTD <last_year>,
    $ Full Year Diff, % Full Year Diff

We additionally surface Salesman + SalesmanNumber as columns so the
on-screen viewer can group by salesman to mimic the live per-salesman
sectioned look. Tabulator's "Group with totals" feature gives the
user the same shape interactively, and Excel export preserves the
grouping in-place.
"""
from __future__ import annotations

import calendar
import logging
import re
from typing import Any, Iterable

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers (lifted from invoiced.py -- keep them local so tab builders don't
# pull in invoiced's tab definitions accidentally).
# ---------------------------------------------------------------------------


def _num(v: Any) -> float:
    if v is None or v == "" or v == "NULL":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _str(v: Any) -> str:
    if v is None or v == "NULL":
        return ""
    return str(v)


def _first(raw: dict, *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", "NULL"):
            return value
    return None


def _sm_key(sales_group: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (sales_group or "").strip().lower())


def _load_salesman_map() -> dict[str, dict]:
    try:
        from test.webapp.db import list_salesman_map
        rows = list_salesman_map()
    except Exception:
        log.exception("salesman: failed to load app_salesmen")
        return {}
    out: dict[str, dict] = {}
    for r in rows or []:
        key = (r.get("key") or "").strip().lower()
        if not key:
            continue
        out[key] = {
            "number":       (r.get("number") or "").strip(),
            "full_name":    (r.get("full_name") or "").strip(),
            "display_name": (r.get("display_name") or "").strip(),
        }
    return out


# ---------------------------------------------------------------------------
# Row normalisation
# ---------------------------------------------------------------------------


def _norm_row(raw: dict, sm_map: dict[str, dict]) -> dict | None:
    """Map an invoiced_order_charges row onto the salesman-report shape.

    Returns None for rows missing an InvoiceDate (the bucketing can't
    use them and the live builder drops them via ``pd.to_datetime
    errors='coerce'``).
    """
    date_raw = _first(raw, "InvoiceDate", "Invoice Date", "DocumentDate")
    if not date_raw:
        return None
    date_str = str(date_raw)[:10]
    try:
        year = int(date_str[:4])
        month = int(date_str[5:7])
    except (TypeError, ValueError):
        return None

    amount = _num(_first(raw, "Amount", "SubTotal", "SubTotalAmount"))
    cc_chg = _num(_first(raw, "SH_ProcessingFeesCharges", "ProcessingFeesCharges", "CCCharges", "CC Charges"))
    freight_chg = _num(_first(raw, "SH_FreightCharges", "SL_FreightCharges", "FreightCharges", "Freight Charges"))
    # Tariff lives at the LINE level in invoiced_order_charges
    # (``SL_TariffCharges``); the header-level alias is always null.
    # Same fix as invoiced._norm_row -- see comment there for context.
    tariff_chg = _num(_first(raw, "SL_TariffCharges", "SH_TariffCharges", "TariffCharges", "Tariff Charges"))

    # Live formula: Sales = Total Invoice - CC Charges - Freight Charges
    # (Total Invoice = SubTotal + Tariff + Freight + CC).
    total_invoice = amount + tariff_chg + freight_chg + cc_chg
    sales = round(total_invoice - cc_chg - freight_chg, 2)

    salesgroup = _str(_first(raw, "SalesGroup", "salesgroup", "Salesman"))
    sm = sm_map.get(_sm_key(salesgroup)) if salesgroup else None
    if sm:
        salesman_label = sm.get("display_name") or sm.get("full_name") or salesgroup
        salesman_number = sm.get("number") or ""
    else:
        salesman_label = salesgroup
        salesman_number = ""

    return {
        "_year":           year,
        "_month":          month,
        "CustomerAccount": _str(_first(raw, "InvoiceAccount", "CustomerAccount", "customeraccount", "AccountNum")),
        "CustomerName":    _str(_first(raw, "CustomerName", "customername", "Name")),
        "Salesman":        salesman_label,
        "SalesmanNumber":  salesman_number,
        "SalesGroup":      salesgroup,
        "Sales":           sales,
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


_GROUP_KEYS = ("CustomerAccount", "Salesman")


def _pad_num(n: str) -> str:
    """Mirror live ``pad_salesman_number``: zero-pad numeric salesman
    IDs to 4 chars for stable lexicographic sort. Non-numeric values
    are returned as-is.
    """
    s = (n or "").strip()
    if s.isdigit():
        return s.zfill(4)
    return s


def _build_month_tab(
    invoices: list[dict],
    year: int,
    month: int,
) -> dict:
    last_year = year - 1
    mon_full = calendar.month_name[month]

    # Active set: every (customer, salesman) pair with sales in either
    # year so customers who only show up in the prior year still appear
    # as rows with $0 in the current year.
    active: dict[tuple, dict] = {}

    def _bucket(key: tuple, meta: dict) -> dict:
        bucket = active.get(key)
        if bucket is None:
            bucket = {
                **meta,
                "Sales_Current":          0.0,
                "Sales_Prior":            0.0,
                "Sales_YTD_Current":      0.0,
                "Sales_YTD_Prior":        0.0,
                "Sales_FullYear_Current": 0.0,
                "Sales_FullYear_Prior":   0.0,
            }
            active[key] = bucket
        return bucket

    for inv in invoices:
        iyear = inv["_year"]
        imonth = inv["_month"]
        if iyear not in (year, last_year):
            continue
        key = (inv["CustomerAccount"], inv["Salesman"])
        meta = {
            "CustomerAccount": inv["CustomerAccount"],
            "CustomerName":    inv["CustomerName"],
            "Salesman":        inv["Salesman"],
            "SalesmanNumber":  inv["SalesmanNumber"],
            "SalesGroup":      inv["SalesGroup"],
        }
        b = _bucket(key, meta)
        s = inv["Sales"]
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

    rows = []
    for b in active.values():
        for f in ("Sales_Current", "Sales_Prior", "Sales_YTD_Current",
                  "Sales_YTD_Prior", "Sales_FullYear_Current",
                  "Sales_FullYear_Prior"):
            b[f] = round(b[f], 2)

        month_diff = round(b["Sales_Current"] - b["Sales_Prior"], 2)
        ytd_diff = round(b["Sales_YTD_Current"] - b["Sales_YTD_Prior"], 2)
        full_diff = round(b["Sales_FullYear_Current"] - b["Sales_FullYear_Prior"], 2)

        month_pct = (month_diff / b["Sales_Prior"]) if b["Sales_Prior"] else 0.0
        ytd_pct = (ytd_diff / b["Sales_YTD_Prior"]) if b["Sales_YTD_Prior"] else 0.0
        full_pct = (full_diff / b["Sales_FullYear_Prior"]) if b["Sales_FullYear_Prior"] else 0.0

        rows.append({
            "Salesman":                            b["Salesman"],
            "SalesmanNumber":                      b["SalesmanNumber"],
            "Cust. #":                             b["CustomerAccount"],
            "Customer Name":                       b["CustomerName"],
            f"Sales {mon_full} {year}":            b["Sales_Current"],
            f"Sales {mon_full} {last_year}":       b["Sales_Prior"],
            "$ This Year to Last Year":            month_diff,
            "% This Year to Last Year":            month_pct,
            f"Sales {year} Jan Thru {mon_full}":   b["Sales_YTD_Current"],
            f"Sales {last_year} Jan Thru {mon_full}": b["Sales_YTD_Prior"],
            "$ YTD Diff":                          ytd_diff,
            "% YTD Diff":                          ytd_pct,
            f"Sales Year to Date {year}":          b["Sales_FullYear_Current"],
            f"Sales Year to Date {last_year}":     b["Sales_FullYear_Prior"],
            "$ Full Year Diff":                    full_diff,
            "% Full Year Diff":                    full_pct,
            "_sort":                               _pad_num(b["SalesmanNumber"]) or b["Salesman"].lower(),
        })

    rows.sort(key=lambda r: (r["_sort"], r["Cust. #"]))
    for r in rows:
        r.pop("_sort", None)

    columns = [
        {"field": "Salesman",                            "header": "Salesman",                            "type": "text"},
        {"field": "SalesmanNumber",                      "header": "Salesman #",                          "type": "text"},
        {"field": "Cust. #",                             "header": "Cust. #",                             "type": "text"},
        {"field": "Customer Name",                       "header": "Customer Name",                       "type": "text"},
        {"field": f"Sales {mon_full} {year}",            "header": f"Sales {mon_full} {year}",            "type": "money"},
        {"field": f"Sales {mon_full} {last_year}",       "header": f"Sales {mon_full} {last_year}",       "type": "money"},
        {"field": "$ This Year to Last Year",            "header": "$ This Year to Last Year",            "type": "money"},
        {"field": "% This Year to Last Year",            "header": "% This Year to Last Year",            "type": "percent"},
        {"field": f"Sales {year} Jan Thru {mon_full}",   "header": f"Sales {year} Jan Thru {mon_full}",   "type": "money"},
        {"field": f"Sales {last_year} Jan Thru {mon_full}", "header": f"Sales {last_year} Jan Thru {mon_full}", "type": "money"},
        {"field": "$ YTD Diff",                          "header": "$ YTD Diff",                          "type": "money"},
        {"field": "% YTD Diff",                          "header": "% YTD Diff",                          "type": "percent"},
        {"field": f"Sales Year to Date {year}",          "header": f"Sales Year to Date {year}",          "type": "money"},
        {"field": f"Sales Year to Date {last_year}",     "header": f"Sales Year to Date {last_year}",     "type": "money"},
        {"field": "$ Full Year Diff",                    "header": "$ Full Year Diff",                    "type": "money"},
        {"field": "% Full Year Diff",                    "header": "% Full Year Diff",                    "type": "percent"},
    ]

    return {
        "key":     f"{calendar.month_abbr[month]}".lower(),
        "name":    calendar.month_abbr[month],
        "columns": columns,
        "rows":    rows,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build(rows: Iterable[dict], *, year: int) -> list[dict]:
    """Turn flat invoiced_order_charges rows into 12 month tabs (Jan-Dec)."""
    sm_map = _load_salesman_map()
    normalized = []
    for r in rows:
        nr = _norm_row(r, sm_map)
        if nr is not None:
            normalized.append(nr)
    return [_build_month_tab(normalized, year, m) for m in range(1, 13)]
