"""
Tests for the Customer Activity Report builder.
"""

from datetime import date, datetime

import pandas as pd
import pytest

from reports.customer_activity.builder import (
    OUTPUT_COLUMNS,
    build_customer_activity,
    split_by_salesman,
)
from tests.fixtures.sample_customers import make_customers


def _headers(rows):
    df = pd.DataFrame(rows)
    df["OrderDate"] = pd.to_datetime(df["OrderDate"], utc=True)
    for c in ["SalesOrderNumber", "CustomerRequisition"]:
        if c not in df.columns:
            df[c] = ""
    return df


class TestBuildCustomerActivity:

    def test_customer_no_orders(self):
        """Customer with no orders → Last Order = NaT, PO# = N/A."""
        customers = make_customers(n=2)
        headers = pd.DataFrame(columns=["CustomerAccount", "OrderDate", "SalesOrderNumber", "CustomerRequisition"])

        result = build_customer_activity(customers, headers)
        assert len(result) == 2
        assert (result["PO #"] == "N/A").all()
        assert (result["Sales Order Number"] == "N/A").all()

    def test_latest_order_picked(self):
        """When a customer has multiple orders, the latest date is selected."""
        customers = make_customers(n=1)
        acct = customers.iloc[0]["CustomerAccount"]
        headers = _headers([
            {"CustomerAccount": acct, "OrderDate": "2026-01-10", "SalesOrderNumber": "SO-OLD", "CustomerRequisition": "PO-OLD"},
            {"CustomerAccount": acct, "OrderDate": "2026-03-15", "SalesOrderNumber": "SO-NEW", "CustomerRequisition": "PO-NEW"},
        ])

        result = build_customer_activity(customers, headers)
        row = result[result["Customer Account"] == acct].iloc[0]
        assert row["Sales Order Number"] == "SO-NEW"
        assert row["PO #"] == "PO-NEW"

    def test_empty_customers(self):
        """No customers → empty result with correct columns."""
        result = build_customer_activity(pd.DataFrame(columns=["CustomerAccount", "CustomerName", "SalesGroup"]),
                                         pd.DataFrame())
        assert result.empty
        assert "Customer Account" in result.columns

    def test_all_customers_included(self):
        """Every customer appears even if they have no orders."""
        customers = make_customers(n=5)
        headers = _headers([
            {"CustomerAccount": customers.iloc[0]["CustomerAccount"],
             "OrderDate": "2026-02-20",
             "SalesOrderNumber": "SO-001",
             "CustomerRequisition": "PO-001"},
        ])

        result = build_customer_activity(customers, headers)
        assert len(result) == 5
        has_order = result[result["Sales Order Number"] != "N/A"]
        no_order = result[result["Sales Order Number"] == "N/A"]
        assert len(has_order) == 1
        assert len(no_order) == 4

    def test_missing_salesgroup(self):
        """Customers without SalesGroup get an empty string, not a crash."""
        customers = make_customers(n=2)
        customers["SalesGroup"] = ""
        headers = pd.DataFrame(columns=["CustomerAccount", "OrderDate", "SalesOrderNumber", "CustomerRequisition"])

        result = build_customer_activity(customers, headers)
        assert len(result) == 2
        assert (result["SalesGroup"] == "").all()


class TestSplitBySalesman:

    def test_split_by_salesman(self):
        """3 customers with 2 salesmen → 2 groups."""
        customers = make_customers(n=3, sales_groups=["SG01", "SG02", "SG01"])
        headers = pd.DataFrame(columns=["CustomerAccount", "OrderDate", "SalesOrderNumber", "CustomerRequisition"])
        activity = build_customer_activity(customers, headers)

        from unittest.mock import patch
        with patch("reports.customer_activity.builder.get_salesman_display_name_xl",
                   side_effect=lambda sg: f"Salesman-{sg}"):
            with patch("reports.customer_activity.builder.load_salesman_map"):
                assigned, unassigned = split_by_salesman(activity)

        assert len(assigned) == 2
        assert "Salesman-SG01" in assigned
        assert "Salesman-SG02" in assigned

    def test_unassigned_bucket(self):
        """Customers with empty SalesGroup go to unassigned."""
        customers = make_customers(n=2, sales_groups=["", ""])
        headers = pd.DataFrame(columns=["CustomerAccount", "OrderDate", "SalesOrderNumber", "CustomerRequisition"])
        activity = build_customer_activity(customers, headers)

        from unittest.mock import patch
        with patch("reports.customer_activity.builder.load_salesman_map"):
            assigned, unassigned = split_by_salesman(activity)

        assert len(assigned) == 0
        assert len(unassigned) == 2

    def test_empty_activity(self):
        """Empty activity → empty groups."""
        empty = pd.DataFrame(columns=OUTPUT_COLUMNS + ["SalesGroup"])
        from unittest.mock import patch
        with patch("reports.customer_activity.builder.load_salesman_map"):
            assigned, unassigned = split_by_salesman(empty)
        assert len(assigned) == 0
        assert unassigned.empty
