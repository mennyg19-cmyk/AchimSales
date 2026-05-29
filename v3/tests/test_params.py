"""web.reporting.params: report-id map + SP param translation."""

from datetime import date

import pytest

from report_engine.dates import today_eastern
from web.reporting import params as P


def test_report_id_map_is_complete():
    assert P.report_id_for("ordered") == "salesline_release"
    assert P.report_id_for("invoiced") == "invoiced_order_charges"
    assert P.report_id_for("salesman") == "invoiced_order_charges"
    assert P.report_id_for("number_4") == "invoice_lines"
    assert P.report_id_for("customer_activity") == "salesline_release"


def test_unknown_report_raises():
    with pytest.raises(KeyError):
        P.translate("nope", {})


def test_ordered_custom_range_and_filters():
    out = P.translate("ordered", {
        "period": "custom", "start_date": "2026-04-01", "end_date": "2026-04-30",
        "customers": ["100001", "100002"], "salesman": "REdwards",
        "status": "Open", "item": "ABC", "order_no": "SO-1", "company": "ACHM",
    })
    assert out["CreatedDateTimeFrom"] == "2026-04-01 00:00:00"
    assert out["CreatedDateTimeTo"] == "2026-04-30 23:59:59"
    assert out["CustomerAccount"] == "100001,100002"
    assert out["SalesGroup"] == "REdwards"
    assert out["SalesStatus"] == "Open"
    assert out["Item"] == "ABC"
    assert out["SalesOrderNumber"] == "SO-1"
    assert out["Company"] == "ACHM"


def test_ordered_all_time_omits_dates():
    out = P.translate("ordered", {"period": "all_time"})
    assert "CreatedDateTimeFrom" not in out
    assert "CreatedDateTimeTo" not in out


def test_invoiced_single_customer_pushes_invoiceaccount():
    out = P.translate("invoiced", {"period": "mtd", "customers": ["100001"]})
    assert out["InvoiceAccount"] == "100001"


def test_invoiced_multi_customer_omits_invoiceaccount():
    # Multi-select can't go to the single-value SP param; caller post-filters.
    out = P.translate("invoiced", {"period": "mtd", "customers": ["100001", "100002"]})
    assert "InvoiceAccount" not in out


def test_salesman_spans_prior_and_current_year():
    out = P.translate("salesman", {"year": "2026"})
    assert out["InvoiceDateFrom"] == "2025-01-01 00:00:00"
    assert out["InvoiceDateTo"] == "2026-12-31 23:59:59"


def test_salesman_defaults_to_current_year():
    out = P.translate("salesman", {})
    y = today_eastern().year
    assert out["InvoiceDateFrom"].startswith(f"{y - 1}-01-01")
    assert out["InvoiceDateTo"].startswith(f"{y}-12-31")


def test_number_4_is_rolling_13_months():
    out = P.translate("number_4", {})
    today = today_eastern()
    expected_start = date(today.year - 1, today.month, 1)
    assert out["InvoiceDateFrom"].startswith(expected_start.isoformat())
    assert out["InvoiceDateTo"].startswith(today.isoformat())


def test_customer_activity_is_all_time():
    out = P.translate("customer_activity", {})
    assert out["CreatedDateTimeFrom"].startswith("2025-01-03")
