"""Repos backing Phase C: saved_reports, schedules, master_schedules, runs, outbox."""

from __future__ import annotations

import pytest

from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.outbox import OutboxRepository
from web.data.repositories.report_defaults import (
    CUSTOM_VIEW_NAME,
    DEFAULT_VIEW_NAME,
    ReportDefaultRepository,
    resolve_send_layout,
    view_and_layout_for_create,
    view_and_layout_for_update,
)
from web.data.repositories.saved_reports import SavedReportRepository
from web.data.repositories.schedules import (
    MASTER,
    PERSONAL,
    MasterScheduleRepository,
    ScheduleRepository,
    ScheduleRunRepository,
)
from web.data.repositories.users import UserRepository


@pytest.fixture()
def db(tmp_path) -> Database:
    d = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(d)
    return d


@pytest.fixture()
def user_id(db) -> int:
    return UserRepository(db).upsert("u@x.com", display_name="U", role="salesman").id


# --- saved_reports ---------------------------------------------------------

def test_saved_report_create_list_get_delete(db, user_id):
    repo = SavedReportRepository(db)
    pid = repo.create(user_id, "ordered", "March view",
                      {"period": "mtd"}, {"hidden": ["x"]})
    rows = repo.list_for_user(user_id)
    assert len(rows) == 1 and rows[0].name == "March view"
    assert rows[0].params == {"period": "mtd"} and rows[0].layout == {"hidden": ["x"]}
    got = repo.get(pid, user_id)
    assert got is not None and got.report_key == "ordered"
    assert repo.delete(pid, user_id) is True
    assert repo.list_for_user(user_id) == []


def test_saved_report_upsert_by_name(db, user_id):
    repo = SavedReportRepository(db)
    repo.create(user_id, "ordered", "v", {"period": "mtd"}, {})
    repo.create(user_id, "ordered", "v", {"period": "ytd"}, {})  # same name -> overwrite
    rows = repo.list_for_user(user_id)
    assert len(rows) == 1 and rows[0].params == {"period": "ytd"}


def test_saved_report_is_owner_scoped(db, user_id):
    other = UserRepository(db).upsert("o@x.com", display_name="O", role="salesman").id
    repo = SavedReportRepository(db)
    pid = repo.create(user_id, "ordered", "v", {}, {})
    assert repo.get(pid, other) is None
    assert repo.delete(pid, other) is False


# --- schedules + runs ------------------------------------------------------

def test_schedule_crud_and_active_toggle(db, user_id):
    repo = ScheduleRepository(db)
    sid = repo.create(user_id, "ordered", params={"period": "mtd"}, layout={},
                      cadence={"freq": "weekly", "time": "08:00", "weekdays": [1]},
                      recipients="a@x.com")
    s = repo.get(sid, user_id)
    assert s and s.cadence["freq"] == "weekly" and s.is_active is True
    assert repo.set_active(sid, user_id, False) is True
    assert repo.get(sid, user_id).is_active is False
    assert repo.update(sid, user_id, params={"period": "ytd"}, layout={},
                       cadence={"freq": "daily", "time": "07:00"}) is True
    assert repo.get(sid, user_id).params == {"period": "ytd"}
    assert repo.delete(sid, user_id) is True
    assert repo.get(sid, user_id) is None


def test_schedule_owner_scoped(db, user_id):
    other = UserRepository(db).upsert("o@x.com", display_name="O", role="salesman").id
    repo = ScheduleRepository(db)
    sid = repo.create(user_id, "ordered", params={}, layout={}, cadence={})
    assert repo.get(sid, other) is None
    assert repo.get_any(sid) is not None  # worker path is owner-agnostic
    assert repo.set_active(sid, other, False) is False


def test_schedule_runs_history_and_last_run(db, user_id):
    sched = ScheduleRepository(db)
    sid = sched.create(user_id, "ordered", params={}, layout={}, cadence={})
    runs = ScheduleRunRepository(db)
    rid = runs.start(sid, PERSONAL, extra_meta={"job_id": "job-1"})
    runs.finish(rid, status="success", rows=42, output_meta={"file": "x.xlsx"})
    history = runs.list_for_schedule(sid, PERSONAL)
    assert len(history) == 1 and history[0].status == "success" and history[0].rows == 42
    assert history[0].output_meta.get("job_id") == "job-1"
    assert history[0].output_meta.get("file") == "x.xlsx"
    assert runs.last_run_at(sid, PERSONAL) is not None
    manual_id = runs.start(sid, PERSONAL, manual=True)
    runs.finish(manual_id, status="success", rows=1, output_meta={"file": "y.xlsx"})
    clock_at = runs.last_run_at(sid, PERSONAL)
    assert clock_at == history[0].started_at
    assert runs.last_success_at(sid, PERSONAL) == history[0].started_at


