"""Number 4 OData bridge helpers: extra files, tab names, item grouping."""

from web.reporting.odata_bridge import (
    _attach_number4_defaults,
    _extra_file_paths,
    _is_summary_row,
    _number4_version_label,
    _slug,
)


def test_extra_file_paths_accepts_dicts_and_strings():
    assert _extra_file_paths([
        {"filepath": "/tmp/a.xlsx", "filename": "a.xlsx"},
        "/tmp/b.xlsx",
        {"path": "/tmp/c.xlsx"},
        {},
        None,
    ]) == ["/tmp/a.xlsx", "/tmp/b.xlsx", "/tmp/c.xlsx"]


def test_number4_filename_picks_item_before_customer():
    assert _number4_version_label("Number_4_Report_Item_2026-08-25.xlsx") == "By Item"
    assert _number4_version_label("Number_4_Report_Customer_2026-08-25.xlsx") == "By Customer"
    assert _number4_version_label("other.xlsx") == ""


def test_number4_prefixed_keys_do_not_collide():
    item_key = _slug("By Item (12 Months)")
    cust_key = _slug("By Customer (12 Months)")
    assert item_key != cust_key
    assert item_key == "by_item_12_months"
    assert cust_key == "by_customer_12_months"


def test_summary_rows_are_detected():
    assert _is_summary_row({"Item #": "TOTALS:", "Total Qty": 3})
    assert _is_summary_row({"Item #": "GRAND TOTALS:", "Total Qty": 9})
    assert not _is_summary_row({"Item #": "ITM-A", "Total Qty": 3})


def test_number4_defaults_group_by_item_and_drop_totals():
    tab = _attach_number4_defaults({
        "key": "by_item_12_months",
        "name": "By Item (12 Months)",
        "columns": ["Item #", "Total Qty"],
        "rows": [
            {"Item #": "ITM-A", "Total Qty": 2},
            {"Item #": "TOTALS:", "Total Qty": 2},
            {"Item #": "GRAND TOTALS:", "Total Qty": 2},
        ],
    })
    assert tab["default_group"] == ["Item #"]
    assert [r["Item #"] for r in tab["rows"]] == ["ITM-A"]
