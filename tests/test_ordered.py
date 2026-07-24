"""
Tests for the Ordered Report builder and writer.

All tests use in-memory DataFrames (no D365). Date freezing ensures
period filtering is deterministic.
"""

import os
from datetime import date

import pandas as pd
import pytest

from core.dates import PeriodSpec
from reports.ordered.builder import build_report
from reports.ordered.writer import write_report
from reports.ordered._temp_rules import apply_temp_rules
from tests.fixtures.sample_orders import (
    make_order_headers,
    make_order_lines,
    make_packing_slips,
    make_whs_lines,
)
from tests.helpers.compare import assert_workbook_structure


def _period(start="2026-02-20", end="2026-02-20", label="Daily"):
    return PeriodSpec(
        label=label,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        subfolder=label,
        filename_tag=f"{start}_to_{end}",
    )


class TestBuildReport:

    def test_normal_10_orders_all_shipped(self):
        """All lines invoiced with full WHS release → QtyShipped == QtyOrdered."""
        headers = make_order_headers(n=10, order_date="2026-02-20")
        lines = make_order_lines(headers, raw_status="invoiced", qty_ordered=10)
        whs = make_whs_lines(lines, released_pct=1.0)
        ps = make_packing_slips(lines, shipped_pct=1.0)

        df, reason = build_report(headers, lines, whs, ps, _period())
        assert reason is None
        assert len(df) > 0
        assert (df["QtyShipped"] == df["QtyOrdered"]).all()
        assert all(f == "100%" for f in df["Fulfillment %"])

    def test_empty_headers(self):
        """No headers → empty report with reason."""
        headers = pd.DataFrame()
        lines = pd.DataFrame()
        whs = pd.DataFrame()
        ps = pd.DataFrame()

        df, reason = build_report(headers, lines, whs, ps, _period())
        assert df.empty
        assert reason is not None
        assert "No order data" in reason

    def test_empty_lines(self):
        """Headers exist but no lines → empty report."""
        headers = make_order_headers(n=3)
        lines = pd.DataFrame()

        df, reason = build_report(headers, lines, pd.DataFrame(), pd.DataFrame(), _period())
        assert df.empty
        assert reason is not None

    def test_partial_release_in_process(self):
        """50% WHS released, packing slip join mismatch → InProcess status.

        When WHSReleased < QtyOrdered and PackSlipQty doesn't match WHSReleased,
        the builder classifies the line as InProcess with the open portion
        set to QtyOrdered - WHSReleased.
        """
        headers = make_order_headers(n=1, order_date="2026-02-20")
        lines = make_order_lines(headers, lines_per_order=1, qty_ordered=10, raw_status="backorder")
        whs = make_whs_lines(lines, released_pct=0.5)
        ps = make_packing_slips(lines, shipped_pct=0.5)

        df, reason = build_report(headers, lines, whs, ps, _period())
        assert reason is None
        assert len(df) == 1
        row = df.iloc[0]
        assert row["WHSReleased"] == pytest.approx(5.0)
        assert row["QtyOpen"] == pytest.approx(5.0)
        assert row["DisplayLineStatus"] == "InProcess"

    def test_cancelled_order(self):
        """Order-level cancel → all lines cancelled."""
        headers = make_order_headers(n=1, order_date="2026-02-20", statuses=["cancelled"])
        lines = make_order_lines(headers, lines_per_order=2, qty_ordered=10, raw_status="backorder")

        df, reason = build_report(headers, lines, pd.DataFrame(), pd.DataFrame(), _period())
        assert reason is None
        assert (df["DisplayLineStatus"] == "Cancelled").all()
        assert (df["QtyCancelled"] == df["QtyOrdered"]).all()

    def test_line_cancelled(self):
        """Line-level cancel (not order-level)."""
        headers = make_order_headers(n=1, order_date="2026-02-20")
        lines = make_order_lines(headers, lines_per_order=1, qty_ordered=10, raw_status="cancelled")

        df, reason = build_report(headers, lines, pd.DataFrame(), pd.DataFrame(), _period())
        assert reason is None
        assert df.iloc[0]["DisplayLineStatus"] == "Cancelled"
        assert df.iloc[0]["QtyCancelled"] == pytest.approx(10.0)

    def test_error_item_filtered(self):
        """Lines with 'ERROR ITEM' in Item# are removed."""
        headers = make_order_headers(n=1, order_date="2026-02-20")
        lines = make_order_lines(headers, lines_per_order=2)
        lines.loc[0, "Item#"] = "ERROR ITEM 123"

        df, reason = build_report(headers, lines, pd.DataFrame(), pd.DataFrame(), _period())
        assert reason is None
        assert not df["Item#"].str.contains("ERROR", case=False).any()

    def test_all_error_items(self):
        """If ALL lines are error items → empty + reason."""
        headers = make_order_headers(n=1, order_date="2026-02-20")
        lines = make_order_lines(headers, lines_per_order=2)
        lines["Item#"] = "ERROR ITEM"

        df, reason = build_report(headers, lines, pd.DataFrame(), pd.DataFrame(), _period())
        assert df.empty
        assert "error items" in reason.lower()

    def test_zero_qty_ordered(self):
        """QtyOrdered=0 → Fulfillment% is blank, not a div/0 crash."""
        headers = make_order_headers(n=1, order_date="2026-02-20")
        lines = make_order_lines(headers, lines_per_order=1, qty_ordered=0, raw_status="backorder")

        df, reason = build_report(headers, lines, pd.DataFrame(), pd.DataFrame(), _period())
        assert reason is None
        assert df.iloc[0]["Fulfillment %"] == ""

    def test_whs_exceeds_ordered(self):
        """WHSReleased > QtyOrdered should not crash."""
        headers = make_order_headers(n=1, order_date="2026-02-20")
        lines = make_order_lines(headers, lines_per_order=1, qty_ordered=5, raw_status="backorder")
        whs = make_whs_lines(lines, released_pct=2.0)

        df, reason = build_report(headers, lines, whs, pd.DataFrame(), _period())
        assert reason is None
        assert len(df) == 1

    def test_missing_unit_price_column(self):
        """When UnitPrice/Price columns are absent, falls back to Total/Qty."""
        headers = make_order_headers(n=1, order_date="2026-02-20")
        lines = make_order_lines(headers, lines_per_order=1, qty_ordered=10, raw_status="backorder")
        lines = lines.drop(columns=["UnitPrice", "SalesPrice"])
        lines["Total"] = 100.0

        df, reason = build_report(headers, lines, pd.DataFrame(), pd.DataFrame(), _period())
        assert reason is None
        assert df.iloc[0]["UnitPrice"] == pytest.approx(10.0)

    def test_null_unit_price_becomes_zero(self):
        """When UnitPrice column exists but value is null, to_number returns 0."""
        headers = make_order_headers(n=1, order_date="2026-02-20")
        lines = make_order_lines(headers, lines_per_order=1, qty_ordered=10, raw_status="backorder")
        lines["UnitPrice"] = None

        df, reason = build_report(headers, lines, pd.DataFrame(), pd.DataFrame(), _period())
        assert reason is None
        assert df.iloc[0]["UnitPrice"] == pytest.approx(0.0)

    def test_date_boundary_inclusion(self):
        """Orders exactly on period start and end dates are included."""
        headers = make_order_headers(n=2, order_date="2026-02-01")
        headers.loc[1, "OrderDate"] = pd.Timestamp("2026-02-28")
        lines = make_order_lines(headers, lines_per_order=1, raw_status="backorder")

        period = _period("2026-02-01", "2026-02-28", "MTD")
        df, reason = build_report(headers, lines, pd.DataFrame(), pd.DataFrame(), period)
        assert reason is None
        assert len(df) == 2

    def test_orders_outside_period_excluded(self):
        """Orders outside the period date range are excluded."""
        headers = make_order_headers(n=2, order_date="2026-01-15")
        lines = make_order_lines(headers, lines_per_order=1, raw_status="backorder")

        period = _period("2026-02-01", "2026-02-28", "MTD")
        df, reason = build_report(headers, lines, pd.DataFrame(), pd.DataFrame(), period)
        assert df.empty
        assert reason is not None

    def test_salesman_filter_no_match(self):
        """Filtering by a salesman not in data → empty + reason."""
        headers = make_order_headers(n=3, order_date="2026-02-20", salesmen=["SM01"])
        lines = make_order_lines(headers, raw_status="backorder")

        df, reason = build_report(headers, lines, pd.DataFrame(), pd.DataFrame(),
                                  _period(), salesman_filter="NonExistent")
        assert df.empty
        assert "salesman" in reason.lower()

    def test_salesman_filter_match(self):
        """Filtering by salesman keeps only matching rows."""
        headers = make_order_headers(n=4, order_date="2026-02-20",
                                     salesmen=["SM01", "SM02", "SM01", "SM02"])
        lines = make_order_lines(headers, lines_per_order=1, raw_status="backorder")

        df, reason = build_report(headers, lines, pd.DataFrame(), pd.DataFrame(),
                                  _period(), salesman_filter="SM01")
        assert reason is None
        assert (df["Salesman"] == "SM01").all()


