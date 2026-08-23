"""Offline unit tests for Number 4 ↔ invoiced reconcile helpers."""

from datetime import date

from web.reporting.reconcile_number4 import (
    _get,
    _is_free_text_invoice,
    _parse_month_header,
    rolling_12_months,
)


def test_rolling_12_includes_current_month():
    months = rolling_12_months(date(2026, 8, 6))
    assert len(months) == 12
    assert months[0] == (2025, 9)
    assert months[-1] == (2026, 8)


def test_parse_month_header_formats():
    assert _parse_month_header("Jul-25 $") == (2025, 7)
    assert _parse_month_header("Jul-25$") == (2025, 7)
    assert _parse_month_header("2025-07 $") == (2025, 7)
    assert _parse_month_header("Total $") is None
    assert _parse_month_header("Jul-25 Qty") is None


def test_get_customer_hash_column():
    row = {"Customer #": "00011005", "Sep-25 $": 100.0}
    assert _get(row, "Customer #", "CustomerAccount", "Cust. #") == "00011005"


def test_free_text_invoice_prefixes():
    assert _is_free_text_invoice({"InvoiceNumber": "FINV-000719", "salesorder": "SO1"})
    assert _is_free_text_invoice({"InvoiceNumber": "FCRD-003244", "salesorder": ""})
    assert _is_free_text_invoice({"InvoiceNumber": "finv_99", "SalesOrderNumber": "X"})
    assert not _is_free_text_invoice({"InvoiceNumber": "INV001", "salesorder": "SO1"})


def test_free_text_blank_sales_order():
    assert _is_free_text_invoice({"InvoiceNumber": "INV001", "salesorder": ""})
    assert _is_free_text_invoice({"InvoiceNumber": "INV001"})
    assert not _is_free_text_invoice({"InvoiceNumber": "INV001", "SalesOrderNumber": "SO9"})
