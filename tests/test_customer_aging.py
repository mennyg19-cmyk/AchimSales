"""
Tests for the Customer Aging Report builder and loader.
"""

import os
from datetime import date

import pandas as pd
import pytest

from reports.customer_aging.builder import (
    REPORT_COLUMNS,
    build_master_sheets,
    build_salesman_sheet,
)
from tests.fixtures.sample_customers import make_aged_balances


def _aging_with_salesman(n=5, salesmen=None):
    """Create aged balances with a Salesman column already assigned."""
    df = make_aged_balances(n=n)
    if salesmen is None:
        salesmen = [f"Salesman {i % 2}" for i in range(n)]
    if len(salesmen) < n:
        salesmen = (salesmen * ((n // len(salesmen)) + 1))[:n]
    df["Salesman"] = salesmen[:n]
    return df


class TestBuildMasterSheets:

    def test_normal_aging(self):
        """5 customers, 2 salesmen → All Customers + 2 salesman sheets."""
        df = _aging_with_salesman(n=5, salesmen=["Alice", "Bob", "Alice", "Bob", "Alice"])
        sheets = build_master_sheets(df)

        assert "All Customers" in sheets
        assert len(sheets["All Customers"]) == 5
        assert "Alice" in sheets
        assert "Bob" in sheets
        assert len(sheets["Alice"]) == 3
        assert len(sheets["Bob"]) == 2

    def test_sentinel_date_cleared(self):
        """1900-01-01 LastPaymentDate is treated as NaT by the loader;
        builder should handle NaT gracefully."""
        df = _aging_with_salesman(n=2)
        df["LastPaymentDate"] = pd.NaT
        sheets = build_master_sheets(df)
        assert "All Customers" in sheets
        assert pd.isna(sheets["All Customers"]["LastPaymentDate"]).all()

    def test_zero_balance_buckets(self):
        """All zero buckets still produce valid sheets."""
        df = _aging_with_salesman(n=3)
        for col in ["Current", "30", "60", "90", "91+"]:
            df[col] = 0.0
        df["AmountDue"] = 0.0

        sheets = build_master_sheets(df)
        assert "All Customers" in sheets
        assert len(sheets["All Customers"]) == 3

    def test_empty_balances(self):
        """Empty DataFrame → empty sheets dict (should not crash)."""
        df = pd.DataFrame(columns=REPORT_COLUMNS)
        sheets = build_master_sheets(df)
        assert "All Customers" in sheets
        assert sheets["All Customers"].empty

    def test_single_salesman(self):
        """All customers same salesman → All Customers + 1 salesman sheet."""
        df = _aging_with_salesman(n=4, salesmen=["Alice"] * 4)
        sheets = build_master_sheets(df)
        assert len(sheets) == 2
        assert "Alice" in sheets
        assert len(sheets["Alice"]) == 4


class TestBuildSalesmanSheet:

    def test_filter_by_salesman(self):
        """Only the specified salesman's customers are returned."""
        df = _aging_with_salesman(n=5, salesmen=["Alice", "Bob", "Alice", "Bob", "Alice"])
        result = build_salesman_sheet(df, "Alice")
        assert len(result) == 3
        assert (result["Salesman"] == "Alice").all()

    def test_nonexistent_salesman(self):
        """Filtering by a salesman not in data → empty DataFrame."""
        df = _aging_with_salesman(n=3, salesmen=["Alice"] * 3)
        result = build_salesman_sheet(df, "Charlie")
        assert result.empty

    def test_columns_match_report_spec(self):
        """Output always has exactly the REPORT_COLUMNS."""
        df = _aging_with_salesman(n=2)
        result = build_salesman_sheet(df, df["Salesman"].iloc[0])
        assert list(result.columns) == REPORT_COLUMNS
