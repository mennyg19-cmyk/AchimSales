"""Salesman report: 12 month tabs, current-vs-prior-year math (LIVE parity)."""

from report_engine.facts import SalesmanFact
from report_engine.lib import salesman_key
from report_engine.reports import salesman as B
from report_engine.sources import invoiced as S


def _salesmen():
    return {salesman_key("REdwards"): SalesmanFact(
        source="reporting_api", key="redwards", number="10",
        full_name="Robert Edwards", display_name="", commission_pct=0.05)}


def _facts():
    return S.to_facts([
        # current year
        {"Invoice": "I1", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-03-10", "Amount": "1000", "SL_TariffCharges": "100",
         "SH_FreightCharges": "50", "SH_ProcessingFeesCharges": "25", "SalesGroup": "REdwards"},
        {"Invoice": "I2", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-02-05", "Amount": "200", "SalesGroup": "REdwards"},
        # prior year
        {"Invoice": "I3", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2025-03-20", "Amount": "500", "SalesGroup": "REdwards"},
    ])


def test_build_returns_twelve_month_tabs():
    tabs = B.build(_facts(), salesmen=_salesmen(), year=2026)
    assert len(tabs) == 12
    assert [t["name"] for t in tabs] == ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def test_march_tab_comparison_math():
    tabs = B.build(_facts(), salesmen=_salesmen(), year=2026)
    march = next(t for t in tabs if t["name"] == "Mar")
    assert len(march["rows"]) == 1
    r = march["rows"][0]
    # Sales = Total Invoice - CC - Freight  => I1 = 1175 - 25 - 50 = 1100
    assert r["Sales March 2026"] == 1100.0
    assert r["Sales March 2025"] == 500.0
    assert r["$ This Year to Last Year"] == 600.0
    assert round(r["% This Year to Last Year"], 4) == 1.2
    assert r["Sales 2026 Jan Thru March"] == 1300.0   # Feb 200 + Mar 1100
    assert r["Sales 2025 Jan Thru March"] == 500.0
    assert r["$ This Year to Last Year (YTD)"] == 800.0
    assert r["Sales Year to Date 2026"] == 1300.0
    assert r["Sales Year to Date 2025"] == 500.0
    assert r["$ This Year to Last Year (YTD Full Year)"] == 800.0
    assert r["SalesmanNumber"] == "10"
    assert r["Sort Number"] == "0010"
    assert r["Cust. #"] == "100"


def test_pct_is_zero_when_no_prior_sales():
    facts = S.to_facts([{"Invoice": "X", "InvoiceAccount": "1", "InvoiceDate": "2026-05-01",
                         "Amount": "100", "SalesGroup": "REdwards"}])
    may = next(t for t in B.build(facts, salesmen=_salesmen(), year=2026) if t["name"] == "May")
    r = may["rows"][0]
    assert r["% This Year to Last Year"] == 0.0


def test_rows_missing_dates_are_dropped():
    facts = S.to_facts([{"Invoice": "X", "InvoiceAccount": "1", "Amount": "100",
                         "SalesGroup": "REdwards"}])  # no InvoiceDate
    tabs = B.build(facts, salesmen=_salesmen(), year=2026)
    assert all(t["rows"] == [] for t in tabs)
