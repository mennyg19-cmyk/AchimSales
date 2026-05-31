"""Number 4 report: invoice_lines adapter + 4-tab builder + Book Price join."""

from datetime import date

from report_engine.facts import SalesmanFact
from report_engine.lib import salesman_key
from report_engine.reports import number_4 as B
from report_engine.sources import invoice_lines as S
from report_engine.sources import released_products as RP

TODAY = date(2026, 3, 15)


def _salesmen():
    return {salesman_key("REdwards"): SalesmanFact(
        source="reporting_api", key="redwards", number="10",
        full_name="Robert Edwards", display_name="Bob", commission_pct=0.0)}


def _rows():
    return [
        {"Invoice": "I1", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-03-01", "Item": "ITM-A", "ItemName": "Widget",
         "InventQTY": "10", "Amount": "100", "SalesGroup": "REdwards", "SalesOrder": "SO1"},
        {"Invoice": "I2", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-02-01", "Item": "ITM-A", "ItemName": "Widget",
         "InventQTY": "5", "Amount": "60", "SalesGroup": "REdwards", "SalesOrder": "SO2"},
        # outside the 12-month / ytd windows (Mar 2024)
        {"Invoice": "I3", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2024-03-01", "Item": "ITM-A", "ItemName": "Widget",
         "InventQTY": "99", "Amount": "999", "SalesGroup": "REdwards", "SalesOrder": "SO3"},
    ]


def test_free_text_lines_without_sales_order_are_excluded():
    rows = [{"Invoice": "I1", "InvoiceAccount": "100", "InvoiceDate": "2026-03-01",
             "Item": "ITM-A", "ItemName": "W", "InventQTY": "1", "Amount": "9",
             "SalesGroup": "REdwards"}]  # no SalesOrder -> free text
    tabs = B.build(S.to_facts(rows), today=TODAY, salesmen=_salesmen())
    assert all(t["rows"] == [] for t in tabs)


def test_adapter_maps_line_fields():
    f = S.to_fact(_rows()[0])
    assert f.invoice_number == "I1"
    assert f.invoice_date == "2026-03-01"
    assert f.item_number == "ITM-A"
    assert f.qty == 10.0 and f.amount == 100.0


def test_four_tabs_in_live_order():
    tabs = B.build(S.to_facts(_rows()), today=TODAY, salesmen=_salesmen())
    assert [t["key"] for t in tabs] == [
        "by_item_12mo", "by_item_ytd", "by_customer_12mo", "by_customer_ytd"]


def test_book_price_is_last_column_and_blank_without_map():
    tabs = B.build(S.to_facts(_rows()), today=TODAY, salesmen=_salesmen())
    for t in tabs:
        assert t["columns"][-1]["header"] == "Book Price"
        assert all(r["BookPrice"] is None for r in t["rows"])


def test_book_price_joins_case_insensitive():
    # invoice item is lowercase; released-products map is uppercase -> still joins
    rows = [{"Invoice": "I9", "InvoiceAccount": "100", "CustomerName": "Acme",
             "InvoiceDate": "2026-03-01", "Item": "itm-a", "ItemName": "Widget",
             "InventQTY": "1", "Amount": "9", "SalesGroup": "REdwards", "SalesOrder": "SO9"}]
    book = RP.to_book_price_map([{"ItemNumber": "ITM-A", "SalesPrice": "2.50"}])
    tabs = B.build(S.to_facts(rows), today=TODAY, salesmen=_salesmen(), book_prices=book)
    by_item = next(t for t in tabs if t["key"] == "by_item_12mo")
    assert len(by_item["rows"]) == 1
    assert by_item["rows"][0]["BookPrice"] == 2.50


def test_ytd_excludes_prior_year_and_totals_qty():
    tabs = B.build(S.to_facts(_rows()), today=TODAY, salesmen=_salesmen())
    by_item_ytd = next(t for t in tabs if t["key"] == "by_item_ytd")
    r = by_item_ytd["rows"][0]
    # YTD 2026 = Jan-Mar -> Feb(5) + Mar(10) = 15 ; 2024 row excluded
    assert r["Total_Qty"] == 15.0
    assert r["Total_$"] == 160.0
    assert r["Salesman"] == "Bob"


def test_twelve_month_window_includes_trailing_year():
    tabs = B.build(S.to_facts(_rows()), today=TODAY, salesmen=_salesmen())
    by_item_12 = next(t for t in tabs if t["key"] == "by_item_12mo")
    r = by_item_12["rows"][0]
    # rolling 12 mo ending Mar 2026 includes Feb+Mar 2026 but not Mar 2024
    assert r["Total_Qty"] == 15.0
    assert r["Avg_Price"] == round(160.0 / 15.0, 4)


def test_lines_without_date_or_item_dropped():
    rows = [{"Invoice": "X", "InvoiceAccount": "1", "Amount": "5", "InventQTY": "1",
             "Item": "A"},  # no date
            {"Invoice": "Y", "InvoiceAccount": "1", "InvoiceDate": "2026-03-01",
             "Amount": "5", "InventQTY": "1"}]  # no item
    tabs = B.build(S.to_facts(rows), today=TODAY)
    assert all(t["rows"] == [] for t in tabs)
