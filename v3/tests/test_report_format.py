"""Explorer report-format catalog: tabs and columns without running a report."""

from report_engine.registry import built_reports
from web.reporting.report_format import apply_format, tabs_for


def test_ordered_tabs_include_every_sheet():
    tabs = tabs_for("ordered")
    assert [t["key"] for t in tabs] == [
        "summary", "by_customer", "by_item", "by_order", "by_salesman", "full_data",
    ]
    summary = next(t for t in tabs if t["key"] == "summary")
    assert any(c["field"] == "Customer Name" for c in summary["columns"])


def test_every_built_report_has_columns():
    for spec in built_reports():
        tabs = tabs_for(spec.key)
        assert tabs, spec.key
        assert tabs[0]["columns"], spec.key


def test_apply_format_omits_group_until_set():
    layout = apply_format(
        {"views": {"by_order": {"hidden": ["LineNumber"]}}},
        [{
            "key": "by_order", "set_group": False, "group": [],
            "sorters": [{"column": "OrderDate", "dir": "desc"}],
            "filters": [{"column": "Status", "op": "contains", "v": "Open", "v2": ""}],
        }],
    )
    tab = layout["views"]["by_order"]
    assert "group" not in tab
    assert tab["hidden"] == ["LineNumber"]
    assert tab["sorters"] == [{"column": "OrderDate", "dir": "desc"}]
    assert tab["columnFilters"]["Status"]["v"] == "Open"


def test_apply_format_empty_group_is_ungroup():
    layout = apply_format({}, [{
        "key": "by_order", "set_group": True, "group": [],
        "sorters": [], "filters": [],
    }])
    assert layout["views"]["by_order"]["group"] == []
