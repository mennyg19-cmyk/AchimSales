"""Ordered report: usp_ordered_report SP adapter + builder (SP qty columns)."""

from report_engine.reports import ordered as B
from report_engine.sources import ordered as S


def _rows():
    return [
        {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "customername": "Acme",
         "SalesGroup": "REdwards", "CreatedDateTime": "2026-03-01T08:30:00",
         "CustomerRequisition": "PO-1001", "purchid": "PO-7788",
         "ExpectedArrivalDate": "2026-03-15T00:00:00",
         "LineNumber": "1", "Item": "ITM-A", "ItemDescription": "Widget",
         "SalesPrice": "2.29", "SalesStatus": "Open", "QuantityOrdered": "30",
         "QuantityReserved": "5", "CancelledQTY": "0", "ReleasedQuantity": "10",
         "DeliveryRemainder": "20",
         "Ordered $": "68.70", "Shipped $": "22.90", "Cancelled $": "0",
         "Commission": "0.06", "SalesmanName": "Ron Edwards"},
        {"SalesOrderNumber": "SO2", "CustomerAccount": "100", "customername": "Acme",
         "SalesGroup": "REdwards", "CreatedDateTime": "2026-03-02T08:30:00",
         "CustomerRequisition": "PO-1002", "purchid": "",
         "ExpectedArrivalDate": "",
         "LineNumber": "1", "Item": "ITM-B", "ItemDescription": "Gadget",
         "SalesPrice": "5.00", "SalesStatus": "Cancelled", "QuantityOrdered": "4",
         "QuantityReserved": "0", "CancelledQTY": "4", "ReleasedQuantity": "0",
         "DeliveryRemainder": "0",
         "Ordered $": "20.00", "Shipped $": "0", "Cancelled $": "20.00",
         "Commission": "0.05", "SalesmanName": "Ron Edwards"},
    ]


def test_adapter_maps_sp_qty_columns_without_deriving_shipped():
    f = S.to_fact_ordered_report(_rows()[0])
    assert f.sales_order_number == "SO1"
    assert f.customer_name == "Acme"
    assert f.sales_order_name == "Acme"
    assert f.order_date == "2026-03-01"
    assert f.qty_ordered == 30 and f.qty_cancelled == 0
    assert f.qty_reserved == 5
    assert f.qty_released == 10
    assert f.delivery_remainder == 20
    assert f.qty_shipped == 0  # SP has no shipped qty; do not invent one
    assert f.ordered_dollars == 68.70 and f.shipped_dollars == 22.90
    assert f.po_number == "PO-1001" and f.order_status == ""
    assert f.purch_id == "PO-7788"
    assert f.expected_arrival_date == "2026-03-15"


def test_full_data_uses_sp_qty_columns():
    tabs = B.build(S.to_facts_ordered_report(_rows()))
    full = next(t for t in tabs if t["key"] == "full_data")
    so1 = next(r for r in full["rows"] if r["SalesOrderNumber"] == "SO1")
    assert so1["QtyOrdered"] == 30
    assert so1["QtyReserved"] == 5
    assert so1["QtyReleased"] == 10
    assert so1["QtyCancelled"] == 0
    assert so1["QtyLeftToShip"] == 20
    assert "QtyShipped" not in so1
    assert "QtyOpen" not in so1
    assert so1["Fulfillment %"] == 1.0
    ff = next(c for c in full["columns"] if c["field"] == "Fulfillment %")
    assert ff["type"] == "percent"
    rel_col = next(c for c in full["columns"] if c["field"] == "QtyReleased")
    assert rel_col["header"] == "QTY Shipping"
    assert not any(c["field"] == "QtyShipped" for c in full["columns"])
    assert not any(c["field"] == "Shipped $" for c in full["columns"])
    ship_col = next(c for c in full["columns"] if c["field"] == "Released $")
    assert ship_col["header"] == "Shipping $"
    assert so1["Open $"] == 45.80  # 68.70 - 22.90 - 0
    assert so1["Released $"] == 22.90  # 10 * 2.29
    assert so1["purchid"] == "PO-7788"
    assert so1["ExpectedArrivalDate"] == "2026-03-15"
    assert any(c["field"] == "purchid" for c in full["columns"])
    assert any(c["field"] == "ExpectedArrivalDate" for c in full["columns"])

    so2 = next(r for r in full["rows"] if r["SalesOrderNumber"] == "SO2")
    assert so2["QtyCancelled"] == 4
    assert so2["QtyLeftToShip"] == 0
    assert so2["Fulfillment %"] == 0.0
    assert so2["purchid"] == ""
    assert so2["ExpectedArrivalDate"] == ""


