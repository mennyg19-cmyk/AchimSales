"""
Tests for the Salesman Report builder.

Uses canonical invoice detail (same shape as ``fetch_invoice_detail`` output)
to verify year-over-year comparisons, monthly tabs, and edge cases.
"""

import os
from datetime import date, datetime
from unittest.mock import patch

import pandas as pd
import pytest

from reports.salesman.builder import build_salesman_full_year_data
from tests.fixtures.sample_invoices import make_invoice_detail


def _detail_with_dates(rows):
    """Build a minimal invoice detail DataFrame from a list of dicts."""
    df = pd.DataFrame(rows)
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    for col in ["SubTotal Invoices", "Tariff Charges", "Freight Charges",
                 "CC Charges", "Total Invoice"]:
        if col not in df.columns:
            df[col] = 0.0
    for col in ["CustomerAccount", "CustomerName", "SalesmanNumber", "Salesman",
                 "InvoiceNumber", "SalesOrderNumber", "SalesmanName"]:
        if col not in df.columns:
            df[col] = ""
    return df


class TestBuildSalesmanFullYear:

    def test_yoy_comparison(self):
        """Both current and prior year data should be populated."""
        detail = _detail_with_dates([
            {"InvoiceDate": "2025-03-10", "CustomerAccount": "C100", "CustomerName": "Test",
             "SalesmanNumber": "01", "Salesman": "SM01", "Total Invoice": 1000,
             "CC Charges": 10, "Freight Charges": 5},
            {"InvoiceDate": "2024-03-10", "CustomerAccount": "C100", "CustomerName": "Test",
             "SalesmanNumber": "01", "Salesman": "SM01", "Total Invoice": 800,
             "CC Charges": 8, "Freight Charges": 4},
        ])
        result = build_salesman_full_year_data(detail, 2025)

        assert 3 in result  # March
        march = result[3]
        assert not march.empty
        assert march["Sales_Current"].iloc[0] == pytest.approx(1000 - 10 - 5)
        assert march["Sales_Prior"].iloc[0] == pytest.approx(800 - 8 - 4)

    def test_no_prior_year(self):
        """Only current year data → prior = 0, diff% = 0."""
        detail = _detail_with_dates([
            {"InvoiceDate": "2026-06-15", "CustomerAccount": "C100", "CustomerName": "Test",
             "SalesmanNumber": "01", "Salesman": "SM01", "Total Invoice": 500,
             "CC Charges": 5, "Freight Charges": 3},
        ])
        result = build_salesman_full_year_data(detail, 2026)

        june = result[6]
        assert june["Sales_Prior"].iloc[0] == pytest.approx(0.0)
        assert june["% Month Diff"].iloc[0] == pytest.approx(0.0)

    def test_12_monthly_tabs(self):
        """Full year of data produces 12 months."""
        rows = []
        for m in range(1, 13):
            rows.append({
                "InvoiceDate": f"2026-{m:02d}-15",
                "CustomerAccount": "C100", "CustomerName": "Test",
                "SalesmanNumber": "01", "Salesman": "SM01",
                "Total Invoice": 100, "CC Charges": 1, "Freight Charges": 1,
            })
        detail = _detail_with_dates(rows)
        result = build_salesman_full_year_data(detail, 2026)

        assert len(result) == 12
        for m in range(1, 13):
            assert m in result

    def test_sales_excludes_tariff(self):
        """Sales = Total Invoice - CC - Freight (tariff NOT subtracted)."""
        detail = _detail_with_dates([
            {"InvoiceDate": "2026-01-15", "CustomerAccount": "C100", "CustomerName": "Test",
             "SalesmanNumber": "01", "Salesman": "SM01",
             "Total Invoice": 200, "CC Charges": 10, "Freight Charges": 5,
             "Tariff Charges": 20},
        ])
        result = build_salesman_full_year_data(detail, 2026)
        jan = result[1]
        # Sales = 200 - 10 - 5 = 185 (tariff 20 is NOT subtracted)
        assert jan["Sales_Current"].iloc[0] == pytest.approx(185.0)

    def test_empty_detail(self):
        """Empty detail → empty dict."""
        result = build_salesman_full_year_data(pd.DataFrame(), 2026)
        assert result == {}

    def test_customer_appears_both_years(self):
        """A customer active in prior year but not current still appears with 0."""
        detail = _detail_with_dates([
            {"InvoiceDate": "2024-05-15", "CustomerAccount": "C100", "CustomerName": "Test",
             "SalesmanNumber": "01", "Salesman": "SM01",
             "Total Invoice": 300, "CC Charges": 3, "Freight Charges": 2},
        ])
        result = build_salesman_full_year_data(detail, 2025)
        may = result[5]
        assert not may.empty
        assert may["Sales_Current"].iloc[0] == pytest.approx(0.0)
        assert may["Sales_Prior"].iloc[0] == pytest.approx(300 - 3 - 2)

    def test_diff_percentage_prior_zero(self):
        """When prior year is 0, % diff should be 0 (not inf)."""
        detail = _detail_with_dates([
            {"InvoiceDate": "2026-04-10", "CustomerAccount": "C100", "CustomerName": "Test",
             "SalesmanNumber": "01", "Salesman": "SM01",
             "Total Invoice": 500, "CC Charges": 5, "Freight Charges": 5},
        ])
        result = build_salesman_full_year_data(detail, 2026)
        april = result[4]
        assert april["% Month Diff"].iloc[0] == pytest.approx(0.0)

    def test_missing_invoice_date(self):
        """Rows with unparseable InvoiceDate are dropped, not crash."""
        detail = _detail_with_dates([
            {"InvoiceDate": "2026-03-15", "CustomerAccount": "C100", "CustomerName": "Test",
             "SalesmanNumber": "01", "Salesman": "SM01",
             "Total Invoice": 100, "CC Charges": 1, "Freight Charges": 1},
        ])
        detail.loc[len(detail)] = detail.iloc[0].copy()
        detail.loc[len(detail) - 1, "InvoiceDate"] = pd.NaT

        result = build_salesman_full_year_data(detail, 2026)
        assert 3 in result