def test_master_schedule_crud(db):
    repo = MasterScheduleRepository(db)
    mid = repo.create("invoiced", "Nightly invoiced", params={}, layout={},
                      cadence={"freq": "daily", "time": "06:00"}, recipients="team@x.com")
    assert len(repo.list_all()) == 1
    assert repo.get(mid).name == "Nightly invoiced"
    assert repo.update(mid, name="Renamed", params={"period": "yesterday"}, layout={},
                       cadence={"freq": "daily", "time": "06:30"},
                       report_key="ordered") is True
    row = repo.get(mid)
    assert row.name == "Renamed"
    assert row.report_key == "ordered"
    assert row.params["period"] == "yesterday"
    assert [m.id for m in repo.list_active()] == [mid]
    assert repo.set_active(mid, False) is True
    assert repo.list_active() == []
    assert repo.delete(mid) is True


def test_master_schedule_create_can_start_inactive(db):
    repo = MasterScheduleRepository(db)
    mid = repo.create("ordered", "Off copy", params={}, layout={},
                      cadence={"freq": "daily", "time": "08:00"},
                      sharepoint_path="Direct Reports/Ordered Report/Daily",
                      is_active=False)
    row = repo.get(mid)
    assert row.is_active is False
    assert repo.list_active() == []


# --- outbox ----------------------------------------------------------------

def test_outbox_enqueue_and_mark(db):
    repo = OutboxRepository(db)
    mid = repo.enqueue(subject="Ordered report", recipients="a@x.com",
                       attachment_meta={"name": "ordered.xlsx"})
    msg = repo.get(mid)
    assert msg and msg.status == "queued" and msg.attachment_meta["name"] == "ordered.xlsx"
    repo.mark(mid, "sent")
    assert repo.get(mid).status == "sent"
    assert len(repo.list_recent()) == 1


def test_report_default_upsert_and_get(db, user_id):
    repo = ReportDefaultRepository(db)
    assert repo.get("ordered") is None
    assert repo.get_layout("ordered") == {}
    saved = repo.upsert("ordered", params={"period": "mtd"},
                        layout={"active": "by_item"}, updated_by=user_id)
    assert saved.params["period"] == "mtd"
    assert repo.get_layout("ordered")["active"] == "by_item"
    repo.upsert("ordered", params={}, layout={"order": ["summary"]}, updated_by=user_id)
    assert repo.get("ordered").layout["order"] == ["summary"]


def test_view_and_layout_helpers():
    assert view_and_layout_for_create({}) == (DEFAULT_VIEW_NAME, {})
    assert view_and_layout_for_create({"view_name": "Default", "layout": {"order": ["x"]}}) == (
        DEFAULT_VIEW_NAME, {})
    name, layout = view_and_layout_for_create(
        {"layout": {"order": ["summary"], "views": {"summary": {}}}})
    assert name == CUSTOM_VIEW_NAME and layout["order"] == ["summary"]
    name, layout = view_and_layout_for_create(
        {"view_name": "March", "layout": {"active": "a"}})
    assert name == "March" and layout["active"] == "a"

    kept = {"order": ["seed"]}
    assert view_and_layout_for_update(
        {"view_name": "Default", "layout": {}}, "Default", kept)[1] == kept
    assert view_and_layout_for_update(
        {"view_name": "Default"}, "March", kept) == (DEFAULT_VIEW_NAME, {})
    assert resolve_send_layout("Default", {}, {"active": "def"}) == {"active": "def"}
    assert resolve_send_layout("Default", {"order": ["x"]}, {"active": "def"}) == {"order": ["x"]}
    assert resolve_send_layout("March", {"active": "m"}, {"active": "def"}) == {"active": "m"}
    live = {"views": {"by_customer": {"group": ["Salesman", "CustomerName"]}}}
    assert resolve_send_layout("Daily Ordered", {"active": "old"}, {"active": "def"}, live) == live
    assert resolve_send_layout("Daily Ordered", {"active": "old"}, {"active": "def"}, {}) == {"active": "old"}
