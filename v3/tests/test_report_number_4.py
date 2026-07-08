"""Number 4 builder: dynamic-column typing, row cleaning, scope, tab shape.

The rolling-12 SPs return the finished pivot (a Qty and $ column per month),
so the builder is a passthrough: it types the columns from their headers and
keeps the SP's column order. Month names must never be hard-coded (handoff
rule) -- these tests use made-up month labels on purpose.
"""

from report_engine.reports import number_4 as B


def _row(**overrides):
    row = {"Customer #": "100", "Customer Name": "Acme",
           "Item #": "ITM-A", "Item Name": "Widget",
           "Jul-25 Qty": "2", "Jul-25 $": "20", "Jun-26 Qty": "1", "Jun-26 $": "10.5",
           "Total Qty": "3", "Total $": "30.5", "Avg Price": "10.1667",
           "Salesman": "REdwards", "Book Price": "12.50"}
    row.update(overrides)
    return row


def test_month_columns_typed_by_suffix_not_by_name():
    columns = B.columns_for(["Customer #", "Zzz-99 Qty", "Zzz-99 $", "Total Qty",
                             "Total $", "Avg Price", "Salesman", "Book Price"])
    types = {c["field"]: c["type"] for c in columns}
    assert types["Zzz-99 Qty"] == "int"
    assert types["Zzz-99 $"] == "money"
    assert types["Total Qty"] == "int"
    assert types["Total $"] == "money"
    assert types["Avg Price"] == "money"
    assert types["Book Price"] == "money"
    assert types["Customer #"] == "text"
    assert types["Salesman"] == "text"


def test_columns_keep_the_sps_own_order():
    headers = ["Item #", "Item Name", "Customer #", "Customer Name",
               "Jul-25 Qty", "Jul-25 $", "Total Qty", "Total $",
               "Avg Price", "Salesman", "Book Price"]
    tab = B.build(by_item=(headers, B.clean_rows([{h: "" for h in headers}])))[0]
    assert [c["field"] for c in tab["columns"]] == headers


def test_clean_rows_coerces_string_numbers_and_keeps_text():
    cleaned = B.clean_rows([_row()])
    row = cleaned[0]
    assert row["Jul-25 Qty"] == 2.0
    assert row["Jun-26 $"] == 10.50
    assert row["Total $"] == 30.5
    assert row["Avg Price"] == 10.17  # money rounds to cents
    assert row["Customer #"] == "100"
    assert row["Salesman"] == "REdwards"


def _view(rows):
    headers = list(rows[0].keys()) if rows else list(_row().keys())
    return (headers, rows)


def test_both_views_build_two_tabs_in_order():
    tabs = B.build(by_customer=_view([_row()]), by_item=_view([_row()]))
    assert [(t["key"], t["name"]) for t in tabs] == [
        ("by_customer", "By Customer"), ("by_item", "By Item")]


def test_missing_view_means_no_tab():
    assert [t["key"] for t in B.build(by_customer=_view([_row()]))] == ["by_customer"]
    assert [t["key"] for t in B.build(by_item=_view([_row()]))] == ["by_item"]
    assert B.build() == []


def test_empty_view_keeps_its_headers():
    # Zero rows (or a fully scope-filtered run) still shows the column headers,
    # because they come from the API's column list, not from the rows.
    tabs = B.build(by_customer=_view([]))
    assert tabs[0]["rows"] == []
    assert [c["field"] for c in tabs[0]["columns"]] == list(_row().keys())


def test_scope_filter_matches_salesman_case_insensitively():
    rows = [_row(), _row(**{"Customer #": "200", "Salesman": "JSmith"})]
    mine = B.filter_rows_by_salesman(rows, {"REDWARDS"})
    assert [r["Customer #"] for r in mine] == ["100"]
    assert B.filter_rows_by_salesman(rows, None) == rows       # unrestricted
    assert B.filter_rows_by_salesman(rows, set()) == []        # no access
