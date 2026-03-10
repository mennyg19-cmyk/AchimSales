"""
Shared pytest fixtures for report builder/loader unit tests.

Provides small, realistic DataFrames that mirror the structure returned
by D365 OData fetchers so builder logic can be tested in isolation.
"""

from datetime import date, datetime

import pandas as pd
import pytest

from core.dates import PeriodSpec


@pytest.fixture
def period_daily() -> PeriodSpec:
    return PeriodSpec(
        label="Daily 2026-02-20",
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        subfolder="Daily",
        filename_tag="2026-02-20",
    )


@pytest.fixture
def period_mtd() -> PeriodSpec:
    return PeriodSpec(
        label="MTD Feb 2026",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 20),
        subfolder="MTD",
        filename_tag="MTD_2026-02",
    )


@pytest.fixture
def sample_order_headers() -> pd.DataFrame:
    return pd.DataFrame({
        "SalesOrderNumber": ["SO-001", "SO-002", "SO-003"],
        "CustomerAccount": ["C100", "C200", "C100"],
        "SalesOrderName": ["Alpha Corp", "Beta Inc", "Alpha Corp"],
        "OrderDate": pd.to_datetime(["2026-02-20", "2026-02-20", "2026-02-15"]),
        "OrderStatus": ["", "", ""],
        "OrderProcessingStatus": ["", "", ""],
        "Salesman": ["MKolko", "JSmith", "MKolko"],
        "CustomerName": ["Alpha Corp", "Beta Inc", "Alpha Corp"],
        "CustomerRequisition": ["PO-A1", "PO-B1", "PO-A2"],
    })


@pytest.fixture
def sample_order_lines() -> pd.DataFrame:
    return pd.DataFrame({
        "SalesOrderNumber": ["SO-001", "SO-001", "SO-002", "SO-003"],
        "LineNumber": [1, 2, 1, 1],
        "Item#": ["ITEM-A", "ITEM-B", "ITEM-C", "ITEM-A"],
        "LineDescription": ["Widget A", "Widget B", "Gadget C", "Widget A"],
        "QtyOrdered": [10.0, 5.0, 20.0, 15.0],
        "UnitPrice": [12.50, 25.00, 8.00, 12.50],
        "RawLineStatus": ["backorder", "invoiced", "backorder", "backorder"],
        "InventoryLotId": ["INV-001", "INV-002", "INV-003", "INV-004"],
    })


@pytest.fixture
def sample_whs_lines() -> pd.DataFrame:
    return pd.DataFrame({
        "InventTransId": ["INV-001", "INV-002", "INV-003", "INV-004"],
        "WHSReleased": [10.0, 5.0, 0.0, 15.0],
    })


@pytest.fixture
def sample_packing_slips() -> pd.DataFrame:
    return pd.DataFrame({
        "InventTransId": ["INV-002"],
        "SalesId": ["SO-001"],
        "LineNum": [2],
        "PackSlipQty": [5.0],
    })


@pytest.fixture
def sample_invoice_detail() -> pd.DataFrame:
    """Canonical invoice detail as returned by ``fetch_invoice_detail``."""
    return pd.DataFrame({
        "CustomerAccount": ["C100", "C100", "C200", "C100"],
        "CustomerName": ["Alpha Corp", "Alpha Corp", "Beta Inc", "Alpha Corp"],
        "InvoiceDate": pd.to_datetime(["2026-02-20", "2026-01-15", "2026-02-10", "2025-02-20"]),
        "InvoiceNumber": ["INV-001", "INV-002", "INV-003", "INV-004"],
        "SalesOrderNumber": ["SO-001", "SO-002", "SO-003", "SO-004"],
        "SubTotal Invoices": [100.0, 200.0, 150.0, 120.0],
        "Tariff Charges": [5.0, 10.0, 7.5, 6.0],
        "Freight Charges": [3.0, 6.0, 4.5, 3.5],
        "CC Charges": [2.0, 4.0, 3.0, 2.5],
        "Total Invoice": [110.0, 220.0, 165.0, 132.0],
        "Salesman": ["MKolko", "MKolko", "JSmith", "MKolko"],
        "SalesmanNumber": ["01", "01", "02", "01"],
        "SalesmanName": ["Mike Kolko", "Mike Kolko", "John Smith", "Mike Kolko"],
    })
