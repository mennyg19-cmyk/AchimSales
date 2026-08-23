"""Offline tests for key-matched parity compare + report writer."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook

from tools.parity.data_compare import compare_workbooks_data
from tools.parity.report import compare_pair, write_index, write_report


def _xlsx(path: Path, sheets: dict[str, list[list]]) -> None:
    wb = Workbook()
    first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet(name)
        if first:
            ws.title = name
            first = False
        for row in rows:
            ws.append(row)
    wb.save(path)


def test_ignores_column_order_and_extra_test_columns(tmp_path: Path):
    live = tmp_path / "live.xlsx"
    test = tmp_path / "test.xlsx"
    _xlsx(live, {
        "Full Details": [
            ["InvoiceNumber", "CustomerAccount", "SubTotal Invoices"],
            ["IN1", "100", 10],
            ["IN2", "200", 20],
        ],
    })
    _xlsx(test, {
        "Full Details": [
            ["CustomerAccount", "Misc Charges", "InvoiceNumber", "SubTotal Invoices"],
            ["100", 0, "IN1", 10],
            ["200", 5, "IN2", 20],
        ],
    })
    result = compare_workbooks_data(live, test)
    assert result.is_match
    sheet = result.sheets[0]
    assert "misc_charges" in sheet.ignored_extra_in_test


def test_flags_missing_rows_with_date_pattern(tmp_path: Path):
    live = tmp_path / "live.xlsx"
    test = tmp_path / "test.xlsx"
    _xlsx(live, {
        "Invoices": [
            ["InvoiceNumber", "InvoiceDate", "Total Invoice"],
            ["IN1", date(2026, 7, 1), 100],
            ["IN2", date(2026, 7, 1), 200],
            ["IN3", date(2026, 7, 1), 300],
            ["IN4", date(2026, 6, 15), 50],
        ],
    })
    _xlsx(test, {
        "Invoices": [
            ["InvoiceNumber", "InvoiceDate", "Total Invoice"],
            ["IN4", date(2026, 6, 15), 50],
        ],
    })
    result = compare_workbooks_data(live, test)
    assert not result.is_match
    sheet = result.sheets[0]
    assert sheet.missing_in_test_count == 3
    joined = " ".join(sheet.patterns)
    assert "2026-07-01" in joined


def test_soft_name_format_does_not_fail(tmp_path: Path):
    live = tmp_path / "live.xlsx"
    test = tmp_path / "test.xlsx"
    _xlsx(live, {
        "Summary": [
            ["CustomerAccount", "SalesmanName", "Total Invoices"],
            ["100", "Meir Grego", 10],
        ],
    })
    _xlsx(test, {
        "Summary": [
            ["CustomerAccount", "SalesmanName", "Total Invoices"],
            ["100", "Grego, Meir", 10],
        ],
    })
    assert compare_workbooks_data(live, test).is_match


def test_cust_hash_header_maps_to_customer_account():
    from tools.parity.data_compare import _canon_header

    assert _canon_header("Cust. #") == "customer_account"
    assert _canon_header("Cust #") == "customer_account"


def test_numeric_diff_explained_by_column(tmp_path: Path):
    live = tmp_path / "live.xlsx"
    test = tmp_path / "test.xlsx"
    _xlsx(live, {
        "By Order": [
            ["SalesOrderNumber", "Ordered $"],
            ["ORD1", 100],
            ["ORD2", 200],
        ],
    })
    _xlsx(test, {
        "By Order": [
            ["SalesOrderNumber", "Ordered $"],
            ["ORD1", 100],
            ["ORD2", 250],
        ],
    })
    result = compare_workbooks_data(live, test)
    assert not result.is_match
    assert result.sheets[0].value_diff_count == 1
    assert "ordered_dollars" in " ".join(result.sheets[0].patterns)


def test_compare_and_write_diff_report(tmp_path: Path):
    live = tmp_path / "live.xlsx"
    test = tmp_path / "test.xlsx"
    _xlsx(live, {"Summary": [["CustomerAccount", "Total"], ["A", 10], ["B", 20]]})
    _xlsx(test, {"Summary": [["CustomerAccount", "Total"], ["A", 10], ["B", 21]]})

    comparison = compare_pair(live, test, tolerance=0.01)
    assert not comparison.is_match
    assert comparison.total_diffs >= 1

    detail = tmp_path / "ordered.md"
    write_report(
        detail,
        report_key="ordered",
        params={"period": "last_month"},
        live_path=live,
        test_path=test,
        comparison=comparison,
    )
    text = detail.read_text(encoding="utf-8")
    assert "DIFFERENCES FOUND" in text
    assert "ordered" in text

    index = write_index(tmp_path, [{
        "report": "ordered", "status": "DIFF", "diffs": comparison.total_diffs,
        "detail": "ordered.md",
    }])
    assert index.exists()
    assert "DIFF" in index.read_text(encoding="utf-8")


def test_compare_match(tmp_path: Path):
    live = tmp_path / "live.xlsx"
    test = tmp_path / "test.xlsx"
    rows = [["CustomerAccount", "Total"], ["X", 1], ["Y", 2]]
    _xlsx(live, {"Data": rows})
    _xlsx(test, {"Data": rows})
    assert compare_pair(live, test).is_match


def test_live_download_prefers_salesman_master():
    from tools.parity.clients import (
        _candidates_from_history_html,
        _candidates_from_result,
        _live_download_target,
    )

    cands = _candidates_from_result({
        "filename": "MKolko Jun 2026.xlsx",
        "extra_files": [
            {"filename": "HKaufman Jun 2026.xlsx"},
            {"filename": "Monthly Salesmen Report Jun 2026.xlsx"},
        ],
    })
    mode, idx, name = _live_download_target("salesman", cands)
    assert mode == "extra"
    assert idx == 1
    assert "Monthly Salesmen Report" in name

    cands = _candidates_from_result({
        "filename": "Monthly Salesmen Report Jun 2026.xlsx",
        "extra_files": [{"filename": "MKolko Jun 2026.xlsx"}],
    })
    mode, idx, _ = _live_download_target("salesman", cands)
    assert (mode, idx) == ("primary", None)

    html = """
    <a href="/history/download/abc123" title="MKolko Jun 2026.xlsx">Download</a>
    <a href="/history/download-extra/abc123/0" title="HKaufman Jun 2026.xlsx">x</a>
    <a href="/history/download-extra/abc123/4" title="Monthly Salesmen Report Jun 2026.xlsx">y</a>
    """
    cands = _candidates_from_history_html(html, "abc123")
    mode, idx, name = _live_download_target("salesman", cands)
    assert (mode, idx) == ("extra", 4)
    assert "Monthly Salesmen Report" in name
