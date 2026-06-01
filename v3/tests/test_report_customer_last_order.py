"""Customer's Last Order builder: invoiced-only history, default-to-latest,
merge + (item, price) rollup, and PO-prefix display."""

from report_engine.reports import customer_last_order as B
from report_engine.sources import ordered as S


def _rows():
    # Two invoiced orders + one open (must be excluded from the history).
    return [
        # Newest invoiced order SO3 (2026-03-10): item A qty 10, all shipped.
        {"SalesOrderNumber": "SO3", "CustomerAccount": "100", "customername": "Acme",
         "SalesGroup": "REdwards", "OrderStatus": "Invoiced", "OrderDate": "2026-03-10",
         "CustomerRequisition": "PO-555", "LineNumber": "1", "Item": "ITM-A",
         "ItemDescription": "Widget", "SalesPrice": "2.00", "SalesStatus": "Delivered",
         "QuantityOrdered": "10", "ReleasedQuantity": "10", "DeliveryRemainder": "0",
         "QuantityLefttoLoad": "0", "Ordered $": "20.00", "Shipped $": "20.00", "Cancelled $": "0"},
        # Older invoiced order SO2 (2026-02-01): item A qty 5 @2.00, item B qty 3 @5.00.
        {"SalesOrderNumber": "SO2", "CustomerAccount": "100", "customername": "Acme",
         "SalesGroup": "REdwards", "OrderStatus": "Partially invoiced", "OrderDate": "2026-02-01",
         "CustomerRequisition": "PO-555-addon", "LineNumber": "1", "Item": "ITM-A",
         "ItemDescription": "Widget", "SalesPrice": "2.00", "SalesStatus": "Delivered",
         "QuantityOrdered": "5", "ReleasedQuantity": "5", "DeliveryRemainder": "0",
         "QuantityLefttoLoad": "0", "Ordered $": "10.00", "Shipped $": "10.00", "Cancelled $": "0"},
        {"SalesOrderNumber": "SO2", "CustomerAccount": "100", "customername": "Acme",
         "SalesGroup": "REdwards", "OrderStatus": "Partially invoiced", "OrderDate": "2026-02-01",
         "CustomerRequisition": "PO-555-addon", "LineNumber": "2", "Item": "ITM-B",
         "ItemDescription": "Gadget", "SalesPrice": "5.00", "SalesStatus": "Delivered",
         "QuantityOrdered": "3", "ReleasedQuantity": "3", "DeliveryRemainder": "0",
         "QuantityLefttoLoad": "0", "Ordered $": "15.00", "Shipped $": "15.00", "Cancelled $": "0"},
        # Open order SO9 - never part of the invoiced history.
        {"SalesOrderNumber": "SO9", "CustomerAccount": "100", "customername": "Acme",
         "SalesGroup": "REdwards", "OrderStatus": "Open order", "OrderDate": "2026-04-01",
         "LineNumber": "1", "Item": "ITM-Z", "ItemDescription": "Zed", "SalesPrice": "1.00",
         "SalesStatus": "Open", "QuantityOrdered": "9", "ReleasedQuantity": "0",
         "DeliveryRemainder": "9", "QuantityLefttoLoad": "0", "Ordered $": "9.00",
         "Shipped $": "0", "Cancelled $": "0"},
    ]


def _facts():
    return S.to_facts(_rows())


def test_invoiced_orders_excludes_open_and_sorts_newest_first():
    orders = B.invoiced_orders(_facts())
    assert [o.order_number for o in orders] == ["SO3", "SO2"]  # newest first, SO9 excluded


def test_defaults_to_latest_invoiced_order():
    view = B.build(_facts())
    assert view.selected_orders == ["SO3"]
    assert view.primary.order_number == "SO3"
    assert len(view.lines) == 1 and view.lines[0].item == "ITM-A"
    assert view.lines[0].qty_shipped == 10
    assert view.lines[0].total == 20.0  # 2.00 * 10 shipped
    assert view.totals["total"] == 20.0


def test_merge_rolls_up_same_item_price_across_orders():
    view = B.build(_facts(), requested_orders=["SO3", "SO2"])
    assert len(view.headers) == 2
    # ITM-A @2.00 appears in both orders -> merged into one row (10 + 5).
    a = next(l for l in view.lines if l.item == "ITM-A")
    assert a.qty_shipped == 15 and a.total == 30.0
    assert set(a.from_orders) == {"SO3", "SO2"}
    b = next(l for l in view.lines if l.item == "ITM-B")
    assert b.qty_shipped == 3 and b.total == 15.0
    assert view.totals["qty_shipped"] == 18 and view.totals["total"] == 45.0


def test_display_po_uses_common_prefix():
    view = B.build(_facts(), requested_orders=["SO3", "SO2"])
    # PO-555 + PO-555-addon -> shared prefix "PO-555" (trailing dash stripped).
    assert view.display_po == "PO-555"


def test_unknown_requested_order_falls_back_to_latest():
    view = B.build(_facts(), requested_orders=["NOPE"])
    assert view.selected_orders == ["SO3"]


def test_no_invoiced_orders_yields_empty_view():
    open_only = [r for r in _rows() if r["SalesOrderNumber"] == "SO9"]
    view = B.build(S.to_facts(open_only))
    assert view.headers == [] and view.lines == [] and view.primary is None
    assert view.totals["total"] == 0
