"""Adapter: invoice_lines SP rows -> InvoiceItemFact (Number 4 report).

The invoice_lines SP returns one row per invoiced item line:
InvoiceAccount, CustomerName, InvoiceDate, Invoice, SalesOrder, Amount,
SalesGroup, Item, ItemName, ExternalItemID, InventQTY, SalesPrice,
InventCostAmount. Quantity is InventQTY; line dollars are Amount.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from report_engine.facts import InvoiceItemFact
from report_engine.lib import first_of, iso_date, num, text


def to_fact(raw: Mapping) -> InvoiceItemFact:
    return InvoiceItemFact(
        source="reporting_api",
        invoice_number=text(first_of(raw, "Invoice", "InvoiceNumber", "InvoiceId")),
        invoice_date=iso_date(first_of(raw, "InvoiceDate", "Invoice Date")),
        customer_account=text(first_of(raw, "InvoiceAccount", "CustomerAccount", "AccountNum")),
        customer_name=text(first_of(raw, "CustomerName", "customername", "Name")),
        sales_group=text(first_of(raw, "SalesGroup", "salesgroup", "Salesman")),
        sales_order_number=text(first_of(raw, "SalesOrder", "SalesOrderNumber", "SalesId")),
        item_number=text(first_of(raw, "Item", "ItemId", "Item#", "ItemNumber")),
        item_name=text(first_of(raw, "ItemName", "ItemDescription")),
        qty=num(first_of(raw, "InventQTY", "Qty", "Quantity")),
        amount=num(first_of(raw, "Amount", "Total_$", "TotalAmount")),
    )


def to_facts(rows: Iterable[Mapping]) -> list[InvoiceItemFact]:
    return [to_fact(r) for r in rows]
