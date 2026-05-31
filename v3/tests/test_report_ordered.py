"""Ordered report: SP adapter + LIVE-format builder (authoritative $, stub qty)."""

from report_engine.reports import ordered as B
from report_engine.sources import ordered as S


def _rows():
    return [
        {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "customername": "Acme",
         "SalesGroup": "REdwards", "CreatedDateTime": "2026-03-01T08:30:00",
         "CustomerRequisition": "PO-1", "LineNumber": "1", "Item": "ITM-A",
         "ItemDescription": "Widget", "SalesPrice": "2.29", "SalesStatus": "Open",
         "QuantityOrdered": "30", "ReleasedQuantity": "10", "DeliveryRemainder": "20",
         "QuantityLefttoLoad": "0", "Ordered $": "68.70", "Shipped $": "22.90",
         "Cancelled $": "0"},
        {"SalesOrderNumber": "SO2", "CustomerAccount": "100", "customername": "Acme",
         "SalesGroup": "REdwards", "CreatedDateTime": "2026-03-02T08:30:00",
         "LineNumber": "1", "Item": "ITM-B", "ItemDescription": "Gadget",
         "SalesPrice": "5.00", "SalesStatus": "Cancelled", "QuantityOrdered": "4",
         "ReleasedQuantity": "0", "DeliveryRemainder": "0", "QuantityLefttoLoad": "0",
         "Ordered $": "20.00", "Shipped $": "0", "Cancelled $": "20.00"},
    ]


def test_adapter_maps_authoritative_dollars_and_qty():
    f = S.to_fact(_rows()[0])
    assert f.sales_order_number == "SO1"
    assert f.customer_name == "Acme"
    assert f.order_date == "2026-03-01"
    assert f.qty_ordered == 30 and f.qty_released == 10
    assert f.ordered_dollars == 68.70 and f.shipped_dollars == 22.90
    assert f.unit_price == 2.29


def test_full_data_qty_derivation_and_open_dollars():
    tabs = B.build(S.to_facts(_rows()))
    full = next(t for t in tabs if t["key"] == "full_data")
    so1 = next(r for r in full["rows"] if r["SalesOrderNumber"] == "SO1")
    # shipped = 30 - 20 remainder - 0 load - 0 cancelled = 10
    assert so1["QtyShipped"] == 10
    assert so1["QtyCancelled"] == 0
    assert so1["QtyOpen"] == 20
    # Open $ derived from authoritative dollars: 68.70 - 22.90 - 0 = 45.80
    assert so1["Open $"] == 45.80
    assert so1["Released $"] == 22.90  # 10 * 2.29

    so2 = next(r for r in full["rows"] if r["SalesOrderNumber"] == "SO2")
    assert so2["QtyCancelled"] == 4          # cancelled status -> all ordered
    assert so2["Fulfillment %"] == 0.0       # (4-4)/4


def test_stub_fields_flagged_on_every_tab():
    tabs = B.build(S.to_facts(_rows()))
    for t in tabs:
        assert "stub_fields" in t and t["stub_fields"]
    full = next(t for t in tabs if t["key"] == "full_data")
    assert "QtyCancelled" in full["stub_fields"]


def test_error_item_lines_dropped():
    rows = _rows() + [{
        "SalesOrderNumber": "SO9", "CustomerAccount": "100", "Item": "ERR",
        "ItemDescription": "ERROR ITEM - unmatched", "QuantityOrdered": "5",
        "Ordered $": "999", "SalesStatus": "Open"}]
    full = next(t for t in B.build(S.to_facts(rows)) if t["key"] == "full_data")
    assert all(r["SalesOrderNumber"] != "SO9" for r in full["rows"])


def test_by_customer_aggregates_dollars():
    by_cust = next(t for t in B.build(S.to_facts(_rows())) if t["key"] == "by_customer")
    assert len(by_cust["rows"]) == 1
    r = by_cust["rows"][0]
    assert r["Ordered $"] == 88.70          # 68.70 + 20.00
    assert r["QtyOrdered"] == 34
    assert r["QtyCancelled"] == 4


def test_summary_net_price_and_remainder():
    summary = next(t for t in B.build(S.to_facts(_rows())) if t["key"] == "summary")
    assert summary["default_layout"]["group_levels"] == ["Customer Name"]
    a = next(r for r in summary["rows"] if r["Item Number"] == "ITM-A")
    assert a["Net Price"] == 2.29           # 68.70 / 30
    assert a["QtyRemainder"] == 20          # open qty
    assert a["Extended Price Remainder"] == 45.80


def test_tab_order_matches_live():
    keys = [t["key"] for t in B.build(S.to_facts(_rows()))]
    assert keys == ["summary", "by_customer", "by_item", "by_order",
                    "by_salesman", "full_data"]
