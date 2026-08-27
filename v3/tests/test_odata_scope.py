"""OData salesman scope must fail closed for scoped users."""

import pytest

from web.reporting.odata_bridge import UnscopedODataError, apply_visible_scope, _scope_tab


def test_scope_tab_keeps_matching_salesman_keys():
    tab = {
        "name": "Full Data",
        "columns": ["Salesman", "Qty"],
        "rows": [
            {"Salesman": "M Kolko", "Qty": 1},
            {"Salesman": "Other Rep", "Qty": 2},
        ],
    }
    out = _scope_tab(tab, {"mkolko"})
    assert [r["Salesman"] for r in out["rows"]] == ["M Kolko"]


def test_scope_tab_raises_when_tab_has_no_salesman_column():
    tab = {
        "name": "By Item",
        "columns": ["Item #", "Qty"],
        "rows": [{"Item #": "A", "Qty": 3}],
    }
    with pytest.raises(UnscopedODataError, match="By Item"):
        _scope_tab(tab, {"mkolko"})


def test_apply_visible_scope_refuses_unscoped_tabs():
    tabs = [
        {
            "name": "By Item",
            "columns": ["Item #"],
            "rows": [{"Item #": "A"}],
        },
        {
            "name": "Full Data",
            "columns": ["Salesman"],
            "rows": [{"Salesman": "M Kolko"}],
        },
    ]
    with pytest.raises(UnscopedODataError, match="By Item"):
        apply_visible_scope(tabs, {"mkolko"})


def test_apply_visible_scope_filters_when_every_tab_has_a_column():
    tabs = [
        {
            "name": "Full Data",
            "columns": ["Salesman", "Qty"],
            "rows": [
                {"Salesman": "M Kolko", "Qty": 1},
                {"Salesman": "Other", "Qty": 9},
            ],
        }
    ]
    out = apply_visible_scope(tabs, {"mkolko"})
    assert len(out[0]["rows"]) == 1


def test_unrestricted_user_keeps_unscoped_tabs():
    tabs = [{"name": "By Item", "columns": ["Item #"], "rows": [{"Item #": "A"}]}]
    assert apply_visible_scope(tabs, None) == tabs


def test_empty_tab_does_not_need_a_salesman_column():
    tabs = [{"name": "By Item", "columns": ["Item #"], "rows": []}]
    assert apply_visible_scope(tabs, {"mkolko"})[0]["rows"] == []
