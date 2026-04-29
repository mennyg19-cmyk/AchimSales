"""Report registry for v2.

Each report is a tiny dataclass describing what the filter page should show
and how the report should appear in lists. The actual data-fetching and
layout live in the blueprint + templates, not here.

Mirrors the 7 reports from the live app (webapp/user_map.py REPORTS_CONFIG)
so the rebuild stays feature-parity with what users already know.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Report:
    key: str
    name: str
    description: str
    icon: str = "file-text"

    # Filter-page capabilities (match the old app's per-report flags).
    has_period: bool       = False
    has_status: bool       = False
    has_year: bool         = False
    salesman_filter: bool  = False
    customer_filter: bool  = False

    # Has the report been wired to a real data source? Disabled reports
    # are hidden from the homepage and refuse to render the filter form.
    # Flip to True as each one gets its on-prem stored procedure.
    enabled: bool = False


REPORTS: dict[str, Report] = {
    r.key: r
    for r in [
        Report(
            key="ordered",
            name="Ordered Report",
            description="Sales orders: ordered, shipped, cancelled, remaining.",
            icon="package",
            has_period=True,
            has_status=True,
            salesman_filter=True,
            customer_filter=True,
            enabled=True,   # <-- wired to salesline_release
        ),
        Report(
            key="invoiced",
            name="Invoiced Report",
            description="Invoices with commissions and freight details.",
            icon="file-text",
            has_period=True,
            salesman_filter=True,
            customer_filter=True,
        ),
        Report(
            key="salesman",
            name="Salesman Report",
            description="Monthly salesman comparison: current vs prior year.",
            icon="users",
            has_year=True,
            salesman_filter=True,
        ),
        Report(
            key="number_4",
            name="Number 4 Report",
            description="Invoice lines by item and by customer (rolling 12 months).",
            icon="bar-chart-2",
        ),
        Report(
            key="amazon_weekly",
            name="Amazon Weekly",
            description="Amazon (customers 9300, 9301) orders for the last 7 days.",
            icon="shopping-cart",
        ),
        Report(
            key="customer_activity",
            name="Customer Activity",
            description="All customers with last order info, split by salesman.",
            icon="activity",
            salesman_filter=True,
        ),
        Report(
            key="customer_aging",
            name="Customer Aging Report",
            description="Aged balances by customer with buckets (Current, 30, 60, 90, 91+).",
            icon="clock",
            salesman_filter=True,
            customer_filter=True,
        ),
    ]
}


def list_reports(*, include_disabled: bool = False) -> list[Report]:
    """Reports in display order. By default only enabled (wired) ones."""
    rs = list(REPORTS.values())
    if include_disabled:
        return rs
    return [r for r in rs if r.enabled]


def get_report(key: str) -> Report:
    """Look up a report by key. Raises KeyError if not registered."""
    return REPORTS[key]
