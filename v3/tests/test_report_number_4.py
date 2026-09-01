"""Number 4 builder: dynamic-column typing, YTD slice, By Item money strip.

The rolling-12 SPs return the finished pivot (a Qty and $ column per month).
YTD is that same pivot with prior-year months dropped. By Item drops money.
"""

from datetime import date

from report_engine.reports import number_4 as B


def _row(**overrides):
    row = {"Customer #": "100", "Customer Name": "Acme",
           "Item #": "ITM-A", "Item Name": "Widget",
           "Dec-25 Qty": "4", "Dec-25 $": "40",
           "Jul-25 Qty": "2", "Jul-25 $": "20",
           "Jun-26 Qty": "1", "Jun-26 $": "10.5",
           "Total Qty": "7", "Total $": "70.5", "Avg Price": "10.0714",
           "Book Price": "12.50", "Salesman": "REdwards"}
    row.update(overrides)
    return row


AS_OF = date(2026, 8, 25)


def test_month_columns_typed_by_suffix_not_by_name():
    columns = B.columns_for(["Customer #", "Zzz-99 Qty", "Zzz-99 $", "Total Qty",
                             "Total $", "Avg Price", "Book Price", "Salesman"])
    types = {c["field"]: c["type"] for c in columns}
    assert types["Zzz-99 Qty"] == "int"
    assert types["Zzz-99 $"] == "money"
    assert types["Total Qty"] == "int"
    assert types["Total $"] == "money"
    assert types["Avg Price"] == "money"
    assert types["Book Price"] == "money"
    assert types["Customer #"] == "text"
    assert types["Salesman"] == "text"


def test_parse_month_header_ignores_totals():
    assert B.parse_month_header("Jul-25 Qty") == (2025, 7)
    assert B.parse_month_header("Jun-26 $") == (2026, 6)
    assert B.parse_month_header("2025-12 Qty") == (2025, 12)
    assert B.parse_month_header("Total Qty") is None
    assert B.parse_month_header("Total $") is None
    assert B.parse_month_header("Avg Price") is None
    assert B.parse_month_header("Book Price") is None


def test_columns_keep_the_sps_own_order_minus_money_on_by_item():
    headers = ["Item #", "Item Name", "Customer #", "Customer Name",
               "Jul-25 Qty", "Jul-25 $", "Total Qty", "Total $",
               "Avg Price", "Book Price", "Salesman"]
    tab = B.build(by_item=(headers, B.clean_rows([{h: "" for h in headers}])),
                  as_of=AS_OF)[0]
    assert [c["field"] for c in tab["columns"]] == [
        "Item #", "Item Name", "Customer #", "Customer Name",
        "Jul-25 Qty", "Total Qty", "Salesman"]


def test_clean_rows_coerces_string_numbers_and_keeps_text():
    cleaned = B.clean_rows([_row()])
    row = cleaned[0]
    assert row["Jul-25 Qty"] == 2.0
    assert row["Jun-26 $"] == 10.50
    assert row["Total $"] == 70.5
    assert row["Avg Price"] == 10.07  # money rounds to cents
    assert row["Customer #"] == "100"
    assert row["Salesman"] == "REdwards"


def _view(rows):
    headers = list(rows[0].keys()) if rows else list(_row().keys())
    return (headers, rows)


def test_both_views_build_four_tabs_in_order():
    tabs = B.build(by_customer=_view([_row()]), by_item=_view([_row()]), as_of=AS_OF)
    assert [(t["key"], t["name"]) for t in tabs] == [
        ("by_customer", "By Customer (12 Months)"),
        ("by_customer_ytd", "By Customer (YTD)"),
        ("by_item", "By Item (12 Months)"),
        ("by_item_ytd", "By Item (YTD)"),
    ]


def test_missing_view_means_no_tabs_for_that_version():
    assert [t["key"] for t in B.build(by_customer=_view([_row()]), as_of=AS_OF)] == [
        "by_customer", "by_customer_ytd"]
    assert [t["key"] for t in B.build(by_item=_view([_row()]), as_of=AS_OF)] == [
        "by_item", "by_item_ytd"]
    assert B.build(as_of=AS_OF) == []


