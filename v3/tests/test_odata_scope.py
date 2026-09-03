"""OData salesman-scope containment."""

from web.reporting.odata_bridge import _scope_tab


def test_empty_visible_keys_empties_rows():
    tab = {"columns": ["Salesman"], "rows": [{"Salesman": "Avi"}]}

    scoped = _scope_tab(tab, set())
    assert scoped is not tab
    assert scoped["rows"] == []


def test_matching_salesman_key_keeps_row():
    tab = {"columns": ["Salesman"], "rows": [{"Salesman": "Avi"}, {"Salesman": "Heshy"}]}

    assert _scope_tab(tab, {"Avi"})["rows"] == [{"Salesman": "Avi"}]


def test_unknown_salesman_column_with_scope_empties_rows():
    tab = {"columns": ["Representative"], "rows": [{"Representative": "Avi"}]}

    scoped = _scope_tab(tab, {"Avi"})

    assert scoped is not tab
    assert scoped["rows"] == []
