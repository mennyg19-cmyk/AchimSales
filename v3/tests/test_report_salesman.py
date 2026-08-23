"""Salesman report: monthly_salesman_yoy SP rows -> 12 month tabs."""

from report_engine.reports import salesman as B


def _row(**overrides):
    base = {
        "SalesmanId": "10",
        "SalesmanName": "Robert Edwards",
        "CustomerAccount": "100",
        "CustomerName": "Acme",
        "Jan This Year": 0, "Jan Last Year": 0,
        "Feb This Year": 200, "Feb Last Year": 0,
        "Mar This Year": 1000, "Mar Last Year": 500,
        "Apr This Year": 0, "Apr Last Year": 0,
        "May This Year": 0, "May Last Year": 0,
        "Jun This Year": 0, "Jun Last Year": 0,
        "Jul This Year": 0, "Jul Last Year": 0,
        "Aug This Year": 0, "Aug Last Year": 0,
        "Sep This Year": 0, "Sep Last Year": 0,
        "Oct This Year": 0, "Oct Last Year": 0,
        "Nov This Year": 0, "Nov Last Year": 0,
        "Dec This Year": 0, "Dec Last Year": 0,
        "Full Year This Year": 1200,
        "Full Year Last Year": 500,
    }
    base.update(overrides)
    return base


def test_build_returns_twelve_month_tabs():
    tabs = B.build(B.clean_rows([_row()]), year=2026)
    assert len(tabs) == 12
    assert [t["name"] for t in tabs] == ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def test_march_tab_uses_total_invoice_month_and_ytd():
    """Sales basis is Total Invoice from the SP — no CC/freight strip here."""
    tabs = B.build(B.clean_rows([_row()]), year=2026)
    march = next(t for t in tabs if t["name"] == "Mar")
    assert len(march["rows"]) == 1
    r = march["rows"][0]
    assert r["Sales March 2026"] == 1000.0
    assert r["Sales March 2025"] == 500.0
    assert r["$ This Year to Last Year"] == 500.0
    assert round(r["% This Year to Last Year"], 4) == 1.0
    assert r["Sales 2026 Jan Thru March"] == 1200.0  # Feb 200 + Mar 1000
    assert r["Sales 2025 Jan Thru March"] == 500.0
    assert r["$ This Year to Last Year (YTD)"] == 700.0
    assert r["Sales Year to Date 2026"] == 1200.0
    assert r["Sales Year to Date 2025"] == 500.0
    assert r["SalesmanNumber"] == "10"
    assert r["Sort Number"] == "0010"
    assert r["Cust. #"] == "100"


def test_pct_is_zero_when_no_prior_sales():
    rows = B.clean_rows([_row(**{
        "Feb This Year": 0, "Mar This Year": 0, "Mar Last Year": 0,
        "May This Year": 100, "May Last Year": 0,
        "Full Year This Year": 100, "Full Year Last Year": 0,
    })])
    may = next(t for t in B.build(rows, year=2026) if t["name"] == "May")
    assert may["rows"][0]["% This Year to Last Year"] == 0.0


def test_filter_rows_by_salesman_name():
    rows = B.clean_rows([
        _row(SalesmanName="Robert Edwards"),
        _row(SalesmanName="Other Rep", CustomerAccount="200"),
    ])
    mine = B.filter_rows_by_salesman(rows, {"robertedwards"})
    assert len(mine) == 1
    assert mine[0]["CustomerAccount"] == "100"
    assert B.filter_rows_by_salesman(rows, None) == rows
    assert B.filter_rows_by_salesman(rows, set()) == []


def test_column_aliases_are_flexible():
    row = {
        "SalesmanId": "42",
        "SalesmanName": "Rep",
        "CustomerAccount": "9",
        "CustomerName": "Zed",
        "MarThisYear": 10,
        "MarLastYear": 5,
        "FullYearThisYear": 10,
        "FullYearLastYear": 5,
    }
    march = next(t for t in B.build(B.clean_rows([row]), year=2026) if t["name"] == "Mar")
    assert march["rows"][0]["Sales March 2026"] == 10.0
    assert march["rows"][0]["Sales March 2025"] == 5.0
