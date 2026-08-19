"""Beta imports Live Azure runbook schedules as disabled company rows."""

from dataclasses import replace
from pathlib import Path

import pytest

from web import _LIVE_RUNBOOK_SCHEDULES, _seed_master_schedules, create_app
from web.config import Config
from web.data.migrate import migrate
from web.data.repositories.schedules import MasterScheduleRepository


def _cfg(tmp_path) -> Config:
    return Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="", new_app_marker=True,
        outbox_dir=tmp_path / "outbox",
    )


def test_beta_runbook_seed_inserts_disabled_company_schedules(tmp_path: Path):
    app = create_app(replace(_cfg(tmp_path), is_beta=True))
    db = app.config["DB"]
    migrate(db)
    _seed_master_schedules(app, db, _LIVE_RUNBOOK_SCHEDULES, inactive=True)
    rows = MasterScheduleRepository(db).list_all()
    names = {r.name for r in rows}
    assert len(rows) == 11
    assert "Daily 9am" not in names
    assert "Weekly 5pm Friday Amazon Ordered" in names
    assert "Weekly Amazon Thursday using amazon_weekly" not in names
    assert all(not r.is_active for r in rows)
    assert all(r.is_shared for r in rows)
    amazon = next(r for r in rows if r.name == "Amazon Monthly Ordered")
    assert amazon.cadence["monthdays"] == [-1]
    assert amazon.params["period"] == "mtd"
    shipped = next(r for r in rows if r.name == "Daily 9am Salesmen Shipped")
    assert "commissions" not in (shipped.layout.get("order") or [])
    assert "invoices" in (shipped.layout.get("order") or [])
    assert shipped.params.get("split_by_salesman") is True
    ordered_sm = next(r for r in rows if r.name == "Daily 9am Salesmen Ordered")
    assert ordered_sm.params.get("split_by_salesman") is True
    _seed_master_schedules(app, db, _LIVE_RUNBOOK_SCHEDULES, inactive=True)
    assert len(MasterScheduleRepository(db).list_all()) == len(rows)


def test_shared_master_schedule_name_is_unique(tmp_path: Path):
    import sqlite3

    app = create_app(replace(_cfg(tmp_path), is_beta=True))
    db = app.config["DB"]
    migrate(db)
    repo = MasterScheduleRepository(db)
    repo.create("ordered", "Daily 9am", params={}, layout={},
                cadence={"freq": "daily", "time": "08:00"}, is_shared=True)
    with pytest.raises(sqlite3.IntegrityError):
        repo.create("ordered", "Daily 9am", params={}, layout={},
                    cadence={"freq": "daily", "time": "08:00"}, is_shared=True)


def test_next_copy_name_uses_copy_then_numbered():
    from web.data.repositories.schedules import next_copy_name

    assert next_copy_name("Daily 9am", set()) == "Daily 9am (copy)"
    assert next_copy_name("Daily 9am", {"Daily 9am (copy)"}) == "Daily 9am (copy 2)"
    assert next_copy_name("Daily 9am", {"Daily 9am (copy)", "Daily 9am (copy 2)"}) == "Daily 9am (copy 3)"


def test_test_mount_seed_stays_on_old_azure_names(tmp_path: Path):
    from web import _AZURE_SCHEDULES

    app = create_app(_cfg(tmp_path))
    db = app.config["DB"]
    migrate(db)
    _seed_master_schedules(app, db, _AZURE_SCHEDULES)
    rows = MasterScheduleRepository(db).list_all()
    names = {r.name for r in rows}
    assert "Daily Invoiced Report" in names
    assert "DailyInvoicedReport" not in names
    assert all(r.is_active for r in rows)


def test_existing_salesmen_schedule_gets_split_all_on_reseed(tmp_path: Path):
    app = create_app(replace(_cfg(tmp_path), is_beta=True))
    db = app.config["DB"]
    migrate(db)
    repo = MasterScheduleRepository(db)
    repo.create(
        "ordered", "Daily 9am Salesmen Ordered",
        params={"period": "yesterday"}, layout={},
        cadence={"freq": "daily", "time": "09:00"}, is_shared=True, is_active=False,
    )
    _seed_master_schedules(app, db, _LIVE_RUNBOOK_SCHEDULES, inactive=True)
    row = next(r for r in repo.list_all() if r.name == "Daily 9am Salesmen Ordered")
    assert row.params.get("split_by_salesman") is True
    assert row.params.get("period") == "yesterday"


def test_seed_does_not_restore_deleted_company_schedule(tmp_path: Path):
    from web.data.repositories.app_settings import AppSettingsRepository

    app = create_app(replace(_cfg(tmp_path), is_beta=True))
    db = app.config["DB"]
    migrate(db)
    _seed_master_schedules(app, db, _LIVE_RUNBOOK_SCHEDULES, inactive=True)
    repo = MasterScheduleRepository(db)
    row = next(r for r in repo.list_all() if r.name == "Daily 9am Salesmen Ordered")
    AppSettingsRepository(db).skip_seed_name(row.name)
    assert repo.delete(row.id)
    _seed_master_schedules(app, db, _LIVE_RUNBOOK_SCHEDULES, inactive=True)
    names = {r.name for r in repo.list_all()}
    assert "Daily 9am Salesmen Ordered" not in names


def test_seed_sharepoint_paths_omit_direct_reports_home():
    from web import _AZURE_SCHEDULES, _LIVE_RUNBOOK_SCHEDULES

    rows = _AZURE_SCHEDULES + _LIVE_RUNBOOK_SCHEDULES
    for s in rows:
        path = s.get("sharepoint_path") or ""
        assert not path.lower().startswith("direct reports"), s["name"]
    live = next(s for s in _LIVE_RUNBOOK_SCHEDULES
                if s["name"] == "Monthly 1st 12am Customer Activity")
    azure = next(s for s in _AZURE_SCHEDULES if s["name"] == "Monthly Customer Activity")
    assert live["sharepoint_path"] == "Salesman Report/Customer Activity/{Month} {YYYY}"
    assert azure["sharepoint_path"] == "Salesman Report/Customer Activity/{Month} {YYYY}"


def test_migration_0011_strips_prefix_and_sets_customer_activity_month_folder(tmp_path: Path):
    from web.data.connection import Database, _connect
    from web.data.migrate import migrate
    from web.data.repositories.schedules import MasterScheduleRepository

    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    repo = MasterScheduleRepository(db)
    doubled = repo.create(
        "ordered", "DailyOrderReport", params={}, layout={},
        cadence={"freq": "daily", "time": "00:00"},
        sharepoint_path="Direct Reports/Direct Reports/Ordered Report/Daily",
        is_shared=True,
    )
    activity = repo.create(
        "customer_activity", "Monthly 1st 12am Customer Activity",
        params={}, layout={},
        cadence={"freq": "monthly", "time": "00:00", "monthdays": [1]},
        sharepoint_path="Salesman Report/Customer Activity",
        is_shared=True,
    )
    sql = (
        Path(__file__).resolve().parents[1]
        / "web/data/migrations/precious/0011_strip_direct_reports_prefix.sql"
    ).read_text(encoding="utf-8")
    conn = _connect(db.precious_path)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()
    assert repo.get(doubled).sharepoint_path == "Ordered Report/Daily"
    assert repo.get(activity).sharepoint_path == (
        "Salesman Report/Customer Activity/{Month} {YYYY}"
    )
