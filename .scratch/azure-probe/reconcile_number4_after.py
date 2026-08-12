"""One-shot reconcile: Number 4 rolling-12 vs invoiced_report.

Number 4 is customer×item with monthly Qty/$ from the SP. Live Number 4 used
line extended amount (Qty×Price) — that is merchandise subtotal, not Total
Invoice (which adds tariff/freight/CC/misc). This diagnostic compares Number 4
Total $ / month $ columns to invoiced on both bases and reports which fits.

Gateway-safe: aggregates Number 4 rows as it goes (does not keep the pivot),
and can fetch invoiced one calendar month at a time (?month=1..12 in window
order) when a full 12-month invoiced pull would time out.
"""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from report_engine.dates import today_eastern
from report_engine.lib import iso_date, num

from web.reporting.params import NUMBER_4_BY_CUSTOMER_SP, NUMBER_4_BY_ITEM_SP


_TOL = 0.05
_SKIP_MONEY = {"total $", "avg price", "book price"}


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


def _invoice_date(row: dict) -> date | None:
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


def _subtotal(row: dict) -> float:
    return round(num(_get(row, "amount", "Amount", "SubTotal Invoices", "SubTotal")), 2)


def _total_invoice(row: dict) -> float:
    total = _get(row, "Total Invoice", "TotalInvoice", "InvoiceAmount")
    sub = _get(row, "SubTotal Invoices", "SubTotal", "Amount", "subtotal", "amount")
    tar = _get(row, "Tariff Charges", "SL_TariffCharges", "Tariff")
    fre = _get(row, "Freight Charges", "SH_FreightCharges", "Freight")
    cc = _get(row, "CC Charges", "SH_ProcessingFeesCharges", "CC")
    misc = _get(row, "Misc Charges", "Misc")
    if any(x is not None for x in (tar, fre, cc, misc)) and sub is not None:
        return round(num(sub) + num(tar) + num(fre) + num(cc) + num(misc), 2)
    if total is not None:
        return round(num(total), 2)
    return round(num(sub), 2)


def rolling_12_months(as_of: date) -> list[tuple[int, int]]:
    """Last 12 calendar months ending at as_of month (IncludeCurrentMonth=true)."""
    y, m = as_of.year, as_of.month
    out: list[tuple[int, int]] = []
    for i in range(12):
        mm = m - i
        yy = y
        while mm < 1:
            mm += 12
            yy -= 1
        out.append((yy, mm))
    out.reverse()
    return out


def _parse_month_header(header: str) -> tuple[int, int] | None:
    """Map 'Jul-25 $' / 'Jul-25$' / '2025-07 $' -> (year, month)."""
    h = str(header or "").strip()
    if not h or h.lower() in _SKIP_MONEY:
        return None
    if not (h.endswith("$") or h.endswith(" $")):
        return None
    body = h[:-1].strip() if h.endswith("$") else h
    body = body.strip()
    # 2025-07
    if len(body) >= 7 and body[4] == "-" and body[:4].isdigit():
        try:
            return int(body[:4]), int(body[5:7])
        except ValueError:
            return None
    # Jul-25 / Jul-2025
    mon_map = {calendar.month_abbr[i].lower(): i for i in range(1, 13)}
    mon_map.update({calendar.month_name[i].lower()[:3]: i for i in range(1, 13)})
    m = re.match(r"^([A-Za-z]{3,9})[-/ ]+(\d{2,4})$", body)
    if not m:
        return None
    mon = mon_map.get(m.group(1).lower()[:3])
    if not mon:
        return None
    yy = int(m.group(2))
    if yy < 100:
        yy += 2000
    return yy, mon


def _discover_month_cols(headers: list[str], rows: list[dict]) -> dict[tuple[int, int], str]:
    """(year, month) -> column name for monthly $ columns."""
    sample_keys = list(headers) if headers else (list(rows[0].keys()) if rows else [])
    found: dict[tuple[int, int], str] = {}
    for h in sample_keys:
        ym = _parse_month_header(h)
        if ym:
            found[ym] = h
    return found


def _compare_maps(
    left: dict[str, float],
    right: dict[str, float],
    *,
    left_label: str,
    right_label: str,
    sample_limit: int = 20,
) -> dict:
    matched = diffs = left_only = right_only = 0
    samples: list[dict] = []
    for key in sorted(set(left) | set(right)):
        if not key:
            continue
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


