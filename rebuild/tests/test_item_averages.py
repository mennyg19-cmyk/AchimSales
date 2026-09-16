"""Tests for Item Averages rollup math and privileged-only access."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rebuild.auth.principal import ROLE_DEVELOPER, ROLE_USER, Principal
from rebuild.reporting.authz import SCOPE_ALL, resolve_access
from rebuild.reports import item_averages


class _FakeScope:
    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self._mapping = mapping

    def salesmen_for(self, email: str) -> list[str]:
        return list(self._mapping.get((email or "").strip().lower(), []))


def test_rollup_sums_qty_across_customers_and_averages_over_full_window():
    rows = [
        {"Item #": "A", "Item Name": "Alpha", "Total Qty": 120},
        {"Item #": "A", "Item Name": "Alpha", "Total Qty": 24},
        {"Item #": "B", "Item Name": "Beta", "Total Qty": 52},
    ]
    out = item_averages.rollup_by_item(rows)
    assert out == [
        {
            "Item #": "A", "Item Name": "Alpha",
            "12-Month Qty": 144.0, "Avg/Month": 12.0, "Avg/Week": round(144 / 52, 2),
        },
        {
            "Item #": "B", "Item Name": "Beta",
            "12-Month Qty": 52.0, "Avg/Month": round(52 / 12, 2), "Avg/Week": 1.0,
        },
    ]


def test_rollup_skips_blank_item_numbers():
    assert item_averages.rollup_by_item([{"Item #": "", "Total Qty": 10}]) == []


def test_sales_rep_cannot_access_item_averages():
    scope = _FakeScope({"rep@x.com": ["10"]})
    access = resolve_access(Principal("rep@x.com", "Rep", ROLE_USER), "item_averages", scope)
    assert not access.allowed
    assert "admins" in access.reason


def test_admin_gets_company_wide_scope_for_item_averages():
    access = resolve_access(
        Principal("boss@x.com", "Boss", ROLE_DEVELOPER), "item_averages", _FakeScope({}))
    assert access.allowed
    assert access.scope_token == SCOPE_ALL
    assert access.salesmen is None


def test_build_snapshot_refuses_scoped_token(monkeypatch):
    monkeypatch.setattr(
        item_averages, "ConfigLoader",
        lambda db: SimpleNamespace(load_runnable=lambda key: SimpleNamespace(title="Item Averages")),
    )
    with pytest.raises(PermissionError, match="admins"):
        item_averages.build_snapshot(
            db=None, config=SimpleNamespace(reporting_api_timeout=1, reporting_api_base_url="",
                                            reporting_api_key="", max_result_rows=1000),
            report_key="item_averages", filters={}, scope_token="sm:10",
        )
