"""Customer Transaction Detail: keep settlement duplicates; SQL-only catalog."""

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
