"""Adapters: SP rows -> OrderLineFact.

Two stored procedures feed OrderLineFact:

  * salesline_release (to_fact / to_facts) - the older SP that powers the
    Customer Activity and Customer's Last Order reports. It returns an
    authoritative shipped quantity and dollar columns computed server-side from
    WHS + packing-slip data, plus SalesOrderName, PO#, and header OrderStatus.

  * rpt.usp_ordered_report (to_fact_ordered_report / to_facts_ordered_report) -
    the newer, leaner SP that now powers the Ordered report. It returns the same
    dollar columns but NO shipped quantity, no SalesOrderName, no PO#, and no
    header status. See that function's docstring for how those gaps are filled.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from report_engine.facts import OrderLineFact
from report_engine.lib import as_int, first_of, iso_date, map_release, num, text

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
        qty_cancelled=num(first_of(raw, "CancelledQuantity", "QuantityCancelled", "QtyCancelled")),
        qty_released=num(first_of(raw, "ReleasedQuantity", "QtyReleased")),
        delivery_remainder=num(first_of(raw, "DeliveryRemainder", "QuantityRemainder", "QtyRemainder")),
        qty_left_to_load=num(first_of(raw, "QuantityLefttoLoad", "QtyLeftToLoad")),
        ordered_dollars=round(num(first_of(raw, "Ordered $", "OrderedDollars", "OrderedAmount")), 2),
        shipped_dollars=round(num(first_of(raw, "Shipped $", "ShippedDollars", "ShippedAmount")), 2),
        cancelled_dollars=round(num(first_of(raw, "Cancelled $", "CancelledDollars", "CancelledAmount")), 2),
    )


def to_facts(rows: Iterable[Mapping]) -> list[OrderLineFact]:
    return map_release(rows, to_fact)


def to_fact_ordered_report(raw: Mapping) -> OrderLineFact:
    """One rpt.usp_ordered_report row -> OrderLineFact.

    The new SP returns fewer columns than salesline_release, so three values are
    filled in here (decisions signed off by the owner, logged in REVIEW-LOG):

      * qty_shipped: the new SP gives no shipped quantity, only Shipped $. We
        derive it from the D365 identity Ordered = Shipped + Cancelled +
        Remaining, so QtyShipped = QtyOrdered - Cancelled - DeliveryRemainder
        (floored at 0). Under this, QtyOpen comes out equal to DeliveryRemainder.
      * sales_order_name: not in the new SP; the owner mapped this column to the
        customer name.
      * po_number / order_status: not in the new SP; left blank (stub) and flagged
        in the builder until the DBA adds them to the SP.
    """
    qty_ordered = num(first_of(raw, "QuantityOrdered", "QtyOrdered"))
    qty_cancelled = num(first_of(raw, "CancelledQTY", "CancelledQuantity", "QuantityCancelled"))
    delivery_remainder = num(first_of(raw, "DeliveryRemainder", "QuantityRemainder", "QtyRemainder"))
    qty_shipped = max(0.0, qty_ordered - qty_cancelled - delivery_remainder)
    customer_name = text(first_of(raw, "customername", "CustomerName", "Name"))
    return OrderLineFact(
        source="reporting_api",
        company="",
        sales_order_number=text(first_of(raw, "SalesOrderNumber", "SalesId", "OrderNumber")),
        sales_order_name=customer_name,
        order_date=iso_date(first_of(raw, "CreatedDateTime", "OrderDate")),
        customer_account=text(first_of(raw, "CustomerAccount", "customeraccount", "AccountNum")),
        customer_name=customer_name,
        sales_group=text(first_of(raw, "SalesGroup", "salesgroup", "Salesman")),
        po_number="",
        line_number=as_int(first_of(raw, "LineNumber", "LineNum")),
        item_number=text(first_of(raw, "Item", "ItemId", "ItemNumber", "Item#")),
        item_name=text(first_of(raw, "ItemDescription", "ItemName", "LineDescription")),
        unit_price=round(num(first_of(raw, "SalesPrice", "UnitPrice")), 4),
        status=text(first_of(raw, "SalesStatus", "Status")),
        order_status="",
        qty_ordered=qty_ordered,
        qty_shipped=qty_shipped,
        qty_cancelled=qty_cancelled,
        qty_released=num(first_of(raw, "ReleasedQuantity", "QtyReleased")),
        delivery_remainder=delivery_remainder,
        qty_left_to_load=0.0,
        ordered_dollars=round(num(first_of(raw, "Ordered $", "OrderedDollars", "OrderedAmount")), 2),
        shipped_dollars=round(num(first_of(raw, "Shipped $", "ShippedDollars", "ShippedAmount")), 2),
        cancelled_dollars=round(num(first_of(raw, "Cancelled $", "CancelledDollars", "CancelledAmount")), 2),
    )


def to_facts_ordered_report(rows: Iterable[Mapping]) -> list[OrderLineFact]:
    return map_release(rows, to_fact_ordered_report)
