"""Sales by State: column shape, date coercion, SQL-only registry."""

from report_engine.registry import ReportStatus, get
from report_engine.reports import sales_by_state as rpt
from web.beta_sources import _ALL_KEYS, default_sources, get_source


def test_summary_sorts_by_amount_and_keeps_blank_nyc():
    tabs = rpt.build(
        summary=[
            {"State": "New York", "SalesAmount": 100},
            {"State": "New Jersey", "Sales amount": 200,
             "New York City Sales amount": 50},
        ],
        nyc=[],
        detail=[],
    )
    summary = tabs[0]
    assert [t["name"] for t in tabs] == ["Summary", "New York City", "Detail"]
    assert [r["State"] for r in summary["rows"]] == ["New Jersey", "New York"]
    assert summary["rows"][0]["New York City Sales amount"] == 50.0
    assert summary["rows"][1]["New York City Sales amount"] == ""


def test_summary_shows_nyc_amount_on_first_row_only():
    tabs = rpt.build(
        summary=[
            {"State": "New York", "SalesAmount": 100,
             "NewYorkCitySalesAmount": 50},
            {"State": "New Jersey", "Sales amount": 200,
             "New York City Sales amount": 50},
        ],
        nyc=[],
        detail=[],
    )
    amounts = [r["New York City Sales amount"] for r in tabs[0]["rows"]]
    assert amounts == [50.0, ""]


def test_detail_coerces_excel_serial_date_and_aliases():
    tabs = rpt.build(
        summary=[],
        nyc=[{"Invoice": "INV1", "Amount": "10.5", "CustomerName": "Acme",
              "StateCode": "NY", "State": "New York", "PostalCode": "10001"}],
        detail=[{"InvoiceNumber": "INV1", "InvoiceDate": 45663,
                 "CustomerAccount": "100", "CustomerName": "Acme",
                 "Amount": -5, "State Code": "AL", "State": "Alabama"}],
    )
    assert tabs[1]["rows"][0]["Invoice"] == "INV1"
    assert tabs[1]["rows"][0]["Amount"] == 10.5
    assert tabs[1]["rows"][0]["Customer_Name"] == "Acme"
    assert tabs[2]["rows"][0]["Invoice Date"] == "2025-01-06"
    assert tabs[2]["rows"][0]["Amount"] == -5.0
    assert tabs[2]["rows"][0]["Customer Account"] == "100"


def test_registry_sql_only_not_a_salesman_default():
    spec = get("sales_by_state")
    assert spec is not None
    assert spec.status is ReportStatus.BUILT
    assert spec.salesman_default is False
    assert spec.privileged_only is False
    assert "sales_by_state" not in _ALL_KEYS
    assert "sales_by_state" not in default_sources()
    assert get_source("sales_by_state") == "sql"
