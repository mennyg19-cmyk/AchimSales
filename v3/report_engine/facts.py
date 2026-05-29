"""Typed report facts - the semantic layer between data sources and builders.

A "fact" is one business row in a source-agnostic, normalized shape. Source
adapters (sources/) produce facts from either the on-prem Reporting API (web
path) or D365 OData (CLI/runbook path); builders (reports/) consume ONLY facts.
This is what lets the parity harness separate *rule* drift from *source* drift:
feed identical facts to two builders and the only difference can be the rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Source = Literal["reporting_api", "odata"]


@dataclass(frozen=True)
class OrderLineFact:
    """One sales-order line (ordered report, dashboard)."""
    source: Source
    order_number: str
    order_date: str
    customer_account: str
    customer_name: str
    sales_group: str
    item_number: str
    item_name: str
    qty_ordered: int
    qty_released: int
    qty_shipped: int
    qty_remaining: int
    line_amount: float
    status: str
    raw: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class InvoiceLineFact:
    """One invoiced charge line (invoiced report)."""
    source: Source
    invoice_number: str
    invoice_date: str
    customer_account: str
    customer_name: str
    sales_group: str
    item_number: str
    amount: float
    tariff_charges: float
    is_credit: bool
    raw: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class CustomerFact:
    """One customer master record (customer activity / last order)."""
    source: Source
    customer_account: str
    customer_name: str
    sales_group: str
    last_order_date: str
    raw: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class SalesmanFact:
    """One salesman master record (salesman report, scoping)."""
    source: Source
    key: str
    number: str
    full_name: str
    display_name: str
    commission_pct: float
    raw: dict = field(default_factory=dict, compare=False, repr=False)
