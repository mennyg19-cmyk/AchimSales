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
    # Optional role-specific labels for salesman users.
    name_salesman: str = ""
    description_salesman: str = ""

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

    # ``in_app_only`` reports skip the standard filter-form -> viewer
    # flow. Their card on the homepage links straight to a custom
    # route. Used for things like "Customer's Last Order" where the
    # interaction model is "pick a customer, see their detail page".
    in_app_only: bool = False
    # Endpoint name for the custom landing route (only consulted when
    # in_app_only is True).
    in_app_endpoint: str = ""

    # Bump when the builder's output shape or semantics change in a
    # way that should invalidate cached payloads. Folded into the
    # cache_first key so a deploy with a real fix doesn't keep
    # serving the pre-fix Excel from yesterday's cache. Stays at 1
    # for reports we haven't had to re-version yet.
    builder_version: int = 1


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
            name_salesman="Shipped Report",
            description_salesman="Your shipped orders with commissions and freight details.",
            icon="file-text",
            has_period=True,
            salesman_filter=True,
            customer_filter=True,
            enabled=True,   # <-- wired to invoiced_order_charges
            # v2 = SL_TariffCharges fix (line-level vs header-level)
            # v3 = monthly YTD commissions tab + UI redesign
            # v4 = InvoiceDate normalized to YYYY-MM-DD (kills tz day-shift)
            #      + full salesman master resolution (emailless reps)
            builder_version=4,
        ),
        Report(
            key="salesman",
            name="Salesman Report",
            description="Monthly salesman comparison: current vs prior year.",
            icon="users",
            has_year=True,
            salesman_filter=False,
            enabled=True,   # <-- wired to invoiced_order_charges
            # v2 = SL_TariffCharges fix (shared with invoiced)
            # v3 = full salesman master resolution (emailless reps)
            builder_version=3,
        ),
        Report(
            key="number_4",
            name="Number 4 Report",
            description="Invoice lines by item and by customer (rolling 12 months).",
            icon="bar-chart-2",
            enabled=True,   # <-- wired to invoice_lines
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
            enabled=True,   # <-- wired to customer_master + salesline_release
        ),
        Report(
            key="customer_last_order",
            name="Customer's Last Order",
            description="Pick a customer, see their last invoiced order.",
            icon="user-check",
            enabled=True,           # wired to salesline_release SP (invoiced filter)
            in_app_only=True,
            in_app_endpoint="customer_last_order.pick",
        ),
        Report(
            key="customer_aging",
            name="Customer Aging Report",
            description="Aged balances by customer with buckets (Current, 30, 60, 90, 91+).",
            name_salesman="Customer Aging",
            description_salesman="Your customers' aged balances with aging buckets.",
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
