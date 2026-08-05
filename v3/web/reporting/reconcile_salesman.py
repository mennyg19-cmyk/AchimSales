"""One-shot reconcile: monthly_salesman_yoy YTD vs invoiced_report Total Invoice."""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import date
from typing import Any

from report_engine.dates import today_eastern
from report_engine.lib import num


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


def _salesman_ytd(row: dict, through: int) -> float:
    ytd = _money(row, "YTD This Year", "YTDThisYear", "Ytd This Year")
    # Prefer explicit YTD when present (including legitimate zeros with column).
    keys = {_norm(k) for k in row}
    if "ytdthisyear" in keys:
        return ytd
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    total = 0.0
    for m in months[:through]:
        total += _money(row, f"{m} This Year", f"{m}ThisYear")
    return round(total, 2)


def reconcile(client, *, year: int | None = None, through_month: int | None = None) -> dict:
    """Fetch both SPs via ReportingApiClient; compare YTD Total Invoice."""
    today = today_eastern()
    year = year or today.year
    through = through_month or (today.month if year == today.year else 12)
    through = max(1, min(12, int(through)))

    # End of through-month (or today if current month).
    if year == today.year and through == today.month:
        end_day = today
    else:
        end_day = date(year, through, calendar.monthrange(year, through)[1])

    sm = client.run_report(
        "monthly_salesman_yoy",
        {"ReportYear": year, "ThroughMonth": through},
    )
    inv = client.run_report(
        "invoiced_report",
        {
            "InvoiceDateFrom": f"{year}-01-01 00:00:00",
            "InvoiceDateTo": f"{end_day.isoformat()} 23:59:59",
        },
    )

    sm_rows = sm.rows or []
    inv_rows = inv.rows or []

    sm_ytd: dict[tuple[str, str], float] = {}
    sm_by_sm: dict[str, float] = defaultdict(float)
    for r in sm_rows:
        sid = str(_get(r, "SalesmanId", "SalesmanNumber") or "").strip()
        sname = str(_get(r, "SalesmanName", "Salesman") or "").strip()
        sm_key = sid or sname
        acct = str(_get(r, "CustomerAccount", "Cust. #") or "").strip()
        ytd = _salesman_ytd(r, through)
        key = (_norm(sm_key), acct)
        sm_ytd[key] = round(sm_ytd.get(key, 0.0) + ytd, 2)
        sm_by_sm[sm_key or "(blank)"] = round(sm_by_sm[sm_key or "(blank)"] + ytd, 2)

    inv_ytd: dict[tuple[str, str], float] = {}
    inv_by_sm: dict[str, float] = defaultdict(float)
    inv_by_acct: dict[str, float] = defaultdict(float)
    for r in inv_rows:
        total = _invoice_total(r)
        sm_raw = str(_get(r, "SalesGroup", "Salesman", "SalesmanName", "salesman") or "").strip()
        acct = str(_get(r, "CustomerAccount", "InvoiceAccount", "AccountNum") or "").strip()
        key = (_norm(sm_raw), acct)
        inv_ytd[key] = round(inv_ytd.get(key, 0.0) + total, 2)
        inv_by_sm[sm_raw or "(blank)"] = round(inv_by_sm[sm_raw or "(blank)"] + total, 2)
        inv_by_acct[acct] = round(inv_by_acct[acct] + total, 2)

    # Also compare by customer account only (salesman labels often differ id vs name).
    sm_by_acct: dict[str, float] = defaultdict(float)
    for (_, acct), val in sm_ytd.items():
        sm_by_acct[acct] = round(sm_by_acct[acct] + val, 2)

    matched = amount_diffs = sm_only = inv_only = 0
    mismatches: list[dict] = []
    for key, sy in sm_ytd.items():
        iv = inv_ytd.get(key)
        if iv is None:
            if abs(sy) > 0.05:
                sm_only += 1
                if len(mismatches) < 30:
                    mismatches.append({
                        "type": "pair_salesman_only", "key": list(key), "salesman_ytd": sy,
                    })
            continue
        if abs(sy - iv) > 0.05:
            amount_diffs += 1
            if len(mismatches) < 40:
                mismatches.append({
                    "type": "pair_amount_diff", "key": list(key),
                    "salesman_ytd": sy, "invoiced_total": iv, "delta": round(sy - iv, 2),
                })
        else:
            matched += 1

    for key, iv in inv_ytd.items():
        if key not in sm_ytd and abs(iv) > 0.05:
            inv_only += 1
            if len(mismatches) < 55:
                mismatches.append({
                    "type": "pair_invoiced_only", "key": list(key), "invoiced_total": iv,
                })

    acct_matched = acct_diffs = 0
    acct_mismatches: list[dict] = []
    all_accts = set(sm_by_acct) | set(inv_by_acct)
    for acct in sorted(all_accts):
        if not acct:
            continue
        sy = sm_by_acct.get(acct, 0.0)
        iv = inv_by_acct.get(acct, 0.0)
        if abs(sy - iv) <= 0.05:
            acct_matched += 1
        else:
            acct_diffs += 1
            if len(acct_mismatches) < 40:
                acct_mismatches.append({
                    "customer": acct, "salesman_ytd": sy, "invoiced_total": iv,
                    "delta": round(sy - iv, 2),
                })

    return {
        "ok": True,
        "year": year,
        "through_month": through,
        "invoice_window": {
            "from": f"{year}-01-01",
            "to": end_day.isoformat(),
        },
        "salesman_sp": {
            "report_id": "monthly_salesman_yoy",
            "row_count": len(sm_rows),
            "columns": list(sm.columns or [])[:80],
            "sample_keys": sorted(sm_rows[0].keys()) if sm_rows else [],
        },
        "invoiced_sp": {
            "report_id": "invoiced_report",
            "row_count": len(inv_rows),
            "columns": list(inv.columns or [])[:40],
            "sample_keys": sorted(inv_rows[0].keys()) if inv_rows else [],
        },
        "totals": {
            "salesman_ytd_sum": round(sum(sm_ytd.values()), 2),
            "invoiced_total_sum": round(sum(inv_ytd.values()), 2),
            "delta_sum": round(sum(sm_ytd.values()) - sum(inv_ytd.values()), 2),
            "salesman_by_customer_sum": round(sum(sm_by_acct.values()), 2),
            "invoiced_by_customer_sum": round(sum(inv_by_acct.values()), 2),
        },
        "by_salesman_label": {
            "salesman_sp_top": dict(sorted(sm_by_sm.items(), key=lambda x: -abs(x[1]))[:25]),
            "invoiced_sp_top": dict(sorted(inv_by_sm.items(), key=lambda x: -abs(x[1]))[:25]),
        },
        "compare_salesman_customer_pairs": {
            "matched_within_5c": matched,
            "amount_diffs": amount_diffs,
            "salesman_only": sm_only,
            "invoiced_only": inv_only,
            "sample_mismatches": mismatches,
        },
        "compare_by_customer_account": {
            "matched_within_5c": acct_matched,
            "amount_diffs": acct_diffs,
            "sample_mismatches": acct_mismatches,
            "note": "Ignores salesman id/name label differences; compares Total Invoice by customer.",
        },
    }
