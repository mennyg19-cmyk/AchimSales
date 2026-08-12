"""One-shot reconcile: monthly_salesman_yoy vs invoiced_report Total Invoice.

Compares grand totals, by-customer, and month/year slices (This Year, Last Year,
YTD, Full Year) so salesman money can be signed perfect against TEST invoiced.

Fetches two invoiced windows of similar size (this-year through end_day, and
prior-year Jan..through) so the diagnostic finishes under the App Service
gateway timeout. Full Year Last Year is checked as SP month-sum vs SP Full Year
column, plus months 1..through vs invoiced.
"""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from report_engine.dates import today_eastern
from report_engine.lib import iso_date, num


_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_TOL = 0.05


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s or "").strip().lower())


def _get(row: dict, *names: str):
    for n in names:
        if n in row:
            return row[n]
    wanted = {_norm(n) for n in names}
    for k, v in row.items():
        if _norm(k) in wanted:
            return v
    return None


def _money(row: dict, *names: str) -> float:
    return round(num(_get(row, *names)), 2)


def _invoice_total(row: dict) -> float:
    """Prefer Total Invoice; else SubTotal+Tariff+Freight+CC+Misc."""
    total = _get(row, "Total Invoice", "TotalInvoice", "InvoiceAmount")
    sub = _get(row, "SubTotal Invoices", "SubTotal", "Amount", "subtotal")
    tar = _get(row, "Tariff Charges", "SL_TariffCharges", "Tariff")
    fre = _get(row, "Freight Charges", "SH_FreightCharges", "Freight")
    cc = _get(row, "CC Charges", "SH_ProcessingFeesCharges", "CC")
    misc = _get(row, "Misc Charges", "Misc")
    if any(x is not None for x in (tar, fre, cc, misc)) and sub is not None:
        return round(num(sub) + num(tar) + num(fre) + num(cc) + num(misc), 2)
    if total is not None:
        return round(num(total), 2)
    return round(num(sub), 2)


def _invoice_date(row: dict) -> date | None:
    """Parse InvoiceDate using the same iso_date helper as the rest of v3."""
    raw = _get(row, "InvoiceDate", "Invoice Date", "InvoiceDate1", "Date")
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    iso = iso_date(raw)
    if not iso or len(iso) < 10 or iso[4] != "-":
        return None
    try:
        return date.fromisoformat(iso[:10])
    except ValueError:
        return None


def _salesman_ytd(row: dict, through: int) -> float:
    ytd = _money(row, "YTD This Year", "YTDThisYear", "Ytd This Year")
    keys = {_norm(k) for k in row}
    if "ytdthisyear" in keys:
        return ytd
    total = 0.0
    for m in _MONTH_ABBR[:through]:
        total += _money(row, f"{m} This Year", f"{m}ThisYear")
    return round(total, 2)


def _salesman_month(row: dict, month: int, *, which: str) -> float:
    abbr = _MONTH_ABBR[month - 1]
    if which == "ty":
        return _money(row, f"{abbr} This Year", f"{abbr}ThisYear")
    return _money(row, f"{abbr} Last Year", f"{abbr}LastYear")


def _compare_money_maps(
    left: dict[str, float],
    right: dict[str, float],
    *,
    left_label: str,
    right_label: str,
    sample_limit: int = 20,
) -> dict:
    matched = diffs = left_only = right_only = 0
    samples: list[dict] = []
    keys = set(left) | set(right)
    for key in sorted(k for k in keys if k):
        lv = left.get(key, 0.0)
        rv = right.get(key, 0.0)
        if abs(lv - rv) <= _TOL:
            if abs(lv) > _TOL or abs(rv) > _TOL:
                matched += 1
            continue
        if abs(lv) > _TOL and abs(rv) <= _TOL:
            left_only += 1
            kind = f"{left_label}_only"
        elif abs(rv) > _TOL and abs(lv) <= _TOL:
            right_only += 1
            kind = f"{right_label}_only"
        else:
            diffs += 1
            kind = "amount_diff"
        if len(samples) < sample_limit:
            samples.append({
                "type": kind, "key": key,
                left_label: lv, right_label: rv,
                "delta": round(lv - rv, 2),
            })
    return {
        "matched_within_5c": matched,
        "amount_diffs": diffs,
        f"{left_label}_only": left_only,
        f"{right_label}_only": right_only,
        "sample_mismatches": samples,
    }


