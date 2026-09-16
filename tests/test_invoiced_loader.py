"""Unit tests for the Invoiced Report loader / aggregator logic."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from reports.invoiced.aggregator import build_invoiced_views, build_reversal_audit
from reports.invoiced.runner import InvoicedReportRunner


class TestBuildInvoicedViews:
    """Tests for ``build_invoiced_views()`` -- pure aggregation, no API calls."""

    def test_returns_five_dataframes(self, sample_invoice_detail):
        result = build_invoiced_views(sample_invoice_detail)
        assert len(result) == 5, "Expected 5 DataFrames from build_invoiced_views"

    def test_summary_not_empty(self, sample_invoice_detail):
        summary, *_ = build_invoiced_views(sample_invoice_detail)
        assert not summary.empty

    def test_commissions_not_empty(self, sample_invoice_detail):
        _, commissions, *_ = build_invoiced_views(sample_invoice_detail)
        assert not commissions.empty

    def test_empty_input(self):
        result = build_invoiced_views(pd.DataFrame())
        assert all(df.empty for df in result)


class TestBuildReversalAudit:
    """Tests for ``build_reversal_audit()``."""

    def test_returns_dataframe(self, sample_invoice_detail):
        audit = build_reversal_audit(sample_invoice_detail)
        assert isinstance(audit, pd.DataFrame)

    def test_empty_input(self):
        audit = build_reversal_audit(pd.DataFrame())
        assert isinstance(audit, pd.DataFrame)


def test_salesman_report_fetches_only_the_selected_period():
    runner = InvoicedReportRunner()
    plan = SimpleNamespace(
        fetch_start=date(2026, 7, 13),
        fetch_end=date(2026, 7, 14),
        periods=[],
    )
    with (
        patch.object(runner, "connect", return_value=("url", "token", "company")),
        patch("reports.invoiced.runner.fetch_invoice_detail", return_value=pd.DataFrame()) as fetch_detail,
    ):
        runner._run_standard(plan, None, ["MKolko"], None)

    assert fetch_detail.call_args.args[2:4] == (plan.fetch_start, plan.fetch_end)