class TestTempRules:

    def test_amazon_open_to_cancelled(self):
        """Amazon accounts (9300/9301) with QtyOpen > 0 → cancelled."""
        df = pd.DataFrame({
            "CustomerAccount": ["9300", "9301", "C100"],
            "QtyOrdered": [10.0, 10.0, 10.0],
            "QtyShipped": [0.0, 5.0, 0.0],
            "QtyOpen": [10.0, 5.0, 10.0],
            "QtyReleased": [0.0, 0.0, 0.0],
            "QtyCancelled": [0.0, 0.0, 0.0],
            "QtyRemainder": [10.0, 10.0, 10.0],
            "DisplayLineStatus": ["Open", "BackOrdered", "Open"],
        })
        result = apply_temp_rules(df)

        assert result.loc[0, "QtyOpen"] == 0
        assert result.loc[0, "QtyCancelled"] == pytest.approx(10.0)
        assert result.loc[0, "DisplayLineStatus"] == "Cancelled"

        assert result.loc[1, "QtyOpen"] == 0
        assert result.loc[1, "QtyCancelled"] == pytest.approx(5.0)
        assert result.loc[1, "QtyRemainder"] == pytest.approx(5.0)

        # Non-Amazon row is unchanged
        assert result.loc[2, "QtyOpen"] == pytest.approx(10.0)
        assert result.loc[2, "DisplayLineStatus"] == "Open"


