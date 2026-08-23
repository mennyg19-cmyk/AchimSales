"""Probe monthly_salesman_yoy catalog + columns."""
from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, "v3")
from web.reporting.http_client import ReportingApiClient

base = os.environ.get("REPORTING_API_BASE_URL", "").strip()
key = os.environ.get("REPORTING_API_KEY", "").strip()
print("configured", bool(base and key), "base", (base[:40] if base else ""))
client = ReportingApiClient(base, key, timeout=180.0)
candidates = [
    "monthly_salesman_yoy",
    "usp_monthly_salesman_yoy",
    "monthly_salesman_year_over_year",
    "salesman_yoy",
    "salesman_monthly_yoy",
]
params = {
    "ReportYear": 2026,
    "ThroughMonth": 5,
    "SalesmanId": None,
    "SalesmanName": None,
    "CustomerAccount": None,
    "CustomerName": None,
}
for rid in candidates:
    try:
        result = client.run_report(rid, params)
        print("OK", rid, "rows", result.row_count, "ncols", len(result.columns))
        print("COLUMNS", result.columns)
        if result.rows:
            print("SAMPLE", json.dumps(result.rows[0], default=str)[:2000])
        break
    except Exception as exc:
        print("FAIL", rid, type(exc).__name__, str(exc)[:250])
