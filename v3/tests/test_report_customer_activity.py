"""Customer Activity: SP rows -> All + per-salesman + Unassigned tabs."""

from report_engine.reports import customer_activity as B


def _rows():
    return B.clean_rows([
        {"Salesman": "REdwards", "Customer Account": "100", "Customer Name": "Acme",
         "Last Order Date": "2026-03-15", "PO #": "PO-2", "Sales Order Number": "SO-NEW"},
        {"Salesman": "JSmith", "Customer Account": "200", "Customer Name": "Beta",
         "Last Order Date": "2025-12-01", "PO #": "N/A", "Sales Order Number": "SO-B"},
        {"Salesman": "", "Customer Account": "300", "Customer Name": "Cold Co",
         "Last Order Date": "N/A", "PO #": "N/A", "Sales Order Number": "N/A"},
    ])


def test_all_tab_has_every_customer_with_salesman_column():
    tabs = B.build(_rows())
    all_tab = next(t for t in tabs if t["key"] == "all")
    assert all_tab["name"] == "All"
    assert all_tab["columns"][0]["field"] == "Salesman"
    assert len(all_tab["rows"]) == 3
    assert [t["name"] for t in tabs][0] == "All"


def test_per_salesman_tabs_omit_salesman_column():
    tabs = B.build(_rows())
    keys = [t["key"] for t in tabs]
    names = [t["name"] for t in tabs]
    assert "unassigned" in keys
    assert "REdwards" in names and "JSmith" in names
    assert names[-1] == "Unassigned"  # live puts Unassigned last
    bob = next(t for t in tabs if t["name"] == "REdwards")
    assert bob["columns"] == B._BASE_COLS
    assert "Salesman" not in bob["rows"][0]


def test_scope_filter_keeps_own_book():
    rows = B.filter_rows_by_salesman(_rows(), {"redwards"})
    tabs = B.build(rows)
    assert "unassigned" not in [t["key"] for t in tabs]
    all_rows = next(t for t in tabs if t["key"] == "all")["rows"]
    assert {r["Customer Account"] for r in all_rows} == {"100"}


def test_empty_build_still_has_all_tab():
    tabs = B.build([])
    assert len(tabs) == 1
    assert tabs[0]["key"] == "all"
    assert tabs[0]["rows"] == []


def test_na_placeholders_survive_clean():
    rows = B.clean_rows([
        {"Salesman": "X", "Customer Account": "1", "Customer Name": "A",
         "Last Order Date": "N/A", "PO #": "N/A", "Sales Order Number": "N/A"},
    ])
    assert rows[0]["Last Order Date"] == "N/A"
    assert rows[0]["PO #"] == "N/A"
