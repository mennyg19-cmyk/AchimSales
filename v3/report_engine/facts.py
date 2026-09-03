"""Typed report facts - the semantic layer between data sources and builders.

A "fact" is one business row in a source-agnostic, normalized shape. Source
adapters (sources/) produce facts from either the on-prem Reporting API (web
path) or D365 OData (CLI/runbook path); builders (reports/) consume ONLY facts.
This is what lets the parity harness separate *rule* drift from *source* drift:
feed identical facts to two builders and the only difference can be the rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Source = Literal["reporting_api", "odata"]


@dataclass(frozen=True)
class OrderLineFact:
    """One sales-order line (ordered report / customer last order / dashboard).

    Dollar columns are authoritative from the SP when present. Qty fields depend
    on which SP fed the row: ``usp_ordered_report`` has reserved + delivery
    remainder (no shipped qty); ``salesline_release`` has shipped qty.
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
    qty_reserved: float
    delivery_remainder: float   # "qty left to ship" on usp_ordered_report
    qty_left_to_load: float
    ordered_dollars: float     # authoritative (server-side)
    shipped_dollars: float     # authoritative (server-side)
    cancelled_dollars: float   # authoritative (server-side)
    # usp_ordered_report only (blank on salesline_release).
    purch_id: str = ""
    expected_arrival_date: str = ""  # 'YYYY-MM-DD' or ''
    ship_date: str = ""              # 'YYYY-MM-DD' or '' when the SP has no Ship Date yet
    shipping_dollars: float = 0.0  # usp_ordered_report ShippingDollars; 0 if absent


@dataclass(frozen=True)
class InvoiceChargeFact:
    """One invoice row from `rpt.usp_invoiced_report` (invoiced + salesman reports).

    Source-shaped: SQL returns invoice-level money columns and salesman labels.
    The SP also sends the salesman's commission rate per row (`commission`); the
    salesman master is the fallback when a row doesn't carry one.

    commission_pct is a fraction (0.06 = 6%), matching the master + live math.
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
    misc: float
    total: float
    sales_group: str
    salesman_name: str = ""
    is_credit: bool = False
    commission_pct: float = 0.0


@dataclass(frozen=True)
class CustomerFact:
    """One customer master record (customer activity / last order)."""
    source: Source
    customer_account: str
    customer_name: str
    sales_group: str
    last_order_date: str


@dataclass(frozen=True)
class SalesmanFact:
    """One salesman master record from the salesmen_master SP (names, commission)."""
    source: Source
    key: str
    full_name: str
    display_name: str
    commission_pct: float