class TestWriteReport:

    def test_excel_output_sheets(self, output_dir):
        """Default variant produces the expected sheets."""
        headers = make_order_headers(n=5, order_date="2026-02-20")
        lines = make_order_lines(headers, raw_status="invoiced")
        whs = make_whs_lines(lines, released_pct=1.0)
        ps = make_packing_slips(lines, shipped_pct=1.0)

        df, _ = build_report(headers, lines, whs, ps, _period())
        out_path = str(output_dir / "ordered_default.xlsx")
        write_report(df, out_path)

        assert os.path.isfile(out_path)
        assert_workbook_structure(
            out_path,
            expected_sheets=["Summary", "By Customer", "By Item", "By Order", "By Salesman", "Full Data"],
            min_rows={"Full Data": 2},
        )

    def test_filtered_variant(self, output_dir):
        """Filtered variant for per-customer runs."""
        headers = make_order_headers(n=3, order_date="2026-02-20")
        lines = make_order_lines(headers, raw_status="invoiced")
        whs = make_whs_lines(lines, released_pct=1.0)
        ps = make_packing_slips(lines, shipped_pct=1.0)

        df, _ = build_report(headers, lines, whs, ps, _period())
        out_path = str(output_dir / "ordered_filtered.xlsx")
        write_report(df, out_path, report_variant="filtered")

        assert os.path.isfile(out_path)
        assert_workbook_structure(out_path, expected_sheets=["Summary", "By Item", "By Order"])