def _slice_ok(sm_sum: float, inv_sum: float, by_acct: dict) -> bool:
    return (
        abs(sm_sum - inv_sum) <= _TOL
        and by_acct["amount_diffs"] == 0
        and by_acct.get("salesman_only", 0) == 0
        and by_acct.get("invoiced_only", 0) == 0
    )


def _month_result(m: int, year: int, sm_map: dict[str, float], inv_map: dict[str, float]) -> dict:
    sm_sum = round(sum(sm_map.values()), 2)
    inv_sum = round(sum(inv_map.values()), 2)
    by_acct = _compare_money_maps(
        sm_map, inv_map, left_label="salesman", right_label="invoiced",
    )
    ok = _slice_ok(sm_sum, inv_sum, by_acct)
    out = {
        "month": m,
        "label": f"{_MONTH_ABBR[m - 1]} {year}",
        "salesman_sum": sm_sum,
        "invoiced_sum": inv_sum,
        "delta": round(sm_sum - inv_sum, 2),
        "ok": ok,
        "by_customer": {
            "matched_within_5c": by_acct["matched_within_5c"],
            "amount_diffs": by_acct["amount_diffs"],
            "salesman_only": by_acct["salesman_only"],
            "invoiced_only": by_acct["invoiced_only"],
        },
    }
    if not ok:
        out["by_customer"]["sample_mismatches"] = by_acct["sample_mismatches"]
    return out


