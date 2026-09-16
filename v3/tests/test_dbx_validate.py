"""Explorer JSON/SQL checks: missing group is not ungroup."""

from web.dbx_validate import json_assignments_in_sql, layout_errors, validate_column_value


def test_layout_missing_group_is_rejected():
    errs = layout_errors({"views": {"by_order": {"hidden": []}}})
    assert errs
    assert "missing group" in errs[0]
    assert "[]" in errs[0]


def test_layout_empty_group_is_ungroup():
    assert layout_errors({"views": {"by_order": {"group": []}}}) == []


def test_layout_groups_typo_is_rejected():
    errs = layout_errors({"views": {"by_order": {"groups": [], "group": []}}})
    assert any("groups is not used" in e for e in errs)


def test_layout_group_must_be_string_array():
    errs = layout_errors({"views": {"by_order": {"group": "Salesman"}}})
    assert any("array of column-name strings" in e for e in errs)


def test_bad_json_cell_is_rejected():
    msg = validate_column_value("layout_json", "{not json")
    assert msg and "not valid JSON" in msg


def test_sql_json_assignment_is_extracted():
    found = json_assignments_in_sql(
        "UPDATE saved_reports SET layout_json = '{\"views\":{}}' WHERE id = 1"
    )
    assert found == [("layout_json", '{"views":{}}')]
