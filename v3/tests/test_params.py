"""web.reporting.params: report-id map + SP param translation."""

import pytest

from report_engine.dates import today_eastern
from web.reporting import params as P


def test_report_id_map_is_complete():
    assert P.report_id_for("ordered") == "ordered_report"
    assert P.report_id_for("invoiced") == "invoiced_report"
    assert P.report_id_for("salesman") == "invoiced_order_charges"
    assert P.report_id_for("number_4") == "customer_item_sales_rolling_12"
    assert P.report_id_for("customer_activity") == "salesline_release"


def test_unknown_report_raises():
    with pytest.raises(KeyError):
        P.translate("nope", {})


def test_ordered_single_customer_and_filters():
    out = P.translate("ordered", {
        "period": "custom", "start_date": "2026-04-01", "end_date": "2026-04-30",
        "customers": ["100001"], "salesman": "REdwards",
        "status": "Open", "item": "ABC", "order_no": "SO-1",
    })
    assert out["CreatedDateTimeFrom"] == "2026-04-01 00:00:00"
    assert out["CreatedDateTimeTo"] == "2026-04-30 23:59:59"
    assert out["CustomerAccount"] == "100001"
    assert out["SalesGroup"] == "REdwards"
    assert out["SalesStatus"] == "Open"
    assert out["Item"] == "ABC"
    assert out["SalesOrderNumber"] == "SO-1"


def test_ordered_multi_customer_is_not_pushed_down():
    # The new SP's CustomerAccount is exact-match, so a multi-select isn't pushed
    # to the SP (the orchestrator post-filters it instead).
    out = P.translate("ordered", {"period": "all_time", "customers": ["100001", "100002"]})
    assert "CustomerAccount" not in out


def test_ordered_drops_unsupported_company_and_shipped_qty():
    # The new SP has no Company param and no shipped-quantity filter.
    out = P.translate("ordered", {
        "period": "all_time", "company": "ACHM",
        "shipped_qty_min": "1", "shipped_qty_max": "9",
    })
    assert "Company" not in out
    assert "shippedquantitymin" not in out
    assert "shippedquantitymax" not in out


def test_ordered_all_time_omits_dates():
    out = P.translate("ordered", {"period": "all_time"})
    assert "CreatedDateTimeFrom" not in out
    assert "CreatedDateTimeTo" not in out


def test_blank_period_with_dates_still_omits_dates():
    # A named period is required to bound dates (matches the test-app contract).
    out = P.translate("ordered", {"period": "", "start_date": "2026-04-01",
                                  "end_date": "2026-04-30"})
    assert "CreatedDateTimeFrom" not in out
    assert "CreatedDateTimeTo" not in out


def test_custom_with_invalid_dates_omits_rather_than_raises():
    out = P.translate("ordered", {"period": "custom", "start_date": "not-a-date",
                                  "end_date": "also-bad"})
    assert "CreatedDateTimeFrom" not in out
    assert "CreatedDateTimeTo" not in out


def test_invoiced_single_customer_pushes_invoiceaccount():
    out = P.translate("invoiced", {"period": "mtd", "customers": ["100001"]})
    assert out["CustomerAccount"] == "100001"
    assert "InvoiceAccount" not in out


def test_invoiced_multi_customer_omits_invoiceaccount():
    # Multi-select can't go to the single-value SP param; caller post-filters.
    out = P.translate("invoiced", {"period": "mtd", "customers": ["100001", "100002"]})
    assert "CustomerAccount" not in out


def test_salesman_spans_prior_and_current_year():
    out = P.translate("salesman", {"year": "2026"})
    assert out["InvoiceDateFrom"] == "2025-01-01 00:00:00"
    assert out["InvoiceDateTo"] == "2026-12-31 23:59:59"


def test_salesman_defaults_to_current_year():
    out = P.translate("salesman", {})
    y = today_eastern().year
    assert out["InvoiceDateFrom"].startswith(f"{y - 1}-01-01")
    assert out["InvoiceDateTo"].startswith(f"{y}-12-31")


def test_number_4_sends_as_of_today_including_current_month():
    out = P.translate("number_4", {})
    assert out["AsOfDate"] == today_eastern().isoformat()
    assert out["IncludeCurrentMonth"] is True


def test_number_4_mode_defaults_to_both_and_rejects_junk():
    assert P.number_4_mode({}) == "both"
    assert P.number_4_mode({"mode": "by_item"}) == "by_item"
    assert P.number_4_mode({"mode": "By_Customer"}) == "by_customer"
    assert P.number_4_mode({"mode": "banana"}) == "both"


def test_customer_activity_is_all_time():
    out = P.translate("customer_activity", {})
    assert out["CreatedDateTimeFrom"].startswith("2025-01-03")