def reconcile(
    client,
    *,
    year: int | None = None,
    through_month: int | None = None,
    scope: str = "all",
    only_month: int | None = None,
) -> dict:
    """Fetch SPs via ReportingApiClient; compare YTD + monthly/yearly slices.

    scope: ``ty`` this-year only, ``ly`` last-year only, ``all`` both.
    only_month: when set with scope=ty|ly, fetch/compare that calendar month only
    (keeps each diagnostic call under the App Service gateway limit).
    """
    today = today_eastern()
    year = year or today.year
    through = through_month or (today.month if year == today.year else 12)
    through = max(1, min(12, int(through)))
    prior = year - 1
    scope = (scope or "all").strip().lower()
    if scope not in ("ty", "ly", "all"):
        scope = "all"
    want_ty = scope in ("ty", "all")
    want_ly = scope in ("ly", "all")
    if only_month is not None:
        only_month = max(1, min(12, int(only_month)))

    if year == today.year and through == today.month:
        end_day = today
    else:
        end_day = date(year, through, calendar.monthrange(year, through)[1])
    prior_end = date(prior, through, calendar.monthrange(prior, through)[1])

    sm = client.run_report(
        "monthly_salesman_yoy",
        {"ReportYear": year, "ThroughMonth": through},
    )
    inv_ty_rows: list = []
    inv_ly_rows: list = []
    inv_ty_cols: list = []

    def _month_window(y: int, m: int) -> tuple[date, date]:
        start = date(y, m, 1)
        last = date(y, m, calendar.monthrange(y, m)[1])
        if y == today.year and m == today.month:
            last = min(last, today)
        return start, last

    if want_ty:
        if only_month is not None:
            start, last = _month_window(year, only_month)
            inv_ty = client.run_report(
                "invoiced_report",
                {
                    "InvoiceDateFrom": f"{start.isoformat()} 00:00:00",
                    "InvoiceDateTo": f"{last.isoformat()} 23:59:59",
                },
            )
        else:
            inv_ty = client.run_report(
                "invoiced_report",
                {
                    "InvoiceDateFrom": f"{year}-01-01 00:00:00",
                    "InvoiceDateTo": f"{end_day.isoformat()} 23:59:59",
                },
            )
        inv_ty_rows = inv_ty.rows or []
        inv_ty_cols = list(inv_ty.columns or [])[:40]
    if want_ly:
        if only_month is not None:
            start, last = _month_window(prior, only_month)
            inv_ly = client.run_report(
                "invoiced_report",
                {
                    "InvoiceDateFrom": f"{start.isoformat()} 00:00:00",
                    "InvoiceDateTo": f"{last.isoformat()} 23:59:59",
                },
            )
        else:
            inv_ly = client.run_report(
                "invoiced_report",
                {
                    "InvoiceDateFrom": f"{prior}-01-01 00:00:00",
                    "InvoiceDateTo": f"{prior_end.isoformat()} 23:59:59",
                },
            )
        inv_ly_rows = inv_ly.rows or []

    sm_rows = sm.rows or []

    sm_ytd: dict[tuple[str, str], float] = {}
    sm_by_sm: dict[str, float] = defaultdict(float)
    sm_by_acct: dict[str, float] = defaultdict(float)
    sm_month_ty: dict[int, dict[str, float]] = {m: defaultdict(float) for m in range(1, 13)}
    sm_month_ly: dict[int, dict[str, float]] = {m: defaultdict(float) for m in range(1, 13)}
    sm_ytd_ly_by_acct: dict[str, float] = defaultdict(float)
    sm_full_ty_by_acct: dict[str, float] = defaultdict(float)
    sm_full_ly_by_acct: dict[str, float] = defaultdict(float)
    sm_ytd_ly_sum = sm_full_ty_sum = sm_full_ly_sum = 0.0
    sm_ly_months_sum = 0.0  # Jan–Dec Last Year columns (SP self-check vs Full Year LY)

    for r in sm_rows:
        sid = str(_get(r, "SalesmanId", "SalesmanNumber") or "").strip()
        sname = str(_get(r, "SalesmanName", "Salesman") or "").strip()
        sm_key = sid or sname
        acct = str(_get(r, "CustomerAccount", "Cust. #") or "").strip()
        ytd = _salesman_ytd(r, through)
        pair = (_norm(sm_key), acct)
        sm_ytd[pair] = round(sm_ytd.get(pair, 0.0) + ytd, 2)
        sm_by_sm[sm_key or "(blank)"] = round(sm_by_sm[sm_key or "(blank)"] + ytd, 2)
        sm_by_acct[acct] = round(sm_by_acct[acct] + ytd, 2)

        row_ly_year = 0.0
        for m in range(1, 13):
            ty = _salesman_month(r, m, which="ty")
            ly = _salesman_month(r, m, which="ly")
            row_ly_year = round(row_ly_year + ly, 2)
            if acct:
                sm_month_ty[m][acct] = round(sm_month_ty[m][acct] + ty, 2)
                sm_month_ly[m][acct] = round(sm_month_ly[m][acct] + ly, 2)

        ytd_ly = _money(r, "YTD Last Year", "YTDLastYear")
        full_ty = _money(r, "Full Year This Year", "FullYearThisYear")
        full_ly = _money(r, "Full Year Last Year", "FullYearLastYear")
        sm_ytd_ly_sum = round(sm_ytd_ly_sum + ytd_ly, 2)
        sm_full_ty_sum = round(sm_full_ty_sum + full_ty, 2)
        sm_full_ly_sum = round(sm_full_ly_sum + full_ly, 2)
        sm_ly_months_sum = round(sm_ly_months_sum + row_ly_year, 2)
        if acct:
            sm_ytd_ly_by_acct[acct] = round(sm_ytd_ly_by_acct[acct] + ytd_ly, 2)
            sm_full_ty_by_acct[acct] = round(sm_full_ty_by_acct[acct] + full_ty, 2)
            sm_full_ly_by_acct[acct] = round(sm_full_ly_by_acct[acct] + full_ly, 2)

    inv_month: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    inv_ytd: dict[tuple[str, str], float] = {}
    inv_by_sm: dict[str, float] = defaultdict(float)
    inv_by_acct: dict[str, float] = defaultdict(float)
    date_parsed = date_failed = 0
    date_fail_samples: list[str] = []

    for r in inv_ty_rows:
        total = _invoice_total(r)
        sm_raw = str(_get(r, "SalesGroup", "Salesman", "SalesmanName", "salesman") or "").strip()
        acct = str(_get(r, "CustomerAccount", "InvoiceAccount", "AccountNum") or "").strip()
        pair = (_norm(sm_raw), acct)
        inv_ytd[pair] = round(inv_ytd.get(pair, 0.0) + total, 2)
        inv_by_sm[sm_raw or "(blank)"] = round(inv_by_sm[sm_raw or "(blank)"] + total, 2)
        inv_by_acct[acct] = round(inv_by_acct[acct] + total, 2)
        d = _invoice_date(r)
        if d is not None and acct:
            date_parsed += 1
            inv_month[(d.year, d.month)][acct] = round(
                inv_month[(d.year, d.month)][acct] + total, 2
            )
        else:
            date_failed += 1
            if len(date_fail_samples) < 5:
                date_fail_samples.append(repr(_get(r, "InvoiceDate", "Invoice Date"))[:80])

    for r in inv_ly_rows:
        total = _invoice_total(r)
        acct = str(_get(r, "CustomerAccount", "InvoiceAccount", "AccountNum") or "").strip()
        d = _invoice_date(r)
        if d is not None and acct:
            date_parsed += 1
            inv_month[(d.year, d.month)][acct] = round(
                inv_month[(d.year, d.month)][acct] + total, 2
            )
        else:
            date_failed += 1
            if len(date_fail_samples) < 5:
                date_fail_samples.append(repr(_get(r, "InvoiceDate", "Invoice Date"))[:80])

    matched = amount_diffs = sm_only = inv_only = 0
    mismatches: list[dict] = []
    acct_cmp = {
        "matched_within_5c": 0, "amount_diffs": 0,
        "salesman_only": 0, "invoiced_only": 0, "sample_mismatches": [],
    }
    if want_ty and only_month is None:
        for key, sy in sm_ytd.items():
            iv = inv_ytd.get(key)
            if iv is None:
                if abs(sy) > _TOL:
                    sm_only += 1
                    if len(mismatches) < 20:
                        mismatches.append({
                            "type": "pair_salesman_only", "key": list(key), "salesman_ytd": sy,
                        })
                continue
            if abs(sy - iv) > _TOL:
                amount_diffs += 1
                if len(mismatches) < 25:
                    mismatches.append({
                        "type": "pair_amount_diff", "key": list(key),
                        "salesman_ytd": sy, "invoiced_total": iv, "delta": round(sy - iv, 2),
                    })
            else:
                matched += 1

        for key, iv in inv_ytd.items():
            if key not in sm_ytd and abs(iv) > _TOL:
                inv_only += 1
                if len(mismatches) < 40:
                    mismatches.append({
                        "type": "pair_invoiced_only", "key": list(key), "invoiced_total": iv,
                    })

        acct_cmp = _compare_money_maps(
            dict(sm_by_acct), dict(inv_by_acct),
            left_label="salesman", right_label="invoiced",
        )

    months_ty = []
    months_ly = []
    month_range = (
        [only_month] if only_month is not None
        else list(range(1, through + 1))
    )
    if want_ty:
        months_ty = [
            _month_result(m, year, dict(sm_month_ty[m]), dict(inv_month.get((year, m), {})))
            for m in month_range
            if m <= through
        ]
    if want_ly:
        months_ly = [
            _month_result(m, prior, dict(sm_month_ly[m]), dict(inv_month.get((prior, m), {})))
            for m in month_range
            if m <= through
        ]

    future_nonzero: list[dict] = []
    if want_ty and year == today.year:
        for m in range(through + 1, 13):
            sm_sum = round(sum(sm_month_ty[m].values()), 2)
            if abs(sm_sum) > _TOL:
                future_nonzero.append({
                    "month": m, "label": f"{_MONTH_ABBR[m - 1]} {year}",
                    "salesman_sum": sm_sum,
                })

    year_slices: list[dict] = []
    if only_month is None and want_ty:
        year_slices.append({
            "key": "ytd_this_year",
            "label": f"YTD This Year ({year} Jan–{_MONTH_ABBR[through - 1]})",
            "salesman_sum": round(sum(sm_by_acct.values()), 2),
            "invoiced_sum": round(sum(inv_by_acct.values()), 2),
            "delta": round(sum(sm_by_acct.values()) - sum(inv_by_acct.values()), 2),
            "ok": _slice_ok(
                round(sum(sm_by_acct.values()), 2),
                round(sum(inv_by_acct.values()), 2),
                acct_cmp,
            ),
            "by_customer": {
                "matched_within_5c": acct_cmp["matched_within_5c"],
                "amount_diffs": acct_cmp["amount_diffs"],
            },
        })
        inv_full_ty_sum = round(sum(inv_by_acct.values()), 2)
        full_ty_cmp = _compare_money_maps(
            dict(sm_full_ty_by_acct), dict(inv_by_acct),
            left_label="salesman", right_label="invoiced",
        )
        year_slices.append({
            "key": "full_year_this_year",
            "label": f"Full Year This Year ({year}) vs invoiced through {end_day.isoformat()}",
            "note": "Mid-year: Full Year TY should match YTD (future months empty).",
            "salesman_sum": sm_full_ty_sum,
            "invoiced_sum": inv_full_ty_sum,
            "delta": round(sm_full_ty_sum - inv_full_ty_sum, 2),
            "ok": _slice_ok(sm_full_ty_sum, inv_full_ty_sum, full_ty_cmp),
            "by_customer": {
                "matched_within_5c": full_ty_cmp["matched_within_5c"],
                "amount_diffs": full_ty_cmp["amount_diffs"],
                "sample_mismatches": full_ty_cmp["sample_mismatches"] if full_ty_cmp["amount_diffs"] else [],
            },
        })

    if only_month is None and want_ly:
        inv_ytd_ly_by_acct: dict[str, float] = defaultdict(float)
        for m in range(1, through + 1):
            for acct, val in inv_month.get((prior, m), {}).items():
                inv_ytd_ly_by_acct[acct] = round(inv_ytd_ly_by_acct[acct] + val, 2)
        inv_ytd_ly_sum = round(sum(inv_ytd_ly_by_acct.values()), 2)
        ytd_ly_cmp = _compare_money_maps(
            dict(sm_ytd_ly_by_acct), dict(inv_ytd_ly_by_acct),
            left_label="salesman", right_label="invoiced",
        )
        sm_ly_through_sum = round(
            sum(sum(sm_month_ly[m].values()) for m in range(1, through + 1)), 2
        )
        ytd_ly_vs_months_delta = round(sm_ytd_ly_sum - sm_ly_through_sum, 2)
        year_slices.append({
            "key": "ytd_last_year",
            "label": f"YTD Last Year ({prior} Jan–{_MONTH_ABBR[through - 1]})",
            "salesman_sum": sm_ytd_ly_sum,
            "invoiced_sum": inv_ytd_ly_sum,
            "delta": round(sm_ytd_ly_sum - inv_ytd_ly_sum, 2),
            "ok": _slice_ok(sm_ytd_ly_sum, inv_ytd_ly_sum, ytd_ly_cmp),
            "sp_ytd_vs_month_sum_delta": ytd_ly_vs_months_delta,
            "by_customer": {
                "matched_within_5c": ytd_ly_cmp["matched_within_5c"],
                "amount_diffs": ytd_ly_cmp["amount_diffs"],
                "sample_mismatches": ytd_ly_cmp["sample_mismatches"] if ytd_ly_cmp["amount_diffs"] else [],
            },
        })
        full_ly_sp_self_delta = round(sm_full_ly_sum - sm_ly_months_sum, 2)
        full_ly_sp_self_ok = abs(full_ly_sp_self_delta) <= _TOL
        year_slices.append({
            "key": "full_year_last_year",
            "label": f"Full Year Last Year ({prior}) SP column vs sum(Jan–Dec Last Year months)",
            "note": (
                "Prior-year invoiced fetch is Jan–through only (gateway time). "
                "Full calendar prior year is verified as SP self-consistency; "
                "months 1–through are also matched to invoiced above."
            ),
            "salesman_sum": sm_full_ly_sum,
            "invoiced_sum": None,
            "sp_month_sum": sm_ly_months_sum,
            "delta": full_ly_sp_self_delta,
            "ok": full_ly_sp_self_ok,
            "by_customer": {"matched_within_5c": None, "amount_diffs": 0 if full_ly_sp_self_ok else 1},
        })

    months_perfect = (
        (not want_ty or all(x["ok"] for x in months_ty))
        and (not want_ly or all(x["ok"] for x in months_ly))
    )
    years_perfect = (
        only_month is not None
        or (all(x["ok"] for x in year_slices) and not future_nonzero)
    )
    perfect = months_perfect and years_perfect
    if want_ty and only_month is None:
        perfect = (
            perfect
            and abs(sum(sm_ytd.values()) - sum(inv_ytd.values())) <= _TOL
            and acct_cmp["amount_diffs"] == 0
        )

    return {
        "ok": True,
        "perfect": perfect,
        "scope": scope,
        "only_month": only_month,
        "year": year,
        "through_month": through,
        "invoice_window": {
            "this_year_from": f"{year}-01-01" if want_ty else None,
            "this_year_to": end_day.isoformat() if want_ty else None,
            "last_year_from": f"{prior}-01-01" if want_ly else None,
            "last_year_to": prior_end.isoformat() if want_ly else None,
        },
        "salesman_sp": {
            "report_id": "monthly_salesman_yoy",
            "row_count": len(sm_rows),
        },
        "invoiced_sp": {
            "report_id": "invoiced_report",
            "this_year_row_count": len(inv_ty_rows),
            "last_year_row_count": len(inv_ly_rows),
            "columns": inv_ty_cols,
            "date_parsed": date_parsed,
            "date_failed": date_failed,
            "date_fail_samples": date_fail_samples,
        },
        "totals": {
            "salesman_ytd_sum": round(sum(sm_ytd.values()), 2) if want_ty else None,
            "invoiced_total_sum": round(sum(inv_ytd.values()), 2) if want_ty else None,
            "delta_sum": (
                round(sum(sm_ytd.values()) - sum(inv_ytd.values()), 2) if want_ty else None
            ),
            "salesman_by_customer_sum": round(sum(sm_by_acct.values()), 2) if want_ty else None,
            "invoiced_by_customer_sum": round(sum(inv_by_acct.values()), 2) if want_ty else None,
        },
        "by_salesman_label": {
            "salesman_sp_top": dict(sorted(sm_by_sm.items(), key=lambda x: -abs(x[1]))[:15]),
            "invoiced_sp_top": dict(sorted(inv_by_sm.items(), key=lambda x: -abs(x[1]))[:15]),
        } if want_ty else None,
        "compare_salesman_customer_pairs": {
            "matched_within_5c": matched,
            "amount_diffs": amount_diffs,
            "salesman_only": sm_only,
            "invoiced_only": inv_only,
            "sample_mismatches": mismatches,
            "note": "Label format differs (REdwards vs Edwards, Reggie); use by-customer for money.",
        } if want_ty and only_month is None else None,
        "compare_by_customer_account": {
            "matched_within_5c": acct_cmp["matched_within_5c"],
            "amount_diffs": acct_cmp["amount_diffs"],
            "sample_mismatches": acct_cmp["sample_mismatches"],
            "note": "Ignores salesman id/name label differences; compares Total Invoice by customer.",
        } if want_ty and only_month is None else None,
        "compare_by_month_this_year": {
            "ok": all(x["ok"] for x in months_ty) if months_ty else None,
            "months": months_ty,
        } if want_ty else None,
        "compare_by_month_last_year": {
            "ok": all(x["ok"] for x in months_ly) if months_ly else None,
            "months": months_ly,
        } if want_ly else None,
        "compare_year_slices": {
            "ok": years_perfect,
            "slices": year_slices,
            "future_months_nonzero_this_year": future_nonzero,
        },
    }
