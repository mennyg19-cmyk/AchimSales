"""Regression tests for the invoiced report's math and tab building.

These are the numbers the owner cares about: credit detection, commission
math, net totals, and which tabs appear. They run as pure functions -- no
database, no network -- so a cheaper model can run them fast.
"""

from __future__ import annotations

from rebuild.reports import conditions
from rebuild.reports import export as export_file
from rebuild.reports.adapter import normalize
from rebuild.reports.engine import build_tabs
from rebuild.reports.lib import iso_date
from rebuild.reports.transforms import TRANSFORMS, commission_cards, commission_monthly_pivot


_SAMPLE_TAB = {
    "label": "Totals",
    "columns": [
        {"field": "Salesman", "label": "Salesman", "type": "text"},
        {"field": "Total", "label": "Total", "type": "money"},
    ],
    "rows": [{"Salesman": "Alice", "Total": 1234.5}, {"Salesman": "Bob", "Total": 0.0}],
    "total": {"Salesman": "TOTAL", "Total": 1234.5},
}


def test_csv_export_has_header_rows_and_total():
    text = export_file.to_csv(_SAMPLE_TAB).decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line]
    assert lines[0] == "Salesman,Total"
    assert lines[1] == "Alice,1234.5"
    assert lines[-1] == "TOTAL,1234.5"


def test_xlsx_export_is_a_real_workbook():
    import io
    from openpyxl import load_workbook

    data = export_file.to_xlsx(_SAMPLE_TAB)
    book = load_workbook(io.BytesIO(data))
    sheet = book.active
    assert sheet["A1"].value == "Salesman"
    assert sheet["B2"].value == 1234.5
    assert sheet["A4"].value == "TOTAL"


def test_export_filename_is_sanitized():
    assert export_file.filename_for("invoiced", "totals_by_salesman", "xlsx") == "invoiced_totals_by_salesman.xlsx"
    assert export_file.filename_for("a/b", "c d", "csv") == "a_b_c_d.csv"


def test_iso_date_parses_rfc_and_common_formats():
    assert iso_date("Fri, 15 Jan 2026 00:00:00 GMT") == "2026-01-15"
    assert iso_date("2026-01-15T00:00:00") == "2026-01-15"
    assert iso_date("01/15/2026") == "2026-01-15"
    assert iso_date("") == ""


def _raw_sample():
    return [
        # Alice: a January invoice (commissionable net excludes freight + cc).
        {"InvoiceNumber": "INV001", "InvoiceDate": "2026-01-15", "CustomerAccount": "C1",
         "CustomerName": "Acme", "salesman": "S1", "SalesmanName": "Alice", "amount": 1000,
         "Tariff Charges": 50, "Freight Charges": 20, "CC Charges": 10, "Misc Charges": 5,
         "Total Invoice": 1085, "IsCredit": 0, "commission": 0.06},
        # Alice: a February credit (no IsCredit flag -> detected from CRD prefix).
        {"InvoiceNumber": "CRD003", "InvoiceDate": "2026-02-12", "CustomerAccount": "C1",
         "CustomerName": "Acme", "salesman": "S1", "SalesmanName": "Alice", "amount": -100,
         "Total Invoice": -100, "commission": 0.06},
        # Bob: a February invoice + a March reversal pair (nets to zero).
        {"InvoiceNumber": "INV002", "InvoiceDate": "2026-02-10", "CustomerAccount": "C2",
         "CustomerName": "Beta", "salesman": "S2", "SalesmanName": "Bob", "amount": 2000,
         "Freight Charges": 40, "CC Charges": 15, "Total Invoice": 2055, "IsCredit": 0,
         "commission": 5},  # whole-percent form -> normalized to 0.05
        {"InvoiceNumber": "INV004", "InvoiceDate": "2026-03-01", "CustomerAccount": "C2",
         "CustomerName": "Beta", "salesman": "S2", "SalesmanName": "Bob", "amount": 500,
         "Total Invoice": 500, "IsCredit": 0, "commission": 5},
        {"InvoiceNumber": "INV004", "InvoiceDate": "2026-03-02", "CustomerAccount": "C2",
         "CustomerName": "Beta", "salesman": "S2", "SalesmanName": "Bob", "amount": -500,
         "Total Invoice": -500, "IsCredit": 0, "commission": 5},
    ]


def test_adapter_detects_credit_from_invoice_number_when_flag_missing():
    rows = normalize("invoiced", _raw_sample())
    by_invoice = {r["InvoiceNumber"]: r for r in rows}
    assert by_invoice["CRD003"]["IsCredit"] is True
    assert by_invoice["INV001"]["IsCredit"] is False


def test_adapter_normalizes_whole_percent_commission_to_fraction():
    rows = normalize("invoiced", _raw_sample())
    bob = next(r for r in rows if r["Salesman"] == "S2")
    assert bob["commission"] == 0.05


