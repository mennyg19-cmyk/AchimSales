"""Attribute Number 4 gaps: invoiced_only vs amount_diff dollars."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

p = Path(r"D:/Projects/Achim/AchimSales/.scratch/parity")
inv_only_accts = Counter()
inv_only_dollars = 0.0
diff_dollars = 0.0
n4_higher = 0.0
n4_lower = 0.0

for i in range(1, 13):
    d = json.loads((p / f"reconcile_number4_m{i}.json").read_text(encoding="utf-8"))
    # Walk months samples only — for full attribution re-sum from by_customer if present
    # The totals already have delta; samples are capped. Pull full compare from months[0].
    m = d["compare_subtotal"]["months"][0]
    samples = m["by_customer"].get("sample_mismatches") or []
    # samples are capped at 20 — not full. Report what we can + top recurring inv_only keys.
    for s in samples:
        if s["type"] == "invoiced_only":
            inv_only_accts[s["key"]] += 1
            inv_only_dollars += s["invoiced"]
        elif s["type"] == "amount_diff":
            diff_dollars += s["delta"]
            if s["delta"] > 0:
                n4_higher += s["delta"]
            else:
                n4_lower += s["delta"]

print("Sample-capped attribution (not full dollars):")
print(f"  invoiced_only sample dollars (inv side): {inv_only_dollars:,.2f}")
print(f"  amount_diff sample net (n4-inv): {diff_dollars:,.2f}")
print(f"  of which n4_higher sample: {n4_higher:,.2f} n4_lower sample: {n4_lower:,.2f}")
print()
print("Top recurring invoiced_only accounts across months (in samples):")
for acct, n in inv_only_accts.most_common(15):
    print(f"  {acct}: {n} months")

# Aug-26 is cleanest: 0 amount_diffs, 6 invoiced_only — full story in samples
d = json.loads((p / "reconcile_number4_m12.json").read_text(encoding="utf-8"))
m = d["compare_subtotal"]["months"][0]
print()
print("Aug-26 FULL mismatches (0 amount_diffs, only invoiced_only):")
print(f"  n4={m['number4_sum']:,.2f} inv={m['invoiced_sum']:,.2f} delta={m['delta']:,.2f}")
total_inv_only = 0.0
for s in m["by_customer"].get("sample_mismatches") or []:
    print(f"  {s}")
    total_inv_only += s["invoiced"]
print(f"  sum(invoiced_only)={total_inv_only:,.2f} vs month delta={-m['delta']:,.2f}")
