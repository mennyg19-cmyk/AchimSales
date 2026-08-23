"""Summarize Number 4 reconcile after free-text exclusion."""
from __future__ import annotations

import json
from pathlib import Path

p = Path(r"D:/Projects/Achim/AchimSales/.scratch/parity")
print("month | n4 | inv_sub(no FT) | delta | matched | ft_excluded_sub | ok")
n4t = invt = ftt = 0.0
all_ok = True
for i in range(1, 13):
    d = json.loads((p / f"reconcile_number4_m{i}.json").read_text(encoding="utf-8"))
    m = d["compare_subtotal"]["months"][0]
    ft = d["invoice_fetch"]["free_text_excluded"]
    print(
        f"{m['month']:7} | {m['number4_sum']:>12,.2f} | {m['invoiced_sum']:>12,.2f} | "
        f"{m['delta']:>8,.2f} | {m['by_customer']['matched_within_5c']:3} | "
        f"{ft['subtotal_sum']:>12,.2f} | {m['ok']}"
    )
    n4t += m["number4_sum"]
    invt += m["invoiced_sum"]
    ftt += ft["subtotal_sum"]
    all_ok = all_ok and m["ok"]
print(
    f"TOTAL  | {n4t:>12,.2f} | {invt:>12,.2f} | {n4t - invt:>8,.2f} |     | "
    f"{ftt:>12,.2f} | {all_ok}"
)