def test_commission_uses_net_of_freight_and_cc_and_includes_credits():
    rows = normalize("invoiced", _raw_sample())
    pivot = commission_monthly_pivot(rows, {})
    by_salesman = {r["Salesman"]: r for r in pivot["rows"]}
    # Alice Jan: net = 1085 - 20 - 10 = 1055; * 0.06 = 63.30. Feb credit: -100 * 0.06 = -6.00.
    assert by_salesman["Alice"]["YTD Commission"] == 57.30
    # Bob Feb: net = 2055 - 40 - 15 = 2000; * 0.05 = 100.00. March reversal nets to 0.
    assert by_salesman["Bob"]["YTD Commission"] == 100.00
    assert pivot["total"]["YTD Commission"] == 157.30


def test_commission_ytd_sums_raw_months_not_rounded_ones():
    # Two months whose commission is x.xx5 each: rounding each month first and
    # summing (10.01 + 10.01 = 20.02) drifts from rounding the raw sum (20.01).
    raw = [
        {"InvoiceNumber": "INV1", "InvoiceDate": "2026-01-15", "salesman": "S1",
         "SalesmanName": "Penny", "amount": 100.05, "commission": 0.1},
        {"InvoiceNumber": "INV2", "InvoiceDate": "2026-02-15", "salesman": "S1",
         "SalesmanName": "Penny", "amount": 100.05, "commission": 0.1},
    ]
    rows = normalize("invoiced", raw)
    pivot = commission_monthly_pivot(rows, {})
    cards = commission_cards(rows, {})
    assert pivot["rows"][0]["YTD Commission"] == 20.01
    assert cards["salesmen"][0]["ytd"]["commission"] == 20.01
    assert pivot["total"]["YTD Commission"] == cards["grand"]["commission"] == 20.01


def test_commission_cards_match_pivot_ytd():
    rows = normalize("invoiced", _raw_sample())
    pivot = commission_monthly_pivot(rows, {})
    cards = commission_cards(rows, {})
    assert cards["layout"] == "commission_cards"
    pivot_ytd = {r["Salesman"]: r["YTD Commission"] for r in pivot["rows"]}
    for salesman in cards["salesmen"]:
        assert salesman["ytd"]["commission"] == pivot_ytd[salesman["salesman_name"]]
    # Grand total agrees across both views.
    assert cards["grand"]["commission"] == pivot["total"]["YTD Commission"]


def test_adapter_keeps_real_zero_total_and_only_fills_blank():
    raw = [
        # A genuine 0.00 net invoice: must be kept, not recomputed from parts.
        {"InvoiceNumber": "INV010", "Total Invoice": 0, "amount": 100,
         "Freight Charges": 0, "salesman": "S1"},
        # No Total sent at all: summed from parts (100 + 5 = 105).
        {"InvoiceNumber": "INV011", "amount": 100, "Misc Charges": 5, "salesman": "S1"},
    ]
    rows = normalize("invoiced", raw)
    by_invoice = {r["InvoiceNumber"]: r for r in rows}
    assert by_invoice["INV010"]["Total Invoice"] == 0.0
    assert by_invoice["INV011"]["Total Invoice"] == 105.0


def test_summary_groups_by_customer_and_salesman_with_distinct_invoice_count():
    rows = normalize("invoiced", _raw_sample())
    tabs = build_tabs(rows, _summary_tab(), transforms=TRANSFORMS)
    summary = tabs[0]
    c1 = next(r for r in summary["rows"] if r["CustomerAccount"] == "C1")
    # C1 net = 1085 (invoice) - 100 (credit) = 985; two distinct invoices.
    assert c1["Total Invoices"] == 985.0
    assert c1["InvoiceCount"] == 2


def test_conditions_gate_audit_and_salesman_tabs():
    rows = normalize("invoiced", _raw_sample())
    assert conditions.has_reversals(rows) is True
    assert conditions.has_multiple_salesmen(rows) is True
    assert conditions.reversal_invoice_numbers(rows) == {"INV004"}

    single = [r for r in rows if r["Salesman"] == "S1"]
    assert conditions.has_multiple_salesmen(single) is False


def test_credit_and_invoice_filters_split_rows():
    rows = normalize("invoiced", _raw_sample())
    tabs = build_tabs(rows, _split_tabs(), transforms=TRANSFORMS)
    credits = next(t for t in tabs if t["key"] == "credits")
    invoices = next(t for t in tabs if t["key"] == "invoices")
    assert len(credits["rows"]) == 1
    assert len(invoices["rows"]) == 4


def _summary_tab():
    return [{
        "tab_key": "summary_by_customer", "label": "Summary by Customer",
        "group_by": ["CustomerAccount", "CustomerName", "Salesman", "SalesmanName"],
        "aggregations": {
            "InvoiceCount": "count_distinct:InvoiceNumber",
            "Total Invoices": "sum:Total Invoice",
        },
        "column_keys": [
            {"field": "CustomerAccount", "type": "text"},
            {"field": "InvoiceCount", "type": "int"},
            {"field": "Total Invoices", "type": "money"},
        ],
    }]


def _split_tabs():
    cols = [{"field": "InvoiceNumber", "type": "text"}]
    return [
        {"tab_key": "credits", "label": "Credits", "filter_expr": '{"op":"truthy","field":"IsCredit"}', "column_keys": cols},
        {"tab_key": "invoices", "label": "Invoices", "filter_expr": '{"op":"falsy","field":"IsCredit"}', "column_keys": cols},
    ]
