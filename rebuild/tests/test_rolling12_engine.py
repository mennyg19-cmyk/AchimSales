"""Tests for the Number 4 rolling-12 report: fetch plan, dynamic columns,
row cleaning, scoping, and the snapshot builder itself (with a faked API)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rebuild.reports import rolling12
from rebuild.reports.params import force_salesman_scope, scope_row_field, translate


# --- fetch plan (the mode question) ---------------------------------------- #

def test_both_mode_runs_customer_sp_then_item_sp():
    plan = rolling12.fetch_plan({"mode": "both"})
    assert [sp for sp, _, _ in plan] == [
        "customer_item_sales_rolling_12", "item_customer_sales_rolling_12"]


def test_single_modes_run_only_their_own_sp():
    assert [t[1] for t in rolling12.fetch_plan({"mode": "by_customer"})] == ["by_customer"]
    assert [t[1] for t in rolling12.fetch_plan({"mode": "by_item"})] == ["by_item"]


def test_missing_or_unknown_mode_falls_back_to_both():
    assert len(rolling12.fetch_plan({})) == 2
    assert len(rolling12.fetch_plan({"mode": "banana"})) == 2


# --- params ----------------------------------------------------------------- #

def test_translator_sends_as_of_today_and_includes_current_month():
    sp_params = translate("number_4", {"mode": "by_item"})
    assert sp_params["IncludeCurrentMonth"] is True
    assert len(sp_params["AsOfDate"]) == 10  # yyyy-mm-dd
    # the mode marker rides along for the cache key but is not an SP parameter
    assert sp_params["_mode"] == "by_item"


def test_salesman_scope_pins_sales_group_param():
    scoped = force_salesman_scope("number_4", translate("number_4", {}), ["MGrego"])
    assert scoped["SalesGroup"] == "MGrego"


def test_scope_row_field_is_salesman_column():
    # The SPs return the sales group under the header "Salesman".
    assert scope_row_field("number_4") == "Salesman"


# --- dynamic columns + cleaning --------------------------------------------- #

_HEADERS = ["Customer #", "Customer Name", "Item #", "Item Name",
            "Jul-25 Qty", "Jul-25 $", "Jun-26 Qty", "Jun-26 $",
            "Total Qty", "Total $", "Avg Price", "Salesman", "Book Price"]


def test_month_columns_are_typed_by_suffix_not_hardcoded_names():
    columns = rolling12._columns(_HEADERS)
    types = {c["field"]: c["type"] for c in columns}
    assert types["Jul-25 Qty"] == "int"
    assert types["Jul-25 $"] == "money"
    assert types["Total Qty"] == "int"
    assert types["Total $"] == "money"
    assert types["Avg Price"] == "money"
    assert types["Book Price"] == "money"
    assert types["Customer Name"] == "text"
    assert types["Salesman"] == "text"


def test_column_order_follows_the_sp_exactly():
    columns = rolling12._columns(_HEADERS)
    assert [c["field"] for c in columns] == _HEADERS


def test_clean_rows_coerces_string_numbers():
    columns = rolling12._columns(["Customer #", "Jul-25 Qty", "Jul-25 $"])
    rows = rolling12._clean_rows(
        [{"Customer #": "C1", "Jul-25 Qty": "3", "Jul-25 $": "45.5"}], columns)
    assert rows[0]["Jul-25 Qty"] == 3.0
    assert rows[0]["Jul-25 $"] == 45.50
    assert rows[0]["Customer #"] == "C1"


# --- snapshot builder (faked API + config) ---------------------------------- #

def _fake_result(rows, columns):
    return SimpleNamespace(rows=rows, columns=columns, row_count=len(rows))


class _FakeClient:
    """Records which SPs were called and returns canned rows per SP."""

    def __init__(self, results):
        self.results = results
        self.calls = []

    def run_report(self, sp_name, params):
        self.calls.append((sp_name, dict(params)))
        return self.results[sp_name]


def _snapshot(monkeypatch, filters, results, scope_token="all", max_rows=1000):
    client = _FakeClient(results)
    monkeypatch.setattr(rolling12, "ReportingApiClient", lambda *a, **k: client)
    monkeypatch.setattr(rolling12, "ConfigLoader", lambda db: SimpleNamespace(
        load_runnable=lambda key: SimpleNamespace(title="Number 4 (Rolling 12 Months)")))
    config = SimpleNamespace(
        reporting_api_base_url="http://x", reporting_api_key="k",
        reporting_api_timeout=5, max_result_rows=max_rows)
    snapshot = rolling12.build_snapshot(
        None, config, "number_4", filters, scope_token, requested_by="me@x.com")
    return snapshot, client


_CUST_ROWS = [
    {"Customer #": "C1", "Jul-25 Qty": 2, "Jul-25 $": 20.0, "Salesman": "MGrego"},
    {"Customer #": "C2", "Jul-25 Qty": 1, "Jul-25 $": 10.0, "Salesman": "JDoe"},
]
_ITEM_ROWS = [
    {"Item #": "I1", "Jul-25 Qty": 3, "Jul-25 $": 30.0, "Salesman": "MGrego"},
]
_RESULTS = {
    "customer_item_sales_rolling_12": _fake_result(_CUST_ROWS, ["Customer #", "Jul-25 Qty", "Jul-25 $", "Salesman"]),
    "item_customer_sales_rolling_12": _fake_result(_ITEM_ROWS, ["Item #", "Jul-25 Qty", "Jul-25 $", "Salesman"]),
}


def test_both_mode_builds_two_tabs_from_two_sp_calls(monkeypatch):
    snapshot, client = _snapshot(monkeypatch, {"mode": "both"}, _RESULTS)
    assert [t["key"] for t in snapshot["tabs"]] == ["by_customer", "by_item"]
    assert [c[0] for c in client.calls] == [
        "customer_item_sales_rolling_12", "item_customer_sales_rolling_12"]
    assert snapshot["row_count"] == 3


def test_mode_marker_never_reaches_the_api(monkeypatch):
    _, client = _snapshot(monkeypatch, {"mode": "both"}, _RESULTS)
    for _, params in client.calls:
        assert "_mode" not in params


def test_single_mode_builds_one_tab(monkeypatch):
    snapshot, client = _snapshot(monkeypatch, {"mode": "by_item"}, _RESULTS)
    assert [t["key"] for t in snapshot["tabs"]] == ["by_item"]
    assert len(client.calls) == 1


def test_scoped_person_only_sees_their_sales_groups_rows(monkeypatch):
    snapshot, client = _snapshot(
        monkeypatch, {"mode": "by_customer"}, _RESULTS, scope_token="sm:MGrego")
    rows = snapshot["tabs"][0]["rows"]
    assert [r["Customer #"] for r in rows] == ["C1"]
    # and the SP was asked to filter server-side too
    assert client.calls[0][1]["SalesGroup"] == "MGrego"


def test_total_row_sums_month_and_dollar_columns(monkeypatch):
    snapshot, _ = _snapshot(monkeypatch, {"mode": "by_customer"}, _RESULTS)
    total = snapshot["tabs"][0]["total"]
    assert total["Customer #"] == "TOTAL"
    assert total["Jul-25 Qty"] == 3
    assert total["Jul-25 $"] == 30.0


def test_total_row_keeps_fractional_quantities(monkeypatch):
    # Quantities can be fractional (cases vs eaches); the total must not be
    # truncated to a whole number like the generic engine total does.
    results = {"customer_item_sales_rolling_12": _fake_result(
        [{"Customer #": "C1", "Jul-25 Qty": 1.5, "Salesman": "MGrego"},
         {"Customer #": "C2", "Jul-25 Qty": 0.75, "Salesman": "JDoe"}],
        ["Customer #", "Jul-25 Qty", "Salesman"])}
    snapshot, _ = _snapshot(monkeypatch, {"mode": "by_customer"}, results)
    assert snapshot["tabs"][0]["total"]["Jul-25 Qty"] == 2.25


def test_row_limit_guard_still_applies(monkeypatch):
    with pytest.raises(ValueError):
        _snapshot(monkeypatch, {"mode": "by_customer"}, _RESULTS, max_rows=1)


def test_cancelled_after_fetch_abandons_the_snapshot(monkeypatch):
    client = _FakeClient(_RESULTS)
    monkeypatch.setattr(rolling12, "ReportingApiClient", lambda *a, **k: client)
    monkeypatch.setattr(rolling12, "ConfigLoader", lambda db: SimpleNamespace(
        load_runnable=lambda key: SimpleNamespace(title="Number 4")))
    config = SimpleNamespace(
        reporting_api_base_url="http://x", reporting_api_key="k",
        reporting_api_timeout=5, max_result_rows=1000)
    snapshot = rolling12.build_snapshot(
        None, config, "number_4", {"mode": "both"}, "all",
        requested_by="me@x.com", cancelled=lambda: True)
    assert snapshot is None
    assert len(client.calls) == 1  # stopped after the first fetch
