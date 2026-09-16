"""Unit tests for the Ordered Report builder logic."""

import pandas as pd
import pytest

from reports.ordered.builder import FULL_DATA_ORDER, build_report


class TestBuildReport:
    """Tests for ``build_report()`` -- pure DataFrame manipulation, no API calls."""

    def test_basic_output_columns(
        self, sample_order_headers, sample_order_lines, sample_whs_lines, sample_packing_slips, period_daily,
    ):
        df, reason = build_report(
            sample_order_headers, sample_order_lines, sample_whs_lines, sample_packing_slips, period_daily,
        )
        assert reason is None
        assert not df.empty
        for col in FULL_DATA_ORDER:
            assert col in df.columns, f"Expected column '{col}' missing from output"

    def test_period_filter_narrows_rows(
        self, sample_order_headers, sample_order_lines, sample_whs_lines, sample_packing_slips, period_daily,
    ):
        """Only orders on 2026-02-20 should appear for the daily period."""
        df, _ = build_report(
            sample_order_headers, sample_order_lines, sample_whs_lines, sample_packing_slips, period_daily,
        )
        assert not df.empty
        assert "SO-003" not in df["SalesOrderNumber"].values

    def test_mtd_includes_wider_range(
        self, sample_order_headers, sample_order_lines, sample_whs_lines, sample_packing_slips, period_mtd,
    ):
        df, _ = build_report(
            sample_order_headers, sample_order_lines, sample_whs_lines, sample_packing_slips, period_mtd,
        )
        assert not df.empty
        assert "SO-003" in df["SalesOrderNumber"].values

    def test_salesman_filter(
        self, sample_order_headers, sample_order_lines, sample_whs_lines, sample_packing_slips, period_mtd,
    ):
        df, _ = build_report(
            sample_order_headers, sample_order_lines, sample_whs_lines, sample_packing_slips,
            period_mtd, salesman_filter="MKolko",
        )
        assert not df.empty
        assert all(s.lower() == "mkolko" for s in df["Salesman"].str.lower())

    def test_salesman_filter_no_match(
        self, sample_order_headers, sample_order_lines, sample_whs_lines, sample_packing_slips, period_mtd,
    ):
        df, reason = build_report(
            sample_order_headers, sample_order_lines, sample_whs_lines, sample_packing_slips,
            period_mtd, salesman_filter="NonExistent",
        )
        assert df.empty
        assert reason is not None
        assert "NonExistent" in reason

    def test_empty_headers(self, sample_order_lines, sample_whs_lines, sample_packing_slips, period_daily):
        df, reason = build_report(
            pd.DataFrame(), sample_order_lines, sample_whs_lines, sample_packing_slips, period_daily,
        )
        assert df.empty
        assert reason is not None

    def test_empty_lines(self, sample_order_headers, sample_whs_lines, sample_packing_slips, period_daily):
        df, reason = build_report(
            sample_order_headers, pd.DataFrame(), sample_whs_lines, sample_packing_slips, period_daily,
        )
        assert df.empty
        assert reason is not None

    def test_dollar_columns_non_negative(
        self, sample_order_headers, sample_order_lines, sample_whs_lines, sample_packing_slips, period_daily,
    ):
        df, _ = build_report(
            sample_order_headers, sample_order_lines, sample_whs_lines, sample_packing_slips, period_daily,
        )
        for col in ["Ordered $", "Shipped $"]:
            if col in df.columns:
                assert (df[col] >= 0).all(), f"{col} has negative values"
