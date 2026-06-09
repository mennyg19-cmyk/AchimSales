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
    """One sales-order line from salesline_release (ordered report, dashboard).

    Source-shaped. The SP returns authoritative dollar columns
    (ordered/shipped/cancelled) computed server-side from WHS + packing-slip
    data, plus authoritative qty_shipped and qty_cancelled.
    """
    source: Source
    company: str
    sales_order_number: str
    sales_order_name: str
    order_date: str            # 'YYYY-MM-DD' or ''
    customer_account: str
    customer_name: str
    sales_group: str
    po_number: str
    line_number: int
    item_number: str
    item_name: str
    unit_price: float
    status: str
    order_status: str
    # Quantities are floats (LIVE keeps them numeric; the SP may return
    # fractional units) - never int-truncated before aggregation.
    qty_ordered: float
    qty_shipped: float
    qty_cancelled: float
    qty_released: float
    delivery_remainder: float
    qty_left_to_load: float
    ordered_dollars: float     # authoritative (server-side)
    shipped_dollars: float     # authoritative (server-side)
    cancelled_dollars: float   # authoritative (server-side)
    raw: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class InvoiceChargeFact:
    """One invoiced-order-charges row (invoiced + salesman reports).

    Source-shaped: money split into subtotal + the three charge buckets, with
    `total` = subtotal + tariff + freight + cc. Salesman LABEL resolution is the
    builder's job (it owns the live business mapping); the fact carries only the
    raw `sales_group` so the same fact can feed multiple builders.
    """
    source: Source
    invoice_number: str
    invoice_date: str          # 'YYYY-MM-DD' (day precision) or ''
    customer_account: str
    customer_name: str
    sales_order_number: str
    subtotal: float
    tariff: float
    freight: float
    cc: float
    total: float
    sales_group: str
    is_credit: bool
    raw: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class InvoiceItemFact:
    """One invoice LINE (item-level) from the invoice_lines SP (Number 4 report).

    Distinct from InvoiceChargeFact: that one is charge-level (one row per
    invoice with the subtotal/tariff/freight/cc split); this one is line-level
    (one row per invoiced item) carrying item, quantity, and line amount.
    """
    source: Source
    invoice_number: str
    invoice_date: str          # 'YYYY-MM-DD' or ''
    customer_account: str
    customer_name: str
    sales_group: str
    sales_order_number: str    # blank = free-text line (LIVE excludes these)
    item_number: str
    item_name: str
    qty: float
    amount: float
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
