"""Diagnose why date-gate explain rate is low; check cross-company + line-number matching."""
from collections import Counter
from pathlib import Path
import csv

rows = list(csv.DictReader(Path(
    ".scratch/parity/20260804-193031-postfix/ordered_line_date_probe/odata_header_vs_line_dates.csv"
).open(encoding="utf-8")))

print("by side+bucket", Counter((r["side"], r["bucket"]) for r in rows))
print("\ntest_only no_header unique SOs",
      len({r["sales_order"] for r in rows if r["side"] == "test_only" and r["bucket"] == "no_header_odata"}))
print("sample no_header SOs",
      list({r["sales_order"] for r in rows if r["bucket"] == "no_header_odata"})[:15])

# fractional lines
frac = [r for r in rows if "." in r["line_number"]]
print(f"\nrows with fractional line#: {len(frac)} / {len(rows)}")
print("frac by side", Counter(r["side"] for r in frac))

# dates_differ among nontz
nontz = [r for r in rows if r["tz_edge"] == "no"]
print("dates_differ nontz", Counter(r["dates_differ"] for r in nontz))
print("header_in / line_in nontz",
      Counter((r["header_in_july"], r["line_in_july"]) for r in nontz))

# live_only both_in_period: are they fractional delivery lines?
live_both = [r for r in rows if r["bucket"] == "live_only:both_in_period_other_cause"
             or (r["side"] == "live_only" and r["bucket"] == "both_in_period_other_cause")]
print("live_only both_in_period", len(live_both),
      "fractional", sum(1 for r in live_both if "." in r["line_number"]))

# test unexplained
tu = [r for r in rows if r["side"] == "test_only" and r["bucket"] == "unexplained_test_only"]
print("test unexplained", len(tu))
print("  header_in/line_in", Counter((r["header_in_july"], r["line_in_july"]) for r in tu))
print("  dates_differ", Counter(r["dates_differ"] for r in tu))
for r in tu[:8]:
    print(f"  {r['sales_order']} L{r['line_number']} {r['item']} "
          f"report={r['report_order_date']} hdr={r['header_order_creation']} "
          f"line={r['line_sys_created']}")
