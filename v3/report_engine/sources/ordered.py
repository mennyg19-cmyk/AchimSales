"""Adapter: salesline_release SP rows -> OrderLineFact.

Field names confirmed against a real SP dump (test/fixtures/ordered_dump.json):
QuantityOrdered, ReleasedQuantity, DeliveryRemainder, QuantityLefttoLoad,
SalesPrice, and precomputed `Ordered $` / `Shipped $` / `Cancelled $`
(authoritative - the SP applies the WHS/packing-slip math server-side).
"""

from __future__ import annotations

from typing import Iterable, Mapping

from report_engine.facts import OrderLineFact
from report_engine.lib import as_int, first_of, iso_date, num, text

# Customer Activity's "last order" needs a true order/created date, so we only
# accept those here - never a requested ship/receipt date (LIVE uses the header
# OrderDate). The ordered report shows the same OrderDate.
_ORDER_DATE_KEYS = ("OrderDate", "OrderCreationDateTime", "CreatedDateTime")


def to_fact(raw: Mapping) -> OrderLineFact:
    return OrderLineFact(
        source="reporting_api",
        company=text(first_of(raw, "Company", "DataAreaId")),
        sales_order_number=text(first_of(raw, "SalesOrderNumber", "SalesId", "OrderNumber")),
        sales_order_name=text(first_of(raw, "SalesOrderName", "SalesName", "OrderName")),
        order_date=iso_date(first_of(raw, *_ORDER_DATE_KEYS)),
        customer_account=text(first_of(raw, "CustomerAccount", "customeraccount", "AccountNum")),
        customer_name=text(first_of(raw, "customername", "CustomerName", "Name")),
        sales_group=text(first_of(raw, "SalesGroup", "salesgroup", "Salesman")),
        po_number=text(first_of(raw, "CustomerRequisition", "CustomerReq", "PONumber", "PO #")),
        line_number=as_int(first_of(raw, "LineNumber", "LineNum")),
        item_number=text(first_of(raw, "Item", "ItemId", "ItemNumber", "Item#")),
        item_name=text(first_of(raw, "ItemDescription", "ItemName", "LineDescription")),
        unit_price=round(num(first_of(raw, "SalesPrice", "UnitPrice")), 4),
        status=text(first_of(raw, "SalesStatus", "Status")),
        order_status=text(first_of(raw, "OrderStatus", "orderstatus", "HeaderStatus")),
        qty_ordered=num(first_of(raw, "QuantityOrdered", "QtyOrdered")),
        qty_shipped=num(first_of(raw, "ShippedQuantity", "QuantityShipped", "QtyShipped")),
        qty_released=num(first_of(raw, "ReleasedQuantity", "QtyReleased")),
        delivery_remainder=num(first_of(raw, "DeliveryRemainder", "QuantityRemainder", "QtyRemainder")),
        qty_left_to_load=num(first_of(raw, "QuantityLefttoLoad", "QtyLeftToLoad")),
        ordered_dollars=round(num(first_of(raw, "Ordered $", "OrderedDollars", "OrderedAmount")), 2),
        shipped_dollars=round(num(first_of(raw, "Shipped $", "ShippedDollars", "ShippedAmount")), 2),
        cancelled_dollars=round(num(first_of(raw, "Cancelled $", "CancelledDollars", "CancelledAmount")), 2),
        raw=dict(raw),
    )


def to_facts(rows: Iterable[Mapping]) -> list[OrderLineFact]:
    return [to_fact(r) for r in rows]