def test_stub_fields_only_missing_sp_columns():
    tabs = B.build(S.to_facts_ordered_report(_rows()))
    full = next(t for t in tabs if t["key"] == "full_data")
    assert "PO #" not in full["stub_fields"]
    assert "OrderStatus" in full["stub_fields"]
    assert "QtyShipped" not in full["stub_fields"]
    assert "QtyOpen" not in full["stub_fields"]


def test_error_item_lines_dropped_by_item_number_only():
    rows = _rows() + [
        {"SalesOrderNumber": "SO9", "CustomerAccount": "100", "Item": "ERROR ITEM",
         "ItemDescription": "x", "QuantityOrdered": "5", "Ordered $": "999",
         "SalesStatus": "Open"},
        {"SalesOrderNumber": "SO8", "CustomerAccount": "100", "Item": "REAL-1",
         "ItemDescription": "ERROR ITEM in name", "QuantityOrdered": "5",
         "Ordered $": "10", "SalesStatus": "Open"}]
    full = next(t for t in B.build(S.to_facts_ordered_report(rows)) if t["key"] == "full_data")
    sos = {r["SalesOrderNumber"] for r in full["rows"]}
    assert "SO9" not in sos
    assert "SO8" in sos


def test_by_customer_aggregates_dollars_and_qtys():
    by_cust = next(t for t in B.build(S.to_facts_ordered_report(_rows())) if t["key"] == "by_customer")
    assert len(by_cust["rows"]) == 1
    r = by_cust["rows"][0]
    assert r["Ordered $"] == 88.70
    assert r["QtyOrdered"] == 34
    assert r["QtyCancelled"] == 4
    assert r["QtyReserved"] == 5
    assert r["QtyLeftToShip"] == 20


def test_summary_uses_sp_left_to_ship():
    summary = next(t for t in B.build(S.to_facts_ordered_report(_rows())) if t["key"] == "summary")
    a = next(r for r in summary["rows"] if r["Item Number"] == "ITM-A")
    assert a["Net Price"] == 2.29
    assert a["QtyLeftToShip"] == 20
    assert a["QtyReserved"] == 5
    # Extended remainder from SP dollars: 68.70 - 22.90 - 0
    assert a["Extended Price Remainder"] == 45.80
    assert a["purchid"] == "PO-7788"
    assert a["ExpectedArrivalDate"] == "2026-03-15"

    b = next(r for r in summary["rows"] if r["Item Number"] == "ITM-B")
    assert b["QtyLeftToShip"] == 0
    assert b["Extended Price Remainder"] == 0.0
    assert b["purchid"] == ""
    assert b["ExpectedArrivalDate"] == ""


def test_by_item_includes_purchid_and_arrival():
    by_item = next(t for t in B.build(S.to_facts_ordered_report(_rows())) if t["key"] == "by_item")
    assert any(c["field"] == "purchid" for c in by_item["columns"])
    assert any(c["field"] == "ExpectedArrivalDate" for c in by_item["columns"])
    a = next(r for r in by_item["rows"] if r["Item#"] == "ITM-A")
    assert a["purchid"] == "PO-7788"
    assert a["ExpectedArrivalDate"] == "2026-03-15"


def test_tab_order_matches_live():
    keys = [t["key"] for t in B.build(S.to_facts_ordered_report(_rows()))]
    assert keys == ["summary", "by_customer", "by_item", "by_order",
                    "by_salesman", "full_data"]


def test_salesman_variant_drops_by_salesman_tab():
    keys = [t["key"] for t in B.build(S.to_facts_ordered_report(_rows()), skip_by_salesman=True)]
    assert keys == ["summary", "by_customer", "by_item", "by_order", "full_data"]


def test_salesman_variant_does_not_group_by_salesman():
    tabs = B.build(S.to_facts_ordered_report(_rows()), skip_by_salesman=True)
    for t in tabs:
        assert not t.get("default_group")


def test_full_data_preserves_source_row_order():
    rows = _rows() * 3
    full = next(t for t in B.build(S.to_facts_ordered_report(rows)) if t["key"] == "full_data")
    assert [r["SalesOrderNumber"] for r in full["rows"]] == \
        ["SO1", "SO2", "SO1", "SO2", "SO1", "SO2"]


def test_build_consumes_facts_list_to_save_memory():
    facts = S.to_facts_ordered_report(_rows())
    B.build(facts)
    assert facts == [None, None]


def test_po_maps_from_customer_requisition_in_by_order():
    by_order = next(t for t in B.build(S.to_facts_ordered_report(_rows())) if t["key"] == "by_order")
    so1 = next(r for r in by_order["rows"] if r["SalesOrderNumber"] == "SO1")
    assert so1["PO #"] == "PO-1001"
    assert so1["OrderStatus"] == ""
    so2 = next(r for r in by_order["rows"] if r["SalesOrderNumber"] == "SO2")
    assert so2["PO #"] == "PO-1002"
