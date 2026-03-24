"""
Tests for the Invoiced Report aggregator, loader charge classification,
and writer output structure.
"""

import os
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from reports.invoiced.aggregator import (
    build_invoiced_views,
    build_reversal_audit,
)
from reports.invoiced.loader import _classify_charge
from tests.fixtures.sample_invoices import make_invoice_detail
from tests.helpers.compare import assert_workbook_structure


class TestClassifyCharge:

    def test_tariff(self):
        assert _classify_charge("Tariff Duty") == "tariff"

    def test_freight(self):
        assert _classify_charge("Freight Charge") == "freight"

    def test_cc(self):
        assert _classify_charge("CC Processing Fee") == "cc"

    def test_processing_is_cc(self):
        assert _classify_charge("Processing") == "cc"

    def test_other(self):
        assert _classify_charge("Miscellaneous") == "other"

    def test_case_insensitive(self):
        assert _classify_charge("TARIFF") == "tariff"


class TestBuildInvoicedViews:

    def test_normal_invoices_no_charges(self):
        """When all charges are 0, SubTotal == Total Invoice."""
        detail = make_invoice_detail(
            n=10,
            tariffs=[0.0] * 10,
            freights=[0.0] * 10,
            cc_charges=[0.0] * 10,
            subtotals=[100.0] * 10,
        )
        detail["Total Invoice"] = detail["SubTotal Invoices"]

        summary, commissions, details_net, credits, invoices = build_invoiced_views(detail)

        assert not summary.empty
        assert len(invoices) == 10
        assert credits.empty

    def test_with_charges(self):
        """SubTotal = Total - tariff - freight - CC (validated by factory)."""
        detail = make_invoice_detail(n=5)
        summary, commissions, details_net, credits, invoices = build_invoiced_views(detail)

        assert not summary.empty
        assert "Total Tariff Charges" in summary.columns or "Tariff Charges" in summary.columns

    def test_credits_identified(self):
        """Invoices with CRD/CM/FC in number are classified as credits."""
        detail = make_invoice_detail(n=4, invoice_numbers=["INV-001", "CRD-001", "CM-002", "FC-001"])
        summary, commissions, details_net, credits, invoices = build_invoiced_views(detail)

        assert len(credits) == 3
        assert len(invoices) == 1

    def test_reversal_audit(self):
        """Invoice appearing with both +$100 and -$100 → shows in audit."""
        detail = make_invoice_detail(n=2, invoice_numbers=["INV-001", "INV-001"])
        detail.loc[0, "Total Invoice"] = 100.0
        detail.loc[1, "Total Invoice"] = -100.0

        audit = build_reversal_audit(detail)
        assert not audit.empty
        assert "INV-001" in audit["InvoiceNumber"].values

    def test_no_reversals(self):
        """No mixed positive/negative → empty audit."""
        detail = make_invoice_detail(n=5)
        audit = build_reversal_audit(detail)
        assert audit.empty

    def test_commission_calculation(self):
        """Commission = (SubTotal + Tariff) * rate."""
        detail = make_invoice_detail(
            n=2,
            salesman_numbers=["01", "01"],
            subtotals=[1000.0, 500.0],
            tariffs=[50.0, 25.0],
        )
        detail["Total Invoice"] = detail["SubTotal Invoices"] + detail["Tariff Charges"] + detail["Freight Charges"] + detail["CC Charges"]

        with patch("reports.invoiced.aggregator.get_commission_rate", return_value=0.05):
            summary, commissions, *_ = build_invoiced_views(detail)

        assert not commissions.empty
        assert commissions["Percent"].iloc[0] == pytest.approx(0.05)
        base = commissions["Commission Base"].iloc[0]
        assert commissions["Commissions"].iloc[0] == pytest.approx(base * 0.05)

    def test_unassigned_salesman(self):
        """Rows with empty salesman number still process."""
        detail = make_invoice_detail(
            n=3,
            salesmen=["Unassigned", "Unassigned", "Unassigned"],
            salesman_numbers=["?unassigned", "?unassigned", "?unassigned"],
        )
        summary, commissions, *_ = build_invoiced_views(detail)
        assert not summary.empty

    def test_empty_invoices(self):
        """Empty detail → all empty views, no crash."""
        summary, commissions, details_net, credits, invoices = build_invoiced_views(pd.DataFrame())
        assert summary.empty
        assert commissions.empty
        assert details_net.empty

    def test_net_detail_by_invoice(self):
        """Duplicate invoice rows are netted (summed) by InvoiceNumber."""
        detail = make_invoice_detail(n=4, invoice_numbers=["INV-A", "INV-A", "INV-B", "INV-B"])
        detail["SubTotal Invoices"] = [100, 200, 300, 400]
        detail["Total Invoice"] = [110, 220, 330, 440]

        _, _, details_net, _, _ = build_invoiced_views(detail)
        inv_a = details_net[details_net["InvoiceNumber"] == "INV-A"]
        assert len(inv_a) == 1
        assert inv_a.iloc[0]["SubTotal Invoices"] == pytest.approx(300.0)


class TestInvoicedWriter:

    def test_excel_sheets(self, output_dir):
        """Invoiced writer produces the expected sheet set."""
        from reports.invoiced.writer import write_invoiced_report

        detail = make_invoice_detail(n=10)
        with patch("reports.invoiced.aggregator.get_commission_rate", return_value=0.05):
            summary, commissions, details_net, credits, invoices = build_invoiced_views(detail)

        audit = build_reversal_audit(detail)
        out_path = str(output_dir / "invoiced_test.xlsx")

        write_invoiced_report(
            summary=summary,
            commissions=commissions,
            details=details_net,
            credits=credits,
            invoices=invoices,
            audit=audit,
            out_path=out_path,
        )

        assert os.path.isfile(out_path)
        assert_workbook_structure(
            out_path,
            expected_sheets=["Summary by Customer", "Full Details"],
            min_rows={"Summary by Customer": 2},
        )
