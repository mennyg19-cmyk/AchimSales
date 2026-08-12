"""Run Number 4 ↔ invoiced reconcile locally (Reporting API), month by month."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "v3"))
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "v3" / ".env", override=False)

from web.reporting.http_client import ReportingApiClient  # noqa: E402
from web.reporting.params import NUMBER_4_BY_CUSTOMER_SP  # noqa: E402
from web.reporting.reconcile_number4 import reconcile, rolling_12_months  # noqa: E402
from report_engine.dates import today_eastern  # noqa: E402

OUT_DIR = ROOT / ".scratch" / "parity"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    base = os.environ.get("REPORTING_API_BASE_URL", "").strip()
    key = os.environ.get("REPORTING_API_KEY", "").strip()
    if not base or not key:
        raise SystemExit("REPORTING_API_BASE_URL / REPORTING_API_KEY missing")

    months = [int(x) for x in (sys.argv[1:] or [str(i) for i in range(1, 13)])]
    client = ReportingApiClient(base, key, timeout=600.0)
    as_of = today_eastern()
    print(f"as_of={as_of.isoformat()} window={rolling_12_months(as_of)}", flush=True)
    print("Fetching Number 4 by-customer (once)...", flush=True)
    n4 = client.run_report(
        NUMBER_4_BY_CUSTOMER_SP,
        {"AsOfDate": as_of.isoformat(), "IncludeCurrentMonth": True},
    )
    print(f"Number 4 rows={len(n4.rows or [])} cols={len(n4.columns or [])}", flush=True)

    summary = []
    for m in months:
        print(f"=== month index {m} ===", flush=True)
        result = reconcile(
            client, view="by_customer", only_month=m, n4_result=n4, as_of=as_of,
        )
        out = OUT_DIR / f"reconcile_number4_m{m}.json"
        out.write_text(json.dumps(result), encoding="utf-8")
        sub = result.get("compare_subtotal", {}).get("totals", {})
        ti = result.get("compare_total_invoice", {}).get("totals", {})
        month_label = (result.get("compare_subtotal", {}).get("months") or [{}])[0].get("month")
        row = {
            "month_index": m,
            "month": month_label,
            "sub_delta": sub.get("delta"),
            "sub_ok": sub.get("ok"),
            "sub_matched": sub.get("by_customer", {}).get("matched_within_5c"),
            "sub_diffs": sub.get("by_customer", {}).get("amount_diffs"),
            "sub_n4_only": sub.get("by_customer", {}).get("number4_only"),
            "sub_inv_only": sub.get("by_customer", {}).get("invoiced_only"),
            "ti_delta": ti.get("delta"),
            "ti_ok": ti.get("ok"),
            "best": result.get("best_fit_basis"),
            "perfect": result.get("perfect"),
        }
        summary.append(row)
        print(
            f"  {month_label} sub delta={row['sub_delta']} ok={row['sub_ok']} "
            f"matched={row['sub_matched']} diffs={row['sub_diffs']} "
            f"n4_only={row['sub_n4_only']} inv_only={row['sub_inv_only']}",
            flush=True,
        )
        print(
            f"  total_inv delta={row['ti_delta']} ok={row['ti_ok']} "
            f"best={row['best']} perfect={row['perfect']}",
            flush=True,
        )
        print(f"  wrote {out}", flush=True)

    summary_path = OUT_DIR / "reconcile_number4_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY {summary_path}", flush=True)
    for row in summary:
        print(
            f"  {row['month']}: sub={row['sub_delta']} ti={row['ti_delta']} "
            f"sub_ok={row['sub_ok']} matched={row['sub_matched']} diffs={row['sub_diffs']}",
            flush=True,
        )


if __name__ == "__main__":
    main()
