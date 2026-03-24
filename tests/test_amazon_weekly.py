"""
Tests for the Amazon Weekly report (ordered-based, customer-filtered).

The Amazon Weekly report reuses the Ordered builder + writer with
customer accounts 9300/9301 and a 7-day window.
"""

import os
from datetime import date

import pandas as pd
import pytest

from core.dates import PeriodSpec, parse_period
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
from tests.helpers.date_helpers import freeze_today


class TestAmazonWeekly:

    def test_only_amazon_customers(self, output_dir):
        """Only accounts 9300 and 9301 appear in the amazon_weekly variant."""
        with freeze_today(date(2026, 3, 18)):
            spec = parse_period("last_7_days")

        mixed_customers = ["9300", "9301", "C100", "C200"]
        headers = make_order_headers(n=4, order_date=str(spec.start_date), customers=mixed_customers)
        lines = make_order_lines(headers, raw_status="invoiced")
        whs = make_whs_lines(lines, released_pct=1.0)
        ps = make_packing_slips(lines, shipped_pct=1.0)

        df, reason = build_report(headers, lines, whs, ps, spec)
        assert reason is None

        # Filter to Amazon accounts (as the runner does)
        amazon_df = df[df["CustomerAccount"].isin(["9300", "9301"])].copy()
        assert len(amazon_df) > 0

        out_path = str(output_dir / "amazon_weekly.xlsx")
        write_report(amazon_df, out_path, report_variant="amazon_weekly")
        assert os.path.isfile(out_path)
        assert_workbook_structure(out_path, expected_sheets=["Summary", "By Order"])

    def test_7_day_window(self):
        """Frozen to Wednesday → window is prior Thursday through Wednesday."""
        # 2026-03-18 is a Wednesday
        with freeze_today(date(2026, 3, 18)):
            spec = parse_period("last_7_days")
        assert spec.start_date == date(2026, 3, 12)
        assert spec.end_date == date(2026, 3, 18)

    def test_temp_rules_applied_amazon(self):
        """Amazon open qty on account 9300 is reclassified as cancelled."""
        headers = make_order_headers(n=2, order_date="2026-03-15", customers=["9300", "9300"])
        lines = make_order_lines(headers, lines_per_order=1, qty_ordered=10, raw_status="backorder")
        whs = make_whs_lines(lines, released_pct=0.0)

        spec = PeriodSpec(label="test", start_date=date(2026, 3, 15),
                          end_date=date(2026, 3, 15), subfolder="Test", filename_tag="test")
        df, _ = build_report(headers, lines, whs, pd.DataFrame(), spec)
        assert not df.empty

        # After temp rules in build_report: QtyOpen should be 0, cancelled
        assert (df["QtyOpen"] == 0).all()
        assert (df["DisplayLineStatus"] == "Cancelled").all()

    def test_non_amazon_unaffected_by_temp_rules(self):
        """Non-Amazon customer open orders are NOT reclassified."""
        headers = make_order_headers(n=1, order_date="2026-03-15", customers=["C100"])
        lines = make_order_lines(headers, lines_per_order=1, qty_ordered=10, raw_status="backorder")
        whs = make_whs_lines(lines, released_pct=0.0)

        spec = PeriodSpec(label="test", start_date=date(2026, 3, 15),
                          end_date=date(2026, 3, 15), subfolder="Test", filename_tag="test")
        df, _ = build_report(headers, lines, whs, pd.DataFrame(), spec)
        assert df.iloc[0]["QtyOpen"] == pytest.approx(10.0)
        assert df.iloc[0]["DisplayLineStatus"] == "Open"
