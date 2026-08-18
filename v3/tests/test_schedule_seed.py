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
    assert len(rows) == 12
    assert "Daily 9am" in names
    assert "Weekly 5pm Friday Amazon Ordered" in names
    assert "Weekly Amazon Thursday using amazon_weekly" not in names
    assert all(not r.is_active for r in rows)
    assert all(r.is_shared for r in rows)
    nine = next(r for r in rows if r.name == "Daily 9am")
    assert nine.params["customers"] == ["48999", "917", "2267"]
    assert nine.sharepoint_path == "Direct Reports/Ordered Report/Daily"
    amazon = next(r for r in rows if r.name == "Amazon Monthly Ordered")
    assert amazon.cadence["monthdays"] == [-1]
    assert amazon.params["period"] == "mtd"
    shipped = next(r for r in rows if r.name == "Daily 9am Salesmen Shipped")
    assert "commissions" not in (shipped.layout.get("order") or [])
    assert "invoices" in (shipped.layout.get("order") or [])
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
