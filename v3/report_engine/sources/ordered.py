"""Adapters: SP rows -> OrderLineFact.

Two stored procedures feed OrderLineFact:

  * salesline_release (to_fact / to_facts) - powers Customer Activity and
    Customer's Last Order. Returns authoritative shipped quantity and dollar
    columns from WHS + packing-slip data, plus SalesOrderName, PO#, header status.

  * rpt.usp_ordered_report (to_fact_ordered_report / to_facts_ordered_report) -
    powers the Ordered report. Qty columns are taken as the SP sends them
    (ordered / reserved / released / cancelled / delivery remainder). No
    QtyShipped derivation. SalesOrderName maps to customer name. PO # comes from
    CustomerRequisition. Also maps purchid + ExpectedArrivalDate. Header
    OrderStatus stays blank until the SP provides it.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from report_engine.facts import OrderLineFact
from report_engine.lib import as_int, first_of, iso_date, map_release, num, text

# Customer Activity's "last order" needs a true order/created date, so we only
# accept those here - never a requested ship/receipt date (LIVE uses the header
# OrderDate). The ordered report shows the same OrderDate.
_ORDER_DATE_KEYS = ("OrderDate", "OrderCreationDateTime", "CreatedDateTime")
# Ordered Full Data shows Ship Date when the SP starts sending it. Any of these
# names is enough; missing/blank stays "" and must not fail the build.
_SHIP_DATE_KEYS = (
    "ShipDate", "ShippingDate", "RequestedShippingDate", "ConfirmedShipDate",
    "DlvDate", "ShippingDateRequested", "ReceiptDateRequested", "shipdate",
)


def _optional_ship_date(raw: Mapping) -> str:
    return iso_date(first_of(raw, *_SHIP_DATE_KEYS))


_REMAINDER_DOLLAR_KEYS = (
    "DeliveryRemainderDollarAmount",
    "Delivery Remainder Dollar Amount",
    "delivery remainder dollar amount",
    "DeliveryRemainderAmount",
    "DeliveryRemainderDollars",
    "DeliveryRemainder $",
)


def _optional_remainder_dollars(raw: Mapping) -> float | None:
    value = first_of(raw, *_REMAINDER_DOLLAR_KEYS)
    if value is None:
        return None
    return round(num(value), 2)


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
        qty_reserved=num(first_of(raw, "QuantityReserved", "QtyReserved")),
        delivery_remainder=num(first_of(raw, "DeliveryRemainder", "QuantityRemainder", "QtyRemainder")),
        qty_left_to_load=num(first_of(raw, "QuantityLefttoLoad", "QtyLeftToLoad")),
        ordered_dollars=round(num(first_of(raw, "Ordered $", "OrderedDollars", "OrderedAmount")), 2),
        shipped_dollars=round(num(first_of(raw, "Shipped $", "ShippedDollars", "ShippedAmount")), 2),
        cancelled_dollars=round(num(first_of(raw, "Cancelled $", "CancelledDollars", "CancelledAmount")), 2),
        ship_date=_optional_ship_date(raw),
    )


def to_facts(rows: Iterable[Mapping]) -> list[OrderLineFact]:
    return map_release(rows, to_fact)


def to_fact_ordered_report(raw: Mapping) -> OrderLineFact:
    """One rpt.usp_ordered_report row -> OrderLineFact.

    Qty columns come straight from the SP. qty_shipped stays 0 (SP has no shipped
    quantity). SalesOrderName uses the customer name. PO # = CustomerRequisition.
    purchid / ExpectedArrivalDate come from the SP when present.
    OrderStatus blank until the SP provides it.
    """
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
        po_number=text(first_of(raw, "CustomerRequisition", "CustomerReq", "PONumber", "PO #")),
        line_number=as_int(first_of(raw, "LineNumber", "LineNum")),
        item_number=text(first_of(raw, "Item", "ItemId", "ItemNumber", "Item#")),
        item_name=text(first_of(raw, "ItemDescription", "ItemName", "LineDescription")),
        unit_price=round(num(first_of(raw, "SalesPrice", "UnitPrice")), 4),
        status=text(first_of(raw, "SalesStatus", "Status")),
        order_status="",
        qty_ordered=num(first_of(raw, "QuantityOrdered", "QtyOrdered")),
        qty_shipped=0.0,
        qty_cancelled=num(first_of(raw, "CancelledQTY", "CancelledQuantity", "QuantityCancelled")),
        qty_released=num(first_of(raw, "ReleasedQuantity", "QtyReleased")),
        qty_reserved=num(first_of(raw, "QuantityReserved", "QtyReserved")),
        delivery_remainder=num(first_of(raw, "DeliveryRemainder", "QuantityRemainder", "QtyRemainder")),
        qty_left_to_load=0.0,
        ordered_dollars=round(num(first_of(raw, "Ordered $", "OrderedDollars", "OrderedAmount")), 2),
        shipped_dollars=round(num(first_of(raw, "Shipped $", "ShippedDollars", "ShippedAmount")), 2),
        cancelled_dollars=round(num(first_of(raw, "Cancelled $", "CancelledDollars", "CancelledAmount")), 2),
        purch_id=text(first_of(raw, "purchid", "PurchId", "PurchID")),
        expected_arrival_date=iso_date(first_of(
            raw, "ExpectedArrivalDate", "expectedarrivaldate", "ExpectedArrival")),
        ship_date=_optional_ship_date(raw),
        delivery_remainder_dollars=_optional_remainder_dollars(raw),
    )


def to_facts_ordered_report(rows: Iterable[Mapping]) -> list[OrderLineFact]:
    return map_release(rows, to_fact_ordered_report)
