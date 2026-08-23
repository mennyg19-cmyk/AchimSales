"""Monthly Salesman YoY builder (pure).

Source: ``rpt.usp_monthly_salesman_yoy`` (catalog ``monthly_salesman_yoy``).
Sales basis is Total Invoice (server-side). The SP returns one wide row per
salesman + customer with Jan–Dec this/last year, YTD, and full-year columns.

This builder only reshapes that dataset into the existing 12 month tabs
(Jan–Dec) so the viewer/export stay workbook-style. No invoice math here.
"""

from __future__ import annotations

import calendar
import re
from typing import Any, Iterable, Sequence

from report_engine.lib import num, salesman_key

SALESMAN_NAME_COLUMN = "SalesmanName"
SALESMAN_ID_COLUMN = "SalesmanId"

def _pad_salesman_number(number: str) -> str:
    s = (number or "").strip()
    return s.zfill(4) if s.isdigit() else s


def _norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _lookup(row: dict, *candidates: str) -> Any:
    """Case/spacing-insensitive column get. Prefer exact, then normalized."""
    for cand in candidates:
        if cand in row:
            return row[cand]
    wanted = {_norm_key(c) for c in candidates}
    for key, value in row.items():
        if _norm_key(str(key)) in wanted:
            return value
    return None


def _money(row: dict, *candidates: str) -> float:
    return round(num(_lookup(row, *candidates)), 2)


def _month_ty_candidates(month: int) -> tuple[str, ...]:
    abbr, name = calendar.month_abbr[month], calendar.month_name[month]
    return (
        f"{abbr} This Year",
        f"{name} This Year",
        f"{abbr}ThisYear",
        f"{abbr}_This_Year",
        f"{abbr} TY",
        f"{abbr}TY",
    )


def _month_ly_candidates(month: int) -> tuple[str, ...]:
    abbr, name = calendar.month_abbr[month], calendar.month_name[month]
    return (
        f"{abbr} Last Year",
        f"{name} Last Year",
        f"{abbr}LastYear",
        f"{abbr}_Last_Year",
        f"{abbr} LY",
        f"{abbr}LY",
        f"{abbr} Prior Year",
        f"{name} Prior Year",
    )


def _month_sales(row: dict, month: int) -> tuple[float, float]:
    return (
        _money(row, *_month_ty_candidates(month)),
        _money(row, *_month_ly_candidates(month)),
    )


def _ytd_from_months(row: dict, through_month: int) -> tuple[float, float]:
    """Sum Jan..through from monthly columns (each month tab needs its own YTD)."""
    ty = ly = 0.0
    for m in range(1, through_month + 1):
        a, b = _month_sales(row, m)
        ty += a
        ly += b
    return round(ty, 2), round(ly, 2)


def _full_year(row: dict) -> tuple[float, float]:
    ty = _money(
        row,
        "Full Year This Year",
        "FullYearThisYear",
        "Full Year TY",
        "Sales Year to Date Current",  # unlikely; fallback below
    )
    ly = _money(
        row,
        "Full Year Last Year",
        "FullYearLastYear",
        "Full Year LY",
        "Full Year Prior Year",
    )
    if ty == 0.0 and ly == 0.0:
        # SP may only expose months; sum all twelve.
        return _ytd_from_months(row, 12)
    return ty, ly


def _pct(diff: float, prior: float) -> float:
    return (diff / prior) if prior else 0.0


def _columns(year: int, month: int) -> list[dict]:
    mon = calendar.month_name[month]
    prior = year - 1
    return [
        {"field": "Sort Number", "header": "Sort Number", "type": "text"},
        {"field": "Salesman", "header": "Salesman", "type": "text"},
        {"field": "Cust. #", "header": "Cust. #", "type": "text"},
        {"field": "Customer Name", "header": "Customer Name", "type": "text"},
        {"field": f"Sales {mon} {year}", "header": f"Sales {mon} {year}", "type": "money"},
        {"field": f"Sales {mon} {prior}", "header": f"Sales {mon} {prior}", "type": "money"},
        {"field": "$ This Year to Last Year", "header": "$ This Year to Last Year", "type": "money"},
        {"field": "% This Year to Last Year", "header": "% This Year to Last Year", "type": "percent"},
        {"field": f"Sales {year} Jan Thru {mon}", "header": f"Sales {year} Jan Thru {mon}", "type": "money"},
        {"field": f"Sales {prior} Jan Thru {mon}", "header": f"Sales {prior} Jan Thru {mon}", "type": "money"},
        {"field": "$ This Year to Last Year (YTD)", "header": "$ This Year to Last Year (YTD)", "type": "money"},
        {"field": "% This Year to Last Year (YTD)", "header": "% This Year to Last Year (YTD)", "type": "percent"},
        {"field": f"Sales Year to Date {year}", "header": f"Sales Year to Date {year}", "type": "money"},
        {"field": f"Sales Year to Date {prior}", "header": f"Sales Year to Date {prior}", "type": "money"},
        {"field": "$ This Year to Last Year (YTD Full Year)",
         "header": "$ This Year to Last Year (YTD Full Year)", "type": "money"},
        {"field": "% This Year to Last Year (YTD Full Year)",
         "header": "% This Year to Last Year (YTD Full Year)", "type": "percent"},
    ]


