"""Offline unit tests for salesman↔invoiced reconcile helpers."""

from __future__ import annotations

from datetime import date

from web.reporting.reconcile_salesman import (
    _compare_money_maps,
    _invoice_date,
    _invoice_total,
    _salesman_month,
    _salesman_ytd,
    _slice_ok,
)


def test_invoice_total_prefers_components_when_present():
    row = {
        "Total Invoice": 999,
        "SubTotal Invoices": 100,
        "Tariff Charges": 10,
        "Freight Charges": 5,
        "CC Charges": 2,
        "Misc Charges": 3,
    }
    assert _invoice_total(row) == 120.0


def test_invoice_date_parses_iso_and_sql():
    assert _invoice_date({"InvoiceDate": "2026-08-05 12:00:00"}) == date(2026, 8, 5)
    assert _invoice_date({"InvoiceDate": "2026-01-15"}) == date(2026, 1, 15)


def test_invoice_date_parses_rfc1123():
    assert _invoice_date({"InvoiceDate": "Thu, 15 Jan 2026 00:00:00 GMT"}) == date(2026, 1, 15)


def test_salesman_month_and_ytd_columns():
    row = {
        "Jan This Year": 10,
        "Feb This Year": 20,
        "Mar This Year": 30,
        "Jan Last Year": 5,
        "YTD This Year": 60,
    }
    assert _salesman_month(row, 1, which="ty") == 10.0
    assert _salesman_month(row, 1, which="ly") == 5.0
    assert _salesman_ytd(row, 3) == 60.0


def test_compare_money_maps_and_slice_ok():
    left = {"A": 100.0, "B": 50.0}
    right = {"A": 100.0, "B": 50.01}
    cmp = _compare_money_maps(left, right, left_label="salesman", right_label="invoiced")
    assert cmp["matched_within_5c"] == 2
    assert cmp["amount_diffs"] == 0
    assert _slice_ok(150.0, 150.01, cmp) is True

    bad = _compare_money_maps(
        {"A": 100.0}, {"A": 110.0},
        left_label="salesman", right_label="invoiced",
    )
    assert bad["amount_diffs"] == 1
    assert _slice_ok(100.0, 110.0, bad) is False
