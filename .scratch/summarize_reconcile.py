import json
from pathlib import Path

for scope in ("ty", "ly"):
    p = Path(rf"d:\Projects\Achim\AchimSales\.scratch\parity\reconcile_salesman_{scope}_out.json")
    print("====", scope, "size", p.stat().st_size if p.exists() else None)
    if not p.exists():
        continue
    raw = p.read_text(encoding="utf-8")
    try:
        d = json.loads(raw)
    except Exception as e:
        print("NOT_JSON", raw[:400], e)
        continue
    print(" invoiced rows", d.get("invoiced_sp"))
    print("perfect", d.get("perfect"), "scope", d.get("scope"))
    print("totals", d.get("totals"))
    print("error", d.get("error"))
    ty = d.get("compare_by_month_this_year") or {}
    ly = d.get("compare_by_month_last_year") or {}
    print("months_ty_ok", ty.get("ok"), "months_ly_ok", ly.get("ok"))
    print("years_ok", (d.get("compare_year_slices") or {}).get("ok"))
    for m in ty.get("months") or []:
        print(" TY", m.get("label"), "delta", m.get("delta"), "ok", m.get("ok"),
              "cust_diffs", (m.get("by_customer") or {}).get("amount_diffs"))
    for m in ly.get("months") or []:
        print(" LY", m.get("label"), "delta", m.get("delta"), "ok", m.get("ok"),
              "cust_diffs", (m.get("by_customer") or {}).get("amount_diffs"),
              "sample", (m.get("by_customer") or {}).get("sample_mismatches", [])[:3])
    for s in (d.get("compare_year_slices") or {}).get("slices") or []:
        print(" YR", s.get("key"), "delta", s.get("delta"), "ok", s.get("ok"),
              "sm", s.get("salesman_sum"), "inv", s.get("invoiced_sum"))
    fut = (d.get("compare_year_slices") or {}).get("future_months_nonzero_this_year") or []
    print("future_nonzero", fut)
    acct = d.get("compare_by_customer_account") or {}
    print("acct", acct.get("matched_within_5c"), "diffs", acct.get("amount_diffs"))
