"""Customer Transaction Detail: keep settlement duplicates; SQL-only catalog."""

import io

import pytest

from report_engine.registry import ReportStatus, get
from report_engine.reports import customer_transaction_detail as rpt
from web.beta_sources import _ALL_KEYS, default_sources, get_source


def test_keeps_two_settlements_for_one_original():
    rows = rpt.clean_rows([
        {"RecId": "111", "AccountNum": "9017", "Invoice": "IN1",
         "AmountMST": 100, "OffsetRecId": "A"},
        {"RecId": "111", "AccountNum": "9017", "Invoice": "IN1",
         "AmountMST": 100, "OffsetRecId": "B"},
    ])
    tabs = rpt.build(rows)
    assert tabs[0]["name"] == "Transactions"
    assert len(tabs[0]["rows"]) == 2
    assert [r["OffsetRecId"] for r in tabs[0]["rows"]] == ["A", "B"]
    assert tabs[0]["rows"][0]["AmountMST"] == 100.0
    by_field = {c["field"]: c for c in tabs[0]["columns"]}
    assert by_field["AmountMST"]["sum"] is False
    assert by_field["RemainAmountCur"]["sum"] is False
    assert by_field["SettleAmountCur"].get("sum") is not False
    assert by_field["OffsetAmountMST"].get("sum") is not False
    assert by_field["CreatedDateTime"]["type"] == "text"
    assert by_field["OffsetCreatedDateTime"]["type"] == "text"


def test_created_dates_convert_gmt_to_eastern_with_time():
    rows = rpt.clean_rows([
        {
            "RecId": "111",
            "CreatedDateTime": "Tue, 15 Sep 2026 16:21:16 GMT",
            "OffsetCreatedDateTime": "Tue, 15 Sep 2026 16:21:16 GMT",
        },
    ])
    assert rows[0]["CreatedDateTime"] == "2026-09-15 12:21:16"
    assert rows[0]["OffsetCreatedDateTime"] == "2026-09-15 12:21:16"


def test_export_does_not_sum_repeated_original_amounts():
    openpyxl = pytest.importorskip("openpyxl")
    from web.reporting.export import build_workbook

    rows = rpt.clean_rows([
        {"RecId": "111", "AccountNum": "9017", "Invoice": "IN1",
         "AmountMST": 100, "RemainAmountCur": 40, "SettleAmountCur": 60,
         "OffsetAmountMST": 60, "OffsetRecId": "A"},
        {"RecId": "111", "AccountNum": "9017", "Invoice": "IN1",
         "AmountMST": 100, "RemainAmountCur": 40, "SettleAmountCur": 40,
         "OffsetAmountMST": 40, "OffsetRecId": "B"},
    ])
    payload = {"tabs": rpt.build(rows)}
    wb = openpyxl.load_workbook(io.BytesIO(build_workbook(payload, {})))
    sheet = wb["Transactions"]
    total = next(row for row in sheet.iter_rows() if row[0].value == "Total")
    fields = [c["field"] for c in payload["tabs"][0]["columns"]]
    amount_i = fields.index("AmountMST")
    remain_i = fields.index("RemainAmountCur")
    settle_i = fields.index("SettleAmountCur")
    offset_i = fields.index("OffsetAmountMST")
    assert total[amount_i].value is None
    assert total[remain_i].value is None
    assert total[settle_i].value == 100
    assert total[offset_i].value == 100


def test_registry_sql_only_not_a_salesman_default():
    spec = get("customer_transaction_detail")
    assert spec is not None
    assert spec.status is ReportStatus.BUILT
    assert spec.salesman_default is False
    assert spec.privileged_only is False
    assert spec.title == "Customer Transaction Detail"
    assert "customer_transaction_detail" not in _ALL_KEYS
    assert "customer_transaction_detail" not in default_sources()
    assert get_source("customer_transaction_detail") == "sql"
