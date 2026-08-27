"""Company-wide named views + stamping Daily Ordered / Heshy Open Orders."""

from types import SimpleNamespace

from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.company_views import CompanyViewRepository
from web.data.repositories.schedules import MasterScheduleRepository
from web.scheduling.company_layouts import (
    DAILY_ORDERED_LAYOUT,
    DAILY_ORDERED_VIEW,
    HESHY_OPEN_LAYOUT,
    HESHY_OPEN_VIEW,
    is_daily_company_ordered,
    is_heshy_open_orders,
    seed_canonical_company_views,
)


def _db(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    return db


def test_company_view_upsert_rejects_reserved_names(tmp_path):
    repo = CompanyViewRepository(_db(tmp_path))
    try:
        repo.upsert("ordered", "Default", params={}, layout={}, updated_by=None)
        assert False, "expected ValueError"
    except ValueError:
        pass
    saved = repo.upsert(
        "ordered", DAILY_ORDERED_VIEW, params={"period": "yesterday"},
        layout=DAILY_ORDERED_LAYOUT, updated_by=None)
    assert saved.name == DAILY_ORDERED_VIEW
    again = repo.upsert(
        "ordered", DAILY_ORDERED_VIEW, params={"period": "yesterday"},
        layout={"active": "by_item"}, updated_by=None)
    assert again.id == saved.id
    assert again.layout["active"] == "by_item"


def test_matchers_daily_ordered_and_heshy():
    daily = SimpleNamespace(
        report_key="ordered", cadence={"freq": "daily"},
        params={"period": "yesterday"})
    split = SimpleNamespace(
        report_key="ordered", cadence={"freq": "daily"},
        params={"period": "yesterday", "split_by_salesman": True})
    weekly = SimpleNamespace(
        report_key="ordered", cadence={"freq": "weekly"},
        params={"period": "yesterday"})
    hesny = SimpleNamespace(
        report_key="ordered", cadence={"freq": "daily"},
        params={"period": "yesterday", "salesman": ["Hkaufman"], "status": ["Open order"]})
    assert is_daily_company_ordered(daily)
    assert not is_daily_company_ordered(split)
    assert not is_daily_company_ordered(weekly)
    assert not is_daily_company_ordered(hesny)
    assert is_heshy_open_orders(hesny)
    assert not is_heshy_open_orders(daily)


def test_seed_stamps_matching_schedules_and_skips_other_views(tmp_path):
    db = _db(tmp_path)
    masters = MasterScheduleRepository(db)
    daily_id = masters.create(
        "ordered", "DailyOrderReport", params={"period": "yesterday"}, layout={},
        cadence={"freq": "daily", "time": "00:00"})
    nine_id = masters.create(
        "ordered", "Daily Ordered (9am)", params={"period": "yesterday"}, layout={},
        cadence={"freq": "daily", "time": "09:00"})
    split_id = masters.create(
        "ordered", "Daily 9am Salesmen Ordered",
        params={"period": "yesterday", "split_by_salesman": True},
        layout={"order": ["summary"]},
        cadence={"freq": "daily", "time": "09:00"})
    hesny_id = masters.create(
        "ordered", "Daily Open Orders Report",
        params={"period": "yesterday", "salesman": ["Hkaufman"], "status": ["Open order"]},
        layout={}, cadence={"freq": "daily", "time": "11:00"})
    custom_id = masters.create(
        "ordered", "Someone's daily Ordered", params={"period": "yesterday"},
        layout={"order": ["summary"]}, cadence={"freq": "daily", "time": "08:00"},
        view_name="March")

    seed_canonical_company_views(db)

    assert masters.get(daily_id).view_name == DAILY_ORDERED_VIEW
    assert masters.get(nine_id).view_name == DAILY_ORDERED_VIEW
    assert masters.get(daily_id).layout["views"]["by_customer"]["group"] == [
        "Salesman", "CustomerName"]
    assert masters.get(split_id).view_name == "Default"
    assert masters.get(hesny_id).view_name == HESHY_OPEN_VIEW
    assert masters.get(hesny_id).layout["order"] == ["full_data"]
    assert masters.get(custom_id).view_name == "March"

    views = {v.name: v for v in CompanyViewRepository(db).list_for_report("ordered")}
    assert DAILY_ORDERED_VIEW in views and HESHY_OPEN_VIEW in views
    assert views[DAILY_ORDERED_VIEW].layout["views"]["summary"]["group"] == ["Salesman"]
    assert views[DAILY_ORDERED_VIEW].layout["views"]["summary"]["sorters"][1]["column"] == "Customer Name"
    assert views[HESHY_OPEN_VIEW].layout["views"]["full_data"]["hidden"] == ["LineNumber"]
