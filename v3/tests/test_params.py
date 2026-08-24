"""web.reporting.params: report-id map + SP param translation."""

import pytest

from report_engine.dates import today_eastern
from web.reporting import params as P


def test_report_id_map_is_complete():
    assert P.report_id_for("ordered") == "ordered_report"
    assert P.report_id_for("invoiced") == "invoiced_report"
    assert P.report_id_for("salesman") == "monthly_salesman_yoy"
    assert P.report_id_for("number_4") == "customer_item_sales_rolling_12"
    assert P.report_id_for("customer_activity") == "customer_activity"
    assert P.report_id_for("customer_last_order") == "customer_last_orders"
    assert P.report_id_for("sales_by_state") == "sales_by_state_summary"
    assert P.SALES_BY_STATE_DETAIL_SP == "sales_by_state_filtered"


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


def test_invoiced_same_day_window_uses_end_of_day():
    """A one-day period (Daily / yesterday) must not send From=To at midnight.

    SQL datetime params with no time collapse to an empty window, so the
    scheduled Daily Invoiced workbook arrives with sheets and no rows.
    """
    out = P.translate("invoiced", {
        "period": "custom", "start_date": "2026-08-16", "end_date": "2026-08-16",
    })
    assert out["InvoiceDateFrom"] == "2026-08-16 00:00:00"
    assert out["InvoiceDateTo"] == "2026-08-16 23:59:59"
    daily = P.translate("invoiced", {"period": "daily"})
    yesterday = P.translate("invoiced", {"period": "yesterday"})
    assert daily == yesterday
    assert daily["InvoiceDateFrom"].endswith("00:00:00")
    assert daily["InvoiceDateTo"].endswith("23:59:59")
    assert daily["InvoiceDateFrom"][:10] == daily["InvoiceDateTo"][:10]


def test_invoiced_single_customer_pushes_invoiceaccount():
    out = P.translate("invoiced", {"period": "mtd", "customers": ["100001"]})
    assert out["CustomerAccount"] == "100001"
    assert "InvoiceAccount" not in out


def test_invoiced_multi_customer_omits_invoiceaccount():
    # Multi-select can't go to the single-value SP param; caller post-filters.
    out = P.translate("invoiced", {"period": "mtd", "customers": ["100001", "100002"]})
    assert "CustomerAccount" not in out


def test_salesman_uses_yoy_sp_params():
    out = P.translate("salesman", {"year": "2026", "through_month": 5})
    assert out["ReportYear"] == 2026
    assert out["ThroughMonth"] == 5
    assert "InvoiceDateFrom" not in out


def test_salesman_defaults_through_month_for_current_year():
    out = P.translate("salesman", {})
    y = today_eastern().year
    assert out["ReportYear"] == y
    assert 1 <= out["ThroughMonth"] <= 12
    if out["ReportYear"] == y:
        assert out["ThroughMonth"] == today_eastern().month


def test_number_4_sends_as_of_today_including_current_month():
    out = P.translate("number_4", {})
    assert out["AsOfDate"] == today_eastern().isoformat()
    assert out["IncludeCurrentMonth"] is True


def test_number_4_mode_defaults_to_both_and_rejects_junk():
    assert P.number_4_mode({}) == "both"
    assert P.number_4_mode({"mode": "by_item"}) == "by_item"
    assert P.number_4_mode({"mode": "By_Customer"}) == "by_customer"
    assert P.number_4_mode({"mode": "banana"}) == "both"


def test_customer_activity_maps_to_dedicated_sp():
    assert P.report_id_for("customer_activity") == "customer_activity"
    out = P.translate("customer_activity", {})
    assert out == {"OrderCount": 1}
    out2 = P.translate("customer_activity", {"order_count": 5, "salesman": "MKolko"})
    assert out2["OrderCount"] == 5
    assert out2["Salesman"] == "MKolko"


def test_customer_last_orders_maps_account_and_default_count():
    out = P.translate("customer_last_order", {"customer_account": "9017"})
    assert out == {"CustomerAccount": "9017", "OrderCount": 10}
    out2 = P.translate("customer_last_order", {
        "customer_account": "9017", "order_count": 3, "as_of_date": "2026-04-01",
    })
    assert out2["OrderCount"] == 3
    assert out2["AsOfDate"] == "2026-04-01"


def test_sales_by_state_year_becomes_from_to_dates():
    out = P.translate("sales_by_state", {"year": "2025"})
    assert out == {"FromDate": "2025-01-01", "ToDate": "2025-12-31"}
    custom = P.translate("sales_by_state", {
        "period": "custom", "start_date": "2025-03-01", "end_date": "2025-03-31",
    })
    assert custom["FromDate"] == "2025-03-01"
    assert custom["ToDate"] == "2025-03-31"
    with_co = P.translate("sales_by_state", {"year": 2025, "Company": "achm"})
    assert with_co["Company"] == "achm"
