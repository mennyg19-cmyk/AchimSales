"""Call ordered_report SP and check CustomerRequisition is populated."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "v3"))
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "v3" / ".env", override=False)

from web.reporting.http_client import ReportingApiClient  # noqa: E402
from web.reporting import params as P  # noqa: E402
from report_engine.sources import ordered as S  # noqa: E402

base = os.environ.get("REPORTING_API_BASE_URL", "").strip()
key = os.environ.get("REPORTING_API_KEY", "").strip()
print("API configured:", bool(base and key), "base=", (base[:50] + "...") if len(base) > 50 else base)

client = ReportingApiClient(base, key, timeout=300.0)
# Small window so retest is fast (3 days mid-July)
sp = {
    "CreatedDateTimeFrom": "2026-07-15 00:00:00",
    "CreatedDateTimeTo": "2026-07-17 23:59:59",
}
print("SP params:", sp)

result = client.run_report("ordered_report", sp)
print("row_count:", result.row_count)
print("columns:", result.columns)
cols = result.columns or (list(result.rows[0].keys()) if result.rows else [])
print("has CustomerRequisition:", "CustomerRequisition" in cols)

if result.rows:
    keys = sorted(result.rows[0].keys())
    po_keys = [k for k in keys if any(x in k.lower() for x in ("req", "po", "purch"))]
    print("PO-ish keys on row:", po_keys)
    print("raw CustomerRequisition:", repr(result.rows[0].get("CustomerRequisition")))

facts = S.to_facts_ordered_report(list(result.rows))
filled = sum(1 for f in facts if f.po_number)
blank = sum(1 for f in facts if not f.po_number)
print(f"adapted PO filled={filled} blank={blank} ({100 * filled / max(1, len(facts)):.1f}% filled)")

samples = []
seen = set()
for f in facts:
    if f.po_number and f.po_number not in seen:
        seen.add(f.po_number)
        samples.append((f.sales_order_number, f.customer_account, f.po_number))
        if len(samples) >= 12:
            break
print("sample SO/acct/PO:", samples)

out = Path(".scratch/parity/ordered_po_retest")
out.mkdir(parents=True, exist_ok=True)
(out / "summary.txt").write_text(
    f"rows={result.row_count}\ncolumns={cols}\n"
    f"po_filled={filled} blank={blank}\nsamples={samples}\n",
    encoding="utf-8",
)
print("Wrote", out / "summary.txt")
