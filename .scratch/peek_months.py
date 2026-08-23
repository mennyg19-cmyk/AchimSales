import json
from pathlib import Path
from collections import Counter

# Peek date-related fields from prior reconcile if any sample rows exist
# Also check what month result says about invoiced_sum
for scope in ("ty", "ly"):
    p = Path(rf"d:\Projects\Achim\AchimSales\.scratch\parity\reconcile_salesman_{scope}_out.json")
    d = json.loads(p.read_text(encoding="utf-8"))
    print(scope, "window", d.get("invoice_window"))
    print(" invoiced rows", d.get("invoiced_sp"))
    months = (d.get("compare_by_month_this_year") or d.get("compare_by_month_last_year") or {}).get("months") or []
    for m in months[:2]:
        print(" ", m["label"], "sm", m["salesman_sum"], "inv", m["invoiced_sum"],
              "by_cust", m.get("by_customer"))
