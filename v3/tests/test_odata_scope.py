"""OData salesman-scope containment."""

from web.reporting.odata_bridge import _public_run_params, _scope_tab


def test_empty_visible_keys_empties_rows():
    tab = {"columns": ["Salesman"], "rows": [{"Salesman": "Avi"}]}

    scoped = _scope_tab(tab, set())
    assert scoped is not tab
    assert scoped["rows"] == []


def test_matching_salesman_key_keeps_row():
    tab = {"columns": ["Salesman"], "rows": [{"Salesman": "Avi"}, {"Salesman": "Heshy"}]}

    assert _scope_tab(tab, {"Avi"})["rows"] == [{"Salesman": "Avi"}]


def test_salesman_key_normalizes_sheet_value_against_scope():
    tab = {"columns": ["Salesman"], "rows": [{"Salesman": "SM01"}, {"Salesman": "Other"}]}

    assert _scope_tab(tab, {"sm01"})["rows"] == [{"Salesman": "SM01"}]


def test_unknown_salesman_column_with_scope_empties_rows():
    tab = {"columns": ["Representative"], "rows": [{"Representative": "Avi"}]}

    scoped = _scope_tab(tab, {"Avi"})

    assert scoped is not tab
    assert scoped["rows"] == []


def test_public_run_params_drops_underscore_keys():
    assert _public_run_params({
        "period": "mtd",
        "_preset_name": "x",
        "_salesman_key": "../../../tmp",
    }) == {"period": "mtd"}
