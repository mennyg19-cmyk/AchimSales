"""Stub "run the report" layer.

In production this is where we call the stored procedure and shape its
rows into the tab structure the viewer expects. For the Phase-3 sandbox
we return deterministic mock data so the multi-tab grid + Excel export
can be exercised end-to-end.

Output shape (what the /api/reports/<key>/run endpoint serialises):

    {
        "report_key":   "ordered",
        "report_name":  "Ordered Report",
        "generated_at": "2026-04-16T10:00:00Z",
        "params":       { ... echoed filter params ... },
        "tabs": [
            {
                "key":     "summary",
                "name":    "Summary by Salesman",
                "columns": [
                    {"field": "salesman", "header": "Salesman", "type": "text"},
                    ...
                ],
                "rows": [
                    {"salesman": "Alex Morgan", ... },
                    ...
                ]
            },
            ...
        ]
    }

Column types drive formatting in both the grid and the Excel export:
    text  | int | money | percent | date
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from test.webapp.services.mock_data import CUSTOMERS, SALESMEN, salesman_name
from test.webapp.services.reports import ordered as ordered_builder
from test.webapp.services import reporting_api

log = logging.getLogger(__name__)


# Path to the JSON fixture stashed from the brother's test dump.
# Used as a fallback when SQL isn't configured (local dev, tests).
_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"
_ORDERED_FIXTURE = _FIXTURE_DIR / "ordered_dump.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed(report_key: str, params: dict) -> random.Random:
    """Deterministic RNG so the same filters always return the same rows."""
    key = f"{report_key}|" + "|".join(f"{k}={params.get(k)}" for k in sorted(params))
    return random.Random(hash(key) & 0xFFFFFFFF)


def _money(r: random.Random, lo: float, hi: float) -> float:
    return round(r.uniform(lo, hi), 2)


def _filtered_customers(params: dict) -> list[dict]:
    chosen = params.get("customers") or []
    if isinstance(chosen, str):
        chosen = [chosen]
    sales_filter = params.get("salesman")

    rows = list(CUSTOMERS)
    if sales_filter:
        rows = [c for c in rows if c["salesman"] == str(sales_filter)]
    if chosen:
        rows = [c for c in rows if c["key"] in chosen]
    return rows


def _filtered_salesmen(params: dict) -> list[dict]:
    sm = params.get("salesman")
    if sm:
        return [s for s in SALESMEN if s["key"] == str(sm)]
    return list(SALESMEN)


def _recent_date(r: random.Random, days_back: int = 90) -> str:
    d = date.today() - timedelta(days=r.randint(0, days_back))
    return d.isoformat()


# ---------------------------------------------------------------------------
# Per-report builders
# ---------------------------------------------------------------------------


def _load_ordered_fixture() -> list[dict] | None:
    """Load the brother's test dump as the offline source-of-truth for the
    ordered report. Returns None if the fixture is missing or unreadable.
    """
    if not _ORDERED_FIXTURE.exists():
        return None
    try:
        with _ORDERED_FIXTURE.open(encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not read ordered fixture %s: %s", _ORDERED_FIXTURE, exc)
    return None


def _build_ordered(params: dict, r: random.Random) -> tuple[list[dict], dict]:
    """Build the ordered report's multi-tab payload + source metadata.

    Returns ``(tabs, source_meta)``. ``source_meta`` describes where the
    rows came from so the viewer can show a "Source: ..." badge.

    Source-selection order:
        1. Reporting API (on-prem via Hybrid Connection) — preferred
           when REPORTING_API_BASE_URL is set. The client also handles
           fresh + stale caching internally.
        2. JSON fixture stashed in test/fixtures/ordered_dump.json — used
           in local dev (no env vars) or if the API is unreachable AND
           no stale cache exists.
        3. Random mock as a final last resort.
    """
    rows: list[dict] | None = None
    source: dict[str, Any] = {"source": "unknown"}

    if reporting_api.is_configured() and os.environ.get("USE_REPORTING_API_ORDERED", "1") != "0":
        api_started = time.monotonic()
        try:
            rows = reporting_api.run("ordered", params)
            elapsed_ms = int((time.monotonic() - api_started) * 1000)
            log.info("ordered report: pulled %d rows from reporting API in %d ms",
                     len(rows), elapsed_ms)
            source = {
                "source":       "reporting_api",
                "label":        "Reporting API (live data)",
                "rows_fetched": len(rows),
                "elapsed_ms":   elapsed_ms,
                "timeout_s":    int(os.environ.get("REPORTING_API_TIMEOUT_SECONDS", "120")),
                "endpoint":     f"{os.environ.get('REPORTING_API_BASE_URL', '').rstrip('/')}/api/reports/salesline_release/run",
            }
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - api_started) * 1000)
            log.exception(
                "Reporting API fetch for ordered failed after %d ms, falling back to fixture: %s",
                elapsed_ms, exc,
            )
            rows = None
            source = {
                "source":     "reporting_api_failed",
                "label":      "API call failed — see fallback below",
                "error":      str(exc),
                "elapsed_ms": elapsed_ms,
                "timeout_s":  int(os.environ.get("REPORTING_API_TIMEOUT_SECONDS", "120")),
            }

    if rows is None:
        fixture_rows = _load_ordered_fixture()
        if fixture_rows is not None:
            log.info("ordered report: using fixture (%d rows)", len(fixture_rows))
            rows = _filter_ordered_fixture(fixture_rows, params)
            previous = source if source.get("source") == "reporting_api_failed" else None
            source = {
                "source": "fixture",
                "label":  "Fixture (test data dump) — not real data",
                "rows_fetched": len(rows),
                "fixture_file": str(_ORDERED_FIXTURE),
            }
            if previous:
                source["api_error"] = previous.get("error")
                if previous.get("elapsed_ms") is not None:
                    source["elapsed_ms"] = previous["elapsed_ms"]
                if previous.get("timeout_s") is not None:
                    source["timeout_s"] = previous["timeout_s"]

    if rows is not None:
        return ordered_builder.build(rows), source

    log.warning("ordered report: no API + no fixture, using random mock")
    tabs = _build_ordered_random_mock(params, r)
    source = {
        "source": "random_mock",
        "label":  "Random mock data — totally synthetic",
    }
    return tabs, source


def _filter_ordered_fixture(rows: list[dict], params: dict) -> list[dict]:
    """Apply a few obvious filters to the fixture so the viewer reflects the
    chosen filter values during local development.
    """
    out = rows
    status = params.get("status")
    if status:
        out = [r for r in out if (r.get("SalesStatus") or "").lower() == str(status).lower()]
    customers = params.get("customers")
    if customers:
        if isinstance(customers, str):
            customers = [customers]
        wanted = {str(c) for c in customers}
        out = [r for r in out if str(r.get("CustomerAccount")) in wanted]
    return out


def _build_ordered_random_mock(params: dict, r: random.Random) -> list[dict]:
    """Original Phase-3 random mock — kept as a final fallback."""
    customers = _filtered_customers(params)
    statuses = ["Open", "Shipped", "Partial", "Cancelled"]
    pool = customers or CUSTOMERS[:10]

    fake_rows: list[dict] = []
    for i in range(min(40, max(10, len(pool) * 2))):
        c = r.choice(pool)
        qty = r.randint(5, 500)
        shipped_qty = r.randint(0, qty)
        unit = _money(r, 4, 55)
        ordered_amt = round(qty * unit, 2)
        shipped_amt = round(shipped_qty * unit, 2)
        cancelled_amt = 0.0
        fake_rows.append({
            "Company": "achm",
            "CustomerAccount": c["key"],
            "customername": c["name"],
            "SalesOrderNumber": f"ORD{100000 + r.randint(0, 99999)}",
            "CustomerRequisition": "",
            "SalesGroup": salesman_name(c["salesman"]),
            "LineNumber": i + 1,
            "SalesStatus": r.choice(statuses),
            "Item": f"AC-{1000 + r.randint(0, 999)}",
            "ItemDescription": "Mock item",
            "QuantityOrdered": qty,
            "QuantityReserved": 0,
            "ReleasedQuantity": shipped_qty,
            "DeliveryRemainder": qty - shipped_qty,
            "QuantityLefttoLoad": 0,
            "SalesPrice": unit,
            "Ordered $": ordered_amt,
            "Shipped $": shipped_amt,
            "Cancelled $": cancelled_amt,
            "CreatedDateTime": _recent_date(r, 60),
            "ShippingDateRequested": _recent_date(r, 60),
            "InventoryTransactionID": str(r.randint(1_000_000, 9_999_999)),
        })
    return ordered_builder.build(fake_rows)


def _build_invoiced(params: dict, r: random.Random) -> list[dict]:
    salesmen = _filtered_salesmen(params)
    customers = _filtered_customers(params)

    summary_cols = [
        {"field": "salesman",         "header": "Salesman",      "type": "text"},
        {"field": "invoice_count",    "header": "# Invoices",    "type": "int"},
        {"field": "invoiced_amount",  "header": "Invoiced $",    "type": "money"},
        {"field": "commission_amount","header": "Commission $",  "type": "money"},
        {"field": "freight_amount",   "header": "Freight $",     "type": "money"},
    ]
    summary_rows = []
    for s in salesmen:
        invoiced = _money(r, 55_000, 260_000)
        summary_rows.append({
            "salesman":          s["name"],
            "invoice_count":     r.randint(10, 90),
            "invoiced_amount":   invoiced,
            "commission_amount": round(invoiced * r.uniform(0.02, 0.08), 2),
            "freight_amount":    round(invoiced * r.uniform(0.01, 0.04), 2),
        })

    detail_cols = [
        {"field": "invoice_no",   "header": "Invoice #",    "type": "text"},
        {"field": "invoice_date", "header": "Invoice Date", "type": "date"},
        {"field": "customer",     "header": "Customer",     "type": "text"},
        {"field": "salesman",     "header": "Salesman",     "type": "text"},
        {"field": "qty",          "header": "Qty",          "type": "int"},
        {"field": "invoiced_amount", "header": "Invoiced $",    "type": "money"},
        {"field": "commission",      "header": "Commission $",  "type": "money"},
        {"field": "freight",         "header": "Freight $",     "type": "money"},
    ]
    detail_rows = []
    pool = customers or CUSTOMERS[:10]
    for i in range(min(45, max(12, len(pool) * 2))):
        c = r.choice(pool)
        qty = r.randint(20, 650)
        unit = _money(r, 3, 38)
        amount = round(qty * unit, 2)
        detail_rows.append({
            "invoice_no":      f"INV{500000 + r.randint(0, 99999)}",
            "invoice_date":    _recent_date(r, 90),
            "customer":        f"{c['key']} — {c['name']}",
            "salesman":        salesman_name(c["salesman"]),
            "qty":             qty,
            "invoiced_amount": amount,
            "commission":      round(amount * r.uniform(0.03, 0.07), 2),
            "freight":         round(amount * r.uniform(0.015, 0.035), 2),
        })

    return [
        {"key": "summary", "name": "Summary by Salesman", "columns": summary_cols, "rows": summary_rows},
        {"key": "detail",  "name": "Invoice Detail",       "columns": detail_cols,  "rows": detail_rows},
    ]


def _build_salesman(params: dict, r: random.Random) -> list[dict]:
    year = int(params.get("year") or date.today().year)
    salesmen = _filtered_salesmen(params)

    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    by_month_cols = [
        {"field": "month",       "header": "Month",            "type": "text"},
        {"field": "curr_amount", "header": f"{year} Sales $",  "type": "money"},
        {"field": "prior_amount","header": f"{year-1} Sales $","type": "money"},
        {"field": "variance",    "header": "Variance $",       "type": "money"},
        {"field": "pct_change",  "header": "% Change",         "type": "percent"},
    ]
    by_month_rows = []
    for m in months:
        curr = _money(r, 120_000, 340_000)
        prior = _money(r, 120_000, 340_000)
        variance = round(curr - prior, 2)
        pct = round((variance / prior) if prior else 0, 4)
        by_month_rows.append({
            "month":        m,
            "curr_amount":  curr,
            "prior_amount": prior,
            "variance":     variance,
            "pct_change":   pct,
        })

    by_sales_cols = [
        {"field": "salesman",     "header": "Salesman",         "type": "text"},
        {"field": "curr_amount",  "header": f"{year} Sales $",  "type": "money"},
        {"field": "prior_amount", "header": f"{year-1} Sales $","type": "money"},
        {"field": "variance",     "header": "Variance $",       "type": "money"},
        {"field": "pct_change",   "header": "% Change",         "type": "percent"},
    ]
    by_sales_rows = []
    for s in salesmen:
        curr = _money(r, 250_000, 1_400_000)
        prior = _money(r, 250_000, 1_400_000)
        variance = round(curr - prior, 2)
        pct = round((variance / prior) if prior else 0, 4)
        by_sales_rows.append({
            "salesman":     s["name"],
            "curr_amount":  curr,
            "prior_amount": prior,
            "variance":     variance,
            "pct_change":   pct,
        })

    return [
        {"key": "by_month",    "name": "By Month",    "columns": by_month_cols, "rows": by_month_rows},
        {"key": "by_salesman", "name": "By Salesman", "columns": by_sales_cols, "rows": by_sales_rows},
    ]


def _build_number_4(params: dict, r: random.Random) -> list[dict]:
    item_cols = [
        {"field": "item",        "header": "Item",        "type": "text"},
        {"field": "description", "header": "Description", "type": "text"},
        {"field": "qty_sold",    "header": "Qty Sold",    "type": "int"},
        {"field": "revenue",     "header": "Revenue $",   "type": "money"},
        {"field": "margin_pct",  "header": "Margin %",    "type": "percent"},
    ]
    descriptors = ["Throw Blanket", "Accent Rug", "Bath Towel Set", "Decorative Pillow",
                   "Shower Curtain", "Kitchen Towel", "Table Runner", "Comforter Set"]
    item_rows = []
    for i in range(25):
        qty = r.randint(200, 5200)
        price = _money(r, 6, 38)
        revenue = round(qty * price, 2)
        item_rows.append({
            "item":        f"AC-{1000 + i * 37 + r.randint(0, 30)}",
            "description": r.choice(descriptors),
            "qty_sold":    qty,
            "revenue":     revenue,
            "margin_pct":  round(r.uniform(0.22, 0.48), 4),
        })

    cust_cols = [
        {"field": "customer",    "header": "Customer",   "type": "text"},
        {"field": "qty_sold",    "header": "Qty Sold",   "type": "int"},
        {"field": "revenue",     "header": "Revenue $",  "type": "money"},
        {"field": "last_order",  "header": "Last Order", "type": "date"},
    ]
    cust_rows = []
    for c in CUSTOMERS[:20]:
        qty = r.randint(150, 4800)
        cust_rows.append({
            "customer":   f"{c['key']} — {c['name']}",
            "qty_sold":   qty,
            "revenue":    round(qty * _money(r, 6, 32), 2),
            "last_order": _recent_date(r, 365),
        })

    return [
        {"key": "by_item",     "name": "By Item",     "columns": item_cols, "rows": item_rows},
        {"key": "by_customer", "name": "By Customer", "columns": cust_cols, "rows": cust_rows},
    ]


def _build_amazon_weekly(_params: dict, r: random.Random) -> list[dict]:
    cols = [
        {"field": "order_no",    "header": "Order #",     "type": "text"},
        {"field": "order_date",  "header": "Order Date",  "type": "date"},
        {"field": "customer",    "header": "Customer",    "type": "text"},
        {"field": "item",        "header": "Item",        "type": "text"},
        {"field": "qty",         "header": "Qty",         "type": "int"},
        {"field": "amount",      "header": "Amount $",    "type": "money"},
    ]
    amazon_customers = [
        {"key": "9300", "name": "Amazon FBA"},
        {"key": "9301", "name": "Amazon Direct"},
    ]
    items = [f"AC-{1000 + i}" for i in range(40)]
    rows = []
    for i in range(28):
        c = r.choice(amazon_customers)
        qty = r.randint(12, 240)
        rows.append({
            "order_no":   f"AZ{700000 + r.randint(0, 99999)}",
            "order_date": _recent_date(r, 7),
            "customer":   f"{c['key']} — {c['name']}",
            "item":       r.choice(items),
            "qty":        qty,
            "amount":     round(qty * _money(r, 8, 42), 2),
        })
    return [{"key": "orders", "name": "Orders", "columns": cols, "rows": rows}]


def _build_customer_activity(params: dict, r: random.Random) -> list[dict]:
    cols = [
        {"field": "customer",    "header": "Customer",     "type": "text"},
        {"field": "salesman",    "header": "Salesman",     "type": "text"},
        {"field": "last_order",  "header": "Last Order",   "type": "date"},
        {"field": "last_invoice","header": "Last Invoice", "type": "date"},
        {"field": "ytd_amount",  "header": "YTD Sales $",  "type": "money"},
        {"field": "open_balance","header": "Open AR $",    "type": "money"},
    ]
    pool = _filtered_customers({"salesman": params.get("salesman")})
    rows = []
    for c in pool:
        rows.append({
            "customer":     f"{c['key']} — {c['name']}",
            "salesman":     salesman_name(c["salesman"]),
            "last_order":   _recent_date(r, 240),
            "last_invoice": _recent_date(r, 240),
            "ytd_amount":   _money(r, 2_000, 180_000),
            "open_balance": _money(r, 0, 28_000),
        })
    return [{"key": "all", "name": "All Customers", "columns": cols, "rows": rows}]


def _build_customer_aging(params: dict, r: random.Random) -> list[dict]:
    detail_cols = [
        {"field": "customer", "header": "Customer",   "type": "text"},
        {"field": "salesman", "header": "Salesman",   "type": "text"},
        {"field": "current",  "header": "Current $",  "type": "money"},
        {"field": "b30",      "header": "1-30 $",     "type": "money"},
        {"field": "b60",      "header": "31-60 $",    "type": "money"},
        {"field": "b90",      "header": "61-90 $",    "type": "money"},
        {"field": "b91",      "header": "91+ $",      "type": "money"},
        {"field": "total",    "header": "Total $",    "type": "money"},
    ]
    pool = _filtered_customers(params)
    detail_rows = []
    totals = {"current": 0.0, "b30": 0.0, "b60": 0.0, "b90": 0.0, "b91": 0.0, "total": 0.0}
    for c in pool:
        cur = _money(r, 0, 18_000)
        b30 = _money(r, 0, 9_000)
        b60 = _money(r, 0, 5_000)
        b90 = _money(r, 0, 3_500)
        b91 = _money(r, 0, 6_500)
        total = round(cur + b30 + b60 + b90 + b91, 2)
        detail_rows.append({
            "customer": f"{c['key']} — {c['name']}",
            "salesman": salesman_name(c["salesman"]),
            "current":  cur,
            "b30":      b30,
            "b60":      b60,
            "b90":      b90,
            "b91":      b91,
            "total":    total,
        })
        totals["current"] += cur; totals["b30"] += b30; totals["b60"] += b60
        totals["b90"] += b90; totals["b91"] += b91; totals["total"] += total

    bucket_cols = [
        {"field": "bucket", "header": "Bucket",  "type": "text"},
        {"field": "amount", "header": "Total $", "type": "money"},
    ]
    bucket_rows = [
        {"bucket": "Current", "amount": round(totals["current"], 2)},
        {"bucket": "1-30",    "amount": round(totals["b30"], 2)},
        {"bucket": "31-60",   "amount": round(totals["b60"], 2)},
        {"bucket": "61-90",   "amount": round(totals["b90"], 2)},
        {"bucket": "91+",     "amount": round(totals["b91"], 2)},
        {"bucket": "Total",   "amount": round(totals["total"], 2)},
    ]

    return [
        {"key": "by_customer", "name": "By Customer",   "columns": detail_cols, "rows": detail_rows},
        {"key": "buckets",     "name": "Aging Buckets", "columns": bucket_cols, "rows": bucket_rows},
    ]


_BUILDERS = {
    "ordered":           _build_ordered,
    "invoiced":          _build_invoiced,
    "salesman":          _build_salesman,
    "number_4":          _build_number_4,
    "amazon_weekly":     _build_amazon_weekly,
    "customer_activity": _build_customer_activity,
    "customer_aging":    _build_customer_aging,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_report(report_key: str, report_name: str, params: dict) -> dict[str, Any]:
    """Return the full multi-tab payload for a report.

    `params` is whatever landed in the URL query string on the view page --
    already normalised (``customers`` is a list, everything else is a
    single value). The stub echoes the params back so the client can show
    them and the Excel export can embed them.
    """
    builder = _BUILDERS.get(report_key)
    if builder is None:
        raise KeyError(f"No mock runner for report '{report_key}'")

    r = _seed(report_key, params)
    result = builder(params, r)

    # Builders may return either `tabs` (legacy mock builders) or
    # `(tabs, source_meta)` (the data-aware ordered builder).
    if isinstance(result, tuple):
        tabs, source_meta = result
    else:
        tabs = result
        source_meta = {
            "source": "random_mock",
            "label":  "Random mock data — totally synthetic",
        }

    return {
        "report_key":   report_key,
        "report_name":  report_name,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "params":       params,
        "tabs":         tabs,
        "data_source":  source_meta,
    }
