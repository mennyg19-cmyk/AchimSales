"""Tests for the dashboard mirror refresh (fetch -> metrics -> cache rebuild)."""

from datetime import date

import pytest

from web.dashboard.mirror import MirrorService
from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.dashboard import DashboardRepository


class _Cust:
    def __init__(self, acct, name, sg):
        self.customer_account, self.customer_name, self.sales_group = acct, name, sg


class _Order:
    def __init__(self, acct, d):
        self.customer_account, self.order_date = acct, d


@pytest.fixture()
def db(tmp_path):
    d = Database(tmp_path / "precious.db", tmp_path / "cache.db")
    migrate(d)
    return d


def test_rebuild_computes_status_per_customer(db):
    customers = [
        _Cust("100", "Acme", "REdwards"),
        _Cust("200", "Beta", "REdwards"),
        _Cust("300", "Gamma", ""),  # no orders -> new
    ]
    orders = [
        # Acme: 30-day cadence, last 5 days ago -> active
        _Order("100", "2026-03-03"), _Order("100", "2026-04-02"),
        _Order("100", "2026-05-02"), _Order("100", "2026-05-27"),
        # Beta: tight cadence but long gap -> overdue
        _Order("200", "2026-01-01"), _Order("200", "2026-01-11"),
        _Order("200", "2026-01-21"),
    ]
    repo = DashboardRepository(db)
    svc = MirrorService(customers_fetch=lambda: customers, orders_fetch=lambda: orders, repo=repo)
    n = svc.rebuild(today=date(2026, 6, 1))
    assert n == 3

    by_acct = {c.customer_account: c for c in repo.all()}
    assert by_acct["100"].status == "active"
    assert by_acct["200"].status == "overdue"
    assert by_acct["300"].status == "new"
    assert by_acct["300"].order_count == 0
    assert by_acct["100"].order_count == 4


def test_rebuild_is_full_replace(db):
    repo = DashboardRepository(db)
    svc = MirrorService(
        customers_fetch=lambda: [_Cust("1", "One", "x")],
        orders_fetch=lambda: [], repo=repo)
    svc.rebuild(today=date(2026, 6, 1))
    assert repo.count() == 1
    # Second rebuild with a different universe fully replaces the first.
    svc2 = MirrorService(
        customers_fetch=lambda: [_Cust("2", "Two", "y")],
        orders_fetch=lambda: [], repo=repo)
    svc2.rebuild(today=date(2026, 6, 1))
    assert repo.count() == 1 and repo.get("1") is None and repo.get("2") is not None