_TEXT_KEYS = {
    _norm_key(k) for k in (
        "SalesmanId", "SalesmanName", "Salesman", "SalesGroup",
        "CustomerAccount", "CustomerName", "Cust. #", "Customer Name", "Name",
    )
}


def clean_rows(rows: Iterable[dict]) -> list[dict]:
    """Keep SP keys; coerce non-label cells to floats when numeric."""
    out: list[dict] = []
    for raw in rows:
        cleaned: dict[str, Any] = {}
        for key, value in raw.items():
            header = str(key)
            if _norm_key(header) in _TEXT_KEYS:
                cleaned[header] = "" if value is None else value
            else:
                cleaned[header] = round(num(value), 2)
        out.append(cleaned)
    return out

def filter_rows_by_salesman(rows: list[dict], visible_keys) -> list[dict]:
    """Scope backstop on SalesmanName (and SalesmanId as secondary)."""
    if visible_keys is None:
        return rows
    allowed = {salesman_key(k) for k in visible_keys}
    kept: list[dict] = []
    for row in rows:
        name = str(_lookup(row, SALESMAN_NAME_COLUMN, "Salesman", "SalesGroup") or "")
        sid = str(_lookup(row, SALESMAN_ID_COLUMN, "SalesmanNumber") or "")
        if salesman_key(name) in allowed or salesman_key(sid) in allowed:
            kept.append(row)
    return kept


def _build_month_tab(rows: Sequence[dict], year: int, month: int) -> dict:
    mon = calendar.month_name[month]
    prior = year - 1
    out_rows: list[dict] = []
    for row in rows:
        cur, prv = _month_sales(row, month)
        ytd_cur, ytd_prv = _ytd_from_months(row, month)
        full_cur, full_prv = _full_year(row)
        month_diff = round(cur - prv, 2)
        ytd_diff = round(ytd_cur - ytd_prv, 2)
        full_diff = round(full_cur - full_prv, 2)
        sid = str(_lookup(row, SALESMAN_ID_COLUMN, "SalesmanNumber") or "").strip()
        sname = str(_lookup(row, SALESMAN_NAME_COLUMN, "Salesman") or "").strip()
        acct = str(_lookup(row, "CustomerAccount", "Cust. #", "AccountNum") or "").strip()
        cname = str(_lookup(row, "CustomerName", "Customer Name", "Name") or "").strip()
        sort_number = _pad_salesman_number(sid)
        out_rows.append({
            "Sort Number": sort_number,
            "Salesman": sname,
            "SalesmanNumber": sid,
            "Cust. #": acct,
            "Customer Name": cname,
            f"Sales {mon} {year}": cur,
            f"Sales {mon} {prior}": prv,
            "$ This Year to Last Year": month_diff,
            "% This Year to Last Year": _pct(month_diff, prv),
            f"Sales {year} Jan Thru {mon}": ytd_cur,
            f"Sales {prior} Jan Thru {mon}": ytd_prv,
            "$ This Year to Last Year (YTD)": ytd_diff,
            "% This Year to Last Year (YTD)": _pct(ytd_diff, ytd_prv),
            f"Sales Year to Date {year}": full_cur,
            f"Sales Year to Date {prior}": full_prv,
            "$ This Year to Last Year (YTD Full Year)": full_diff,
            "% This Year to Last Year (YTD Full Year)": _pct(full_diff, full_prv),
            "_sort": sort_number or sname.lower(),
        })

    out_rows.sort(key=lambda r: (r["_sort"], r["Cust. #"] or ""))
    for r in out_rows:
        r.pop("_sort", None)

    return {
        "key": calendar.month_abbr[month].lower(),
        "name": calendar.month_abbr[month],
        "columns": _columns(year, month),
        "rows": out_rows,
    }


def build(rows: Sequence[dict], *, year: int) -> list[dict]:
    """Build 12 month tabs (Jan–Dec) from ``monthly_salesman_yoy`` rows."""
    return [_build_month_tab(rows, year, m) for m in range(1, 13)]