def _slice(n4: float, inv: float, by_acct: dict) -> dict:
    ok = (
        abs(n4 - inv) <= _TOL
        and by_acct["amount_diffs"] == 0
        and by_acct.get("number4_only", 0) == 0
        and by_acct.get("invoiced_only", 0) == 0
    )
    out = {
        "number4_sum": n4,
        "invoiced_sum": inv,
        "delta": round(n4 - inv, 2),
        "ok": ok,
        "by_customer": {
            "matched_within_5c": by_acct["matched_within_5c"],
            "amount_diffs": by_acct["amount_diffs"],
            "number4_only": by_acct.get("number4_only", 0),
            "invoiced_only": by_acct.get("invoiced_only", 0),
        },
    }
    if not ok:
        out["by_customer"]["sample_mismatches"] = by_acct.get("sample_mismatches", [])
    return out


def reconcile(
    client,
    *,
    as_of: date | None = None,
    view: str = "by_customer",
    only_month: int | None = None,
    n4_result=None,
) -> dict:
    """Compare Number 4 Total $/months to invoiced subtotal and Total Invoice.

    n4_result: optional pre-fetched SP result (same shape as client.run_report)
    so a month-by-month loop does not re-pull the rolling-12 Number 4 pivot.
    """
    today = today_eastern()
    as_of = as_of or today
    months = rolling_12_months(as_of)
    window_start = date(months[0][0], months[0][1], 1)
    window_end = as_of

    if only_month is not None:
        # only_month is 1..12 index into the rolling window (1=oldest).
        only_month = max(1, min(12, int(only_month)))
        target_ym = months[only_month - 1]
        inv_start = date(target_ym[0], target_ym[1], 1)
        last_day = calendar.monthrange(target_ym[0], target_ym[1])[1]
        inv_end = date(target_ym[0], target_ym[1], last_day)
        if inv_end > as_of:
            inv_end = as_of
    else:
        inv_start, inv_end = window_start, window_end
        target_ym = None

    sp_id = NUMBER_4_BY_ITEM_SP if view == "by_item" else NUMBER_4_BY_CUSTOMER_SP
    if n4_result is None:
        n4 = client.run_report(
            sp_id,
            {"AsOfDate": as_of.isoformat(), "IncludeCurrentMonth": True},
        )
    else:
        n4 = n4_result
    n4_rows = n4.rows or []
    headers = list(n4.columns or [])
    month_cols = _discover_month_cols(headers, n4_rows)

    n4_total = 0.0
    n4_by_acct: dict[str, float] = defaultdict(float)
    n4_by_month: dict[tuple[int, int], float] = defaultdict(float)
    n4_by_month_acct: dict[tuple[int, int], dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    # SP header is "Customer #" (by-customer) / may vary on by-item.
    acct_field_candidates = (
        "Customer #", "Customer Account", "CustomerAccount",
        "Cust. #", "AccountNum",
    )

    for r in n4_rows:
        acct = str(_get(r, *acct_field_candidates) or "").strip()
        row_total = round(num(_get(r, "Total $", "Total$", "Total")), 2)
        # Prefer summing month $ columns when present (guards Total $ drift).
        month_sum = 0.0
        for ym, col in month_cols.items():
            val = round(num(r.get(col)), 2)
            month_sum = round(month_sum + val, 2)
            n4_by_month[ym] = round(n4_by_month[ym] + val, 2)
            if acct:
                n4_by_month_acct[ym][acct] = round(n4_by_month_acct[ym][acct] + val, 2)
        use = month_sum if month_cols else row_total
        n4_total = round(n4_total + use, 2)
        if acct:
            n4_by_acct[acct] = round(n4_by_acct[acct] + use, 2)

    inv = client.run_report(
        "invoiced_report",
        {
            "InvoiceDateFrom": f"{inv_start.isoformat()} 00:00:00",
            "InvoiceDateTo": f"{inv_end.isoformat()} 23:59:59",
        },
    )
    inv_rows = inv.rows or []

    inv_sub_total = inv_ti_total = 0.0
    inv_sub_by_acct: dict[str, float] = defaultdict(float)
    inv_ti_by_acct: dict[str, float] = defaultdict(float)
    inv_sub_by_month: dict[tuple[int, int], float] = defaultdict(float)
    inv_ti_by_month: dict[tuple[int, int], float] = defaultdict(float)
    inv_sub_month_acct: dict[tuple[int, int], dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    inv_ti_month_acct: dict[tuple[int, int], dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    date_parsed = date_failed = 0

    for r in inv_rows:
        acct = str(_get(r, "CustomerAccount", "InvoiceAccount", "AccountNum") or "").strip()
        sub = _subtotal(r)
        ti = _total_invoice(r)
        inv_sub_total = round(inv_sub_total + sub, 2)
        inv_ti_total = round(inv_ti_total + ti, 2)
        if acct:
            inv_sub_by_acct[acct] = round(inv_sub_by_acct[acct] + sub, 2)
            inv_ti_by_acct[acct] = round(inv_ti_by_acct[acct] + ti, 2)
        d = _invoice_date(r)
        if d is None:
            date_failed += 1
            continue
        date_parsed += 1
        ym = (d.year, d.month)
        inv_sub_by_month[ym] = round(inv_sub_by_month[ym] + sub, 2)
        inv_ti_by_month[ym] = round(inv_ti_by_month[ym] + ti, 2)
        if acct:
            inv_sub_month_acct[ym][acct] = round(inv_sub_month_acct[ym][acct] + sub, 2)
            inv_ti_month_acct[ym][acct] = round(inv_ti_month_acct[ym][acct] + ti, 2)

    def month_label(ym: tuple[int, int]) -> str:
        return f"{calendar.month_abbr[ym[1]]}-{str(ym[0])[-2:]}"

    if target_ym is not None:
        month_list = [target_ym]
        # When only one invoiced month was fetched, Number 4 still has all 12 —
        # compare only that month's slice.
        n4_slice_total = round(n4_by_month.get(target_ym, 0.0), 2)
        n4_slice_acct = dict(n4_by_month_acct.get(target_ym, {}))
    else:
        month_list = months
        n4_slice_total = n4_total
        n4_slice_acct = dict(n4_by_acct)

    months_sub = []
    months_ti = []
    for ym in month_list:
        n4_m = round(n4_by_month.get(ym, 0.0), 2)
        sub_m = round(inv_sub_by_month.get(ym, 0.0), 2)
        ti_m = round(inv_ti_by_month.get(ym, 0.0), 2)
        n4_acct = dict(n4_by_month_acct.get(ym, {}))
        cmp_sub = _compare_maps(
            n4_acct, dict(inv_sub_month_acct.get(ym, {})),
            left_label="number4", right_label="invoiced",
        )
        cmp_ti = _compare_maps(
            n4_acct, dict(inv_ti_month_acct.get(ym, {})),
            left_label="number4", right_label="invoiced",
        )
        months_sub.append({"month": month_label(ym), "ym": list(ym), **_slice(n4_m, sub_m, cmp_sub)})
        months_ti.append({"month": month_label(ym), "ym": list(ym), **_slice(n4_m, ti_m, cmp_ti)})

    cmp_sub_all = _compare_maps(
        n4_slice_acct, dict(inv_sub_by_acct),
        left_label="number4", right_label="invoiced",
    )
    cmp_ti_all = _compare_maps(
        n4_slice_acct, dict(inv_ti_by_acct),
        left_label="number4", right_label="invoiced",
    )
    totals_sub = _slice(n4_slice_total, inv_sub_total, cmp_sub_all)
    totals_ti = _slice(n4_slice_total, inv_ti_total, cmp_ti_all)

    # SP Total $ column vs sum of month $ columns (self-check on full N4 pull).
    n4_total_col = round(sum(round(num(_get(r, "Total $", "Total$")), 2) for r in n4_rows), 2)
    month_cols_sum = round(sum(n4_by_month.values()), 2)
    self_delta = round(n4_total_col - month_cols_sum, 2) if month_cols else None

    best = "subtotal" if abs(totals_sub["delta"]) <= abs(totals_ti["delta"]) else "total_invoice"
    perfect_sub = totals_sub["ok"] and all(m["ok"] for m in months_sub)
    perfect_ti = totals_ti["ok"] and all(m["ok"] for m in months_ti)

    return {
        "ok": True,
        "perfect": perfect_sub or perfect_ti,
        "perfect_on": (
            "subtotal" if perfect_sub else ("total_invoice" if perfect_ti else None)
        ),
        "best_fit_basis": best,
        "view": view,
        "sp_id": sp_id,
        "as_of": as_of.isoformat(),
        "only_month_index": only_month,
        "rolling_window": {
            "from": window_start.isoformat(),
            "to": window_end.isoformat(),
            "months": [month_label(ym) for ym in months],
        },
        "invoice_fetch": {
            "from": inv_start.isoformat(),
            "to": inv_end.isoformat(),
            "row_count": len(inv_rows),
            "date_parsed": date_parsed,
            "date_failed": date_failed,
        },
        "number4": {
            "row_count": len(n4_rows),
            "columns_sample": headers[:40],
            "month_columns": {month_label(k): v for k, v in sorted(month_cols.items())},
            "total_from_month_cols": month_cols_sum,
            "total_from_total_col": n4_total_col,
            "total_vs_months_delta": self_delta,
        },
        "compare_subtotal": {
            "note": "Number 4 $ vs invoiced amount/SubTotal (line goods; live Number 4 basis).",
            "totals": totals_sub,
            "months": months_sub,
            "ok": perfect_sub,
        },
        "compare_total_invoice": {
            "note": "Number 4 $ vs invoiced Total Invoice (includes tariff/freight/CC/misc).",
            "totals": totals_ti,
            "months": months_ti,
            "ok": perfect_ti,
        },
    }
