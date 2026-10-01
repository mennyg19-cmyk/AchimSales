"""Explorer report-format catalog: tabs and columns without running a report."""

from web.data.connection import Database
from web.data.migrate import migrate
from web.reporting.report_catalog import read_catalog, remember_catalog
from web.reporting.report_format import apply_format, tabs_for
from report_engine.registry import built_reports


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


def test_apply_format_saves_hidden_columns_and_tab_visibility():
    layout = apply_format(
        {"views": {"summary": {"hidden": ["Open$"]}}},
        [
            {"key": "summary", "show_tab": True, "hidden": ["Customer Name"], "set_group": False, "sorters": [], "filters": []},
            {"key": "by_item", "show_tab": False, "hidden": [], "set_group": False, "sorters": [], "filters": []},
        ],
    )
    assert layout["order"] == ["summary"]
    assert layout["views"]["summary"]["hidden"] == ["Customer Name"]


def test_catalog_from_a_run_replaces_that_tabs_columns(tmp_path):
    db = Database(tmp_path / "precious.db", tmp_path / "cache.db")
    migrate(db)
    remember_catalog(db, "ordered", {"tabs": [
        {"key": "summary", "name": "Summary", "columns": [{"field": "LiveCol", "header": "Live Col"}]},
    ]})
    remember_catalog(db, "ordered", {"tabs": [
        {"key": "by_item", "name": "By Item", "columns": []},
    ]})
    stored = read_catalog(db, "ordered")
    by_key = {tab["key"]: tab for tab in stored}
    assert set(by_key) == {"summary", "by_item"}
    assert by_key["summary"]["columns"] == [{"field": "LiveCol", "header": "Live Col"}]
    assert by_key["by_item"]["columns"] == []
    assert {tab["key"] for tab in tabs_for("ordered", db)} == {"summary", "by_item"}


def test_column_order_is_the_on_report_field_order():
    layout = apply_format(
        {"views": {"summary": {"hidden": ["Open$"]}}},
        [{
            "key": "summary",
            "hidden": ["Open$"],
            "column_order": ["Customer Name", "Open$", "CustomerAccount"],
            "set_group": False,
            "sorters": [],
            "filters": [],
        }],
    )
    summary = layout["views"]["summary"]
    assert summary["order"] == ["Customer Name", "Open$", "CustomerAccount"]
    assert summary["hidden"] == ["Open$"]


def test_apply_format_empty_group_is_ungroup():
    layout = apply_format({}, [{
        "key": "by_order", "set_group": True, "group": [],
        "sorters": [], "filters": [],
    }])
    assert layout["views"]["by_order"]["group"] == []
