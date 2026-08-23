"""Reconcile monthly_salesman_yoy vs invoiced_report (Total Invoice) on Azure."""
from __future__ import annotations

import json
import os
import traceback
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date

OUT = os.path.join(os.path.dirname(__file__), "_reconcile_salesman_out.json")


def _post(report_id: str, params: dict, timeout: int = 240) -> dict:
    base = os.environ["REPORTING_API_BASE_URL"].rstrip("/")
    key = os.environ["REPORTING_API_KEY"]
    req = urllib.request.Request(
        f"{base}/api/reports/{report_id}/run",
        data=json.dumps(params).encode(),
        method="POST",
        headers={"X-API-Key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _num(v) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return round(float(v), 2)
    except (TypeError, ValueError):
        return 0.0


def _norm(s) -> str:
    return str(s or "").strip().lower()


def _get(row: dict, *names: str):
    for n in names:
        if n in row:
            return row[n]
    wanted = {_norm(n).replace(" ", "").replace("_", "") for n in names}
    for k, v in row.items():
        if _norm(k).replace(" ", "").replace("_", "") in wanted:
            return v
    return None


def main() -> None:
    today = date.today()
    year = today.year
    through = today.month
    result: dict = {
        "year": year,
        "through_month": through,
        "ok": False,
        "error": None,
    }
    try:
        sm = _post(
            "monthly_salesman_yoy",
            {"ReportYear": year, "ThroughMonth": through},
            timeout=240,
        )
        inv = _post(
            "invoiced_report",
            {
                "InvoiceDateFrom": f"{year}-01-01 00:00:00",
                "InvoiceDateTo": f"{year}-{through:02d}-{today.day:02d} 23:59:59"
                if through == today.month
                else f"{year}-{through:02d}-28 23:59:59",
            },
            timeout=300,
        )
        # Prefer month-end for through months before current; for current use today.
        if through < today.month or year < today.year:
            # last day approx — re-fetch with proper end if we used wrong day
            pass

        sm_rows = sm.get("rows") or []
        inv_rows = inv.get("rows") or []
        sm_cols = sm.get("columns") or (list(sm_rows[0].keys()) if sm_rows else [])
        inv_cols = inv.get("columns") or (list(inv_rows[0].keys()) if inv_rows else [])

        result["salesman"] = {
            "row_count": len(sm_rows),
            "columns": sm_cols,
            "sample_keys": sorted(sm_rows[0].keys()) if sm_rows else [],
        }
        result["invoiced"] = {
            "row_count": len(inv_rows),
            "columns": inv_cols[:40],
            "sample_keys": sorted(inv_rows[0].keys()) if inv_rows else [],
        }

        # Salesman YTD This Year per (salesman, customer)
        sm_ytd: dict[tuple[str, str], float] = {}
        sm_by_sm: dict[str, float] = defaultdict(float)
        for r in sm_rows:
            sid = str(_get(r, "SalesmanId", "SalesmanNumber") or "").strip()
            sname = str(_get(r, "SalesmanName", "Salesman") or "").strip()
            sm_key = sid or sname
            acct = str(_get(r, "CustomerAccount", "Cust. #") or "").strip()
            ytd = _num(
                _get(
                    r,
                    "YTD This Year",
                    "YTDThisYear",
                    "Ytd This Year",
                    "Sales YTD This Year",
                )
            )
            # If YTD column missing, sum Jan..Through monthly cols
            if ytd == 0.0 and "YTD This Year" not in (sm_cols or []) and not any(
                "ytdthisyear" in _norm(c).replace(" ", "") for c in (sm_cols or r.keys())
            ):
                months = [
                    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
                ]
                ytd = 0.0
                for m in months[:through]:
                    ytd += _num(_get(r, f"{m} This Year", f"{m}ThisYear"))
                ytd = round(ytd, 2)
            sm_ytd[(sm_key, acct)] = round(sm_ytd.get((sm_key, acct), 0.0) + ytd, 2)
            sm_by_sm[sm_key] = round(sm_by_sm[sm_key] + ytd, 2)

        # Invoiced Total Invoice by salesman + customer for the window
        inv_ytd: dict[tuple[str, str], float] = {}
        inv_by_sm: dict[str, float] = defaultdict(float)
        total_col_candidates = (
            "Total Invoice", "TotalInvoice", "InvoiceAmount", "Amount", "total"
        )
        salesman_candidates = ("SalesGroup", "Salesman", "SalesmanName", "salesman")
        acct_candidates = ("CustomerAccount", "InvoiceAccount", "AccountNum", "customeraccount")

        for r in inv_rows:
            total = _num(_get(r, *total_col_candidates))
            # Prefer composed total if pieces present
            sub = _get(r, "SubTotal Invoices", "SubTotal", "Amount", "subtotal")
            tar = _get(r, "Tariff Charges", "SL_TariffCharges", "Tariff")
            fre = _get(r, "Freight Charges", "SH_FreightCharges", "Freight")
            cc = _get(r, "CC Charges", "SH_ProcessingFeesCharges", "CC")
            misc = _get(r, "Misc Charges", "Misc")
            if any(x is not None for x in (tar, fre, cc, misc)) and sub is not None:
                total = round(
                    _num(sub) + _num(tar) + _num(fre) + _num(cc) + _num(misc), 2
                )
            sm_raw = str(_get(r, *salesman_candidates) or "").strip()
            acct = str(_get(r, *acct_candidates) or "").strip()
            key = (sm_raw, acct)
            inv_ytd[key] = round(inv_ytd.get(key, 0.0) + total, 2)
            inv_by_sm[sm_raw] = round(inv_by_sm[sm_raw] + total, 2)

        # Match keys loosely: salesman id vs name
        def find_inv(sm_key: str, acct: str) -> float | None:
            if (sm_key, acct) in inv_ytd:
                return inv_ytd[(sm_key, acct)]
            # try case-insensitive salesman
            for (isk, iacct), val in inv_ytd.items():
                if iacct == acct and _norm(isk) == _norm(sm_key):
                    return val
            return None

        mismatches = []
        matched = 0
        sm_only = 0
        money_gap = 0
        for (sm_key, acct), sy in sm_ytd.items():
            iv = find_inv(sm_key, acct)
            if iv is None:
                # try match by account only across renamed salesmen — skip for now
                if abs(sy) > 0.009:
                    sm_only += 1
                    if len(mismatches) < 40:
                        mismatches.append({
                            "type": "salesman_only",
                            "salesman": sm_key,
                            "customer": acct,
                            "salesman_ytd": sy,
                        })
                continue
            if abs(sy - iv) > 0.05:
                money_gap += 1
                if len(mismatches) < 40:
                    mismatches.append({
                        "type": "amount_diff",
                        "salesman": sm_key,
                        "customer": acct,
                        "salesman_ytd": sy,
                        "invoiced_total": iv,
                        "delta": round(sy - iv, 2),
                    })
            else:
                matched += 1

        inv_only = 0
        sm_accts = {(a) for _, a in sm_ytd}
        for (isk, iacct), iv in inv_ytd.items():
            if abs(iv) < 0.009:
                continue
            # any salesman row for this account?
            found = any(a == iacct and abs(find_inv(sk, a) or 0) >= 0 for sk, a in sm_ytd)
            # better: check if this exact pair matched
            hit = False
            for (sk, a), sy in sm_ytd.items():
                if a == iacct and (_norm(sk) == _norm(isk) or sk == isk):
                    hit = True
                    break
            if not hit:
                inv_only += 1
                if len(mismatches) < 60 and inv_only <= 20:
                    mismatches.append({
                        "type": "invoiced_only",
                        "salesman": isk,
                        "customer": iacct,
                        "invoiced_total": iv,
                    })

        result["totals"] = {
            "salesman_ytd_sum": round(sum(sm_ytd.values()), 2),
            "invoiced_total_sum": round(sum(inv_ytd.values()), 2),
            "delta_sum": round(sum(sm_ytd.values()) - sum(inv_ytd.values()), 2),
            "salesman_by_salesman": dict(sorted(sm_by_sm.items(), key=lambda x: -abs(x[1]))[:30]),
            "invoiced_by_salesman": dict(sorted(inv_by_sm.items(), key=lambda x: -abs(x[1]))[:30]),
        }
        result["compare"] = {
            "pairs_matched_within_5c": matched,
            "amount_diffs": money_gap,
            "salesman_only_nonzero": sm_only,
            "invoiced_only_nonzero": inv_only,
            "salesman_pair_count": len(sm_ytd),
            "invoiced_pair_count": len(inv_ytd),
            "sample_mismatches": mismatches,
        }
        result["ok"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()[-2000:]

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print("WROTE", OUT, "ok=", result.get("ok"), "err=", result.get("error"))


if __name__ == "__main__":
    main()