def test_empty_view_keeps_its_headers():
    # Zero rows (or a fully scope-filtered run) still shows the column headers,
    # because they come from the API's column list, not from the rows.
    tabs = B.build(by_customer=_view([]), as_of=AS_OF)
    assert tabs[0]["rows"] == []
    assert [c["field"] for c in tabs[0]["columns"]] == list(_row().keys())


def test_by_item_tabs_have_no_money():
    tabs = B.build(by_item=_view([_row()]), as_of=AS_OF)
    for tab in tabs:
        fields = [c["field"] for c in tab["columns"]]
        assert all(c["type"] != "money" for c in tab["columns"])
        assert "Total $" not in fields
        assert "Avg Price" not in fields
        assert "Book Price" not in fields
        assert not any(f.endswith("$") for f in fields)
        assert "Total Qty" in fields
        assert "Jun-26 Qty" in fields


def test_by_customer_puts_avg_and_book_price_before_salesman():
    tab = B.build(by_customer=_view([_row()]), as_of=AS_OF)[0]
    fields = [c["field"] for c in tab["columns"]]
    assert fields[-3:] == ["Avg Price", "Book Price", "Salesman"]
    assert fields.index("Avg Price") < fields.index("Book Price") < fields.index("Salesman")


def test_aliased_and_missing_prices_are_added_before_salesman():
    headers = ["Customer #", "Item #", "Total Qty", "Total $", "AvgPrice", "Salesman"]
    row = {"Customer #": "100", "Item #": "A", "Total Qty": "2", "Total $": "10",
           "AvgPrice": "", "Salesman": "S"}
    tab = B.build(by_customer=(headers, [row]), as_of=AS_OF)[0]
    fields = [c["field"] for c in tab["columns"]]
    assert fields[-3:] == ["Avg Price", "Book Price", "Salesman"]
    assert tab["rows"][0]["Avg Price"] == 5.0
    assert "Book Price" in tab["rows"][0]


def test_by_customer_keeps_money():
    tab = B.build(by_customer=_view([_row()]), as_of=AS_OF)[0]
    fields = [c["field"] for c in tab["columns"]]
    assert "Jun-26 $" in fields
    assert "Total $" in fields
    assert "Avg Price" in fields
    assert "Book Price" in fields


def test_ytd_drops_prior_year_months_and_recalcs_totals():
    tab = B.build(by_customer=_view([_row()]), as_of=AS_OF)[1]
    fields = [c["field"] for c in tab["columns"]]
    assert "Jun-26 Qty" in fields
    assert "Jun-26 $" in fields
    assert "Dec-25 Qty" not in fields
    assert "Jul-25 Qty" not in fields
    row = tab["rows"][0]
    assert row["Total Qty"] == 1.0
    assert row["Total $"] == 10.5
    assert row["Avg Price"] == 10.5


def test_ytd_drops_rows_with_no_current_year_activity():
    prior_only = _row(**{"Jun-26 Qty": 0, "Jun-26 $": 0,
                         "Total Qty": 6, "Total $": 60})
    tab = B.build(by_customer=_view([prior_only]), as_of=AS_OF)[1]
    assert tab["rows"] == []


def test_tabs_group_by_item_by_default():
    tabs = B.build(by_customer=_view([_row()]), by_item=_view([_row()]), as_of=AS_OF)
    for tab in tabs:
        assert tab["default_group"] == ["Item #"]


def test_scope_filter_matches_salesman_case_insensitively():
    rows = [_row(), _row(**{"Customer #": "200", "Salesman": "JSmith"})]
    mine = B.filter_rows_by_salesman(rows, {"REDWARDS"})
    assert [r["Customer #"] for r in mine] == ["100"]
    assert B.filter_rows_by_salesman(rows, None) == rows       # unrestricted
    assert B.filter_rows_by_salesman(rows, set()) == []        # no access
