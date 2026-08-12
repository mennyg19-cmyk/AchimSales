"""Scheduling: cadence math + the schedule runner (build -> deliver -> record)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from web.auth.authorization import Authorization
from web.config import Config
from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.outbox import OutboxRepository
from web.data.repositories.salesmen import SalesmanRepository, SalesmanSeed
from web.data.repositories.schedules import (
    MASTER,
    PERSONAL,
    MasterScheduleRepository,
    ScheduleRepository,
    ScheduleRunRepository,
)
from web.data.repositories.users import UserRepository
from web.delivery.email import DeliveryResult, EmailService
from web.delivery.service import DeliveryOutcome, DeliveryService
from web.delivery.sharepoint import SharePointService
from web.scheduling import cadence as C
from web.scheduling.runner import ScheduleRunner
from web.reporting.cache import ReportCache
from web.reporting.runner import ReportRunner


# --- cadence ---------------------------------------------------------------

def test_normalize_validates_and_clamps():
    assert C.normalize({"freq": "daily", "time": "8:5"}) == {"freq": "daily", "time": "08:05"}
    assert C.normalize({"freq": "weekly", "time": "08:00", "weekdays": [3, 1, 1]}) == \
        {"freq": "weekly", "time": "08:00", "weekdays": [1, 3]}
    assert C.normalize({"freq": "monthly", "monthday": 99})["monthday"] == 28
    assert C.normalize({"freq": "monthly", "monthday": 99})["monthdays"] == [28]
    assert C.normalize({"freq": "monthly", "monthdays": [1, 15, -1, 15]})["monthdays"] == [1, 15, -1]
    with pytest.raises(ValueError):
        C.normalize({"freq": "hourly"})
    with pytest.raises(ValueError):
        C.normalize({"freq": "weekly", "weekdays": []})


def test_due_now_daily():
    cad = {"freq": "daily", "time": "08:00"}
    # 2026-06-01 is a Monday; 13:00 UTC = 09:00 EDT (past 08:00)
    now = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    assert C.due_now(cad, None, now) is True
    # already ran earlier today (Eastern) -> not due
    assert C.due_now(cad, "2026-06-01T12:30:00+00:00", now) is False
    # before the scheduled time -> not due (10:00 UTC = 06:00 EDT)
    assert C.due_now(cad, None, datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)) is False


def test_due_now_weekly_wrong_day():
    cad = {"freq": "weekly", "time": "08:00", "weekdays": [2]}  # Wednesday only
    monday = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    assert C.due_now(cad, None, monday) is False


def test_describe():
    assert "Daily" in C.describe({"freq": "daily", "time": "08:00"})
    assert "Mon" in C.describe({"freq": "weekly", "time": "08:00", "weekdays": [0]})


# --- runner ----------------------------------------------------------------

@pytest.fixture()
def stack(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    cfg = Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="", new_app_marker=True, outbox_dir=tmp_path / "outbox",
    )
    email = EmailService(cfg, OutboxRepository(db), SharePointService(cfg))
    payload = {"tabs": [{"key": "t", "name": "T", "columns": [{"field": "a"}],
                         "rows": [{"a": 1}, {"a": 2}]}]}
    delivery = DeliveryService(ReportRunner(ReportCache(db)),
                               lambda key: (lambda params, vk: payload), email)
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)
    return db, runner


def test_runner_personal_records_success(stack):
    db, runner = stack
    uid = UserRepository(db).upsert("rep@x.com", display_name="Rep", role="admin").id
    sid = ScheduleRepository(db).create(uid, "ordered", params={}, layout={},
                                        cadence={"freq": "daily", "time": "08:00"},
                                        recipients="a@x.com")
    runner.run(sid, PERSONAL)
    hist = ScheduleRunRepository(db).list_for_schedule(sid, PERSONAL)
    assert len(hist) == 1 and hist[0].status == "success" and hist[0].rows == 2
    assert OutboxRepository(db).list_recent()


def test_runner_master_runs_unrestricted(stack):
    db, runner = stack
    mid = MasterScheduleRepository(db).create("ordered", "Nightly", params={}, layout={},
                                              cadence={"freq": "daily", "time": "08:00"},
                                              recipients="team@x.com")
    runner.run(mid, MASTER)
    hist = ScheduleRunRepository(db).list_for_schedule(mid, MASTER)
    assert len(hist) == 1 and hist[0].status == "success"


def test_runner_master_manager_owner_is_scoped(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from report_engine.lib import salesman_key
    mgr = UserRepository(db).upsert("mgr@x.com", display_name="Mgr", role="manager")
    SalesmanRepository(db).upsert_many([
        SalesmanSeed(raw_key="MKolko", number="1", full_name="M Kolko",
                     display_name="M Kolko", email="m@x.com"),
    ])
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO user_salesman_access(user_id, salesman_key) VALUES (?, ?)",
            (mgr.id, salesman_key("MKolko")),
        )

    class FakeDelivery:
        def __init__(self):
            self.calls = []

        def run_and_deliver(self, **kwargs):
            self.calls.append(kwargs)
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=[kwargs["recipients"]], eml_name="x.eml"),
                row_count=1,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Mgr book", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="m@x.com",
        owner_user_id=mgr.id, is_shared=True)
    runner.run(mid, MASTER)
    assert delivery.calls[0]["identity"] == "mgr@x.com"
    assert delivery.calls[0]["visible_salesman_keys"] == {salesman_key("MKolko")}


def test_runner_master_fans_out_salesman_emails_with_full_management_copy(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    SalesmanRepository(db).upsert_many([
        SalesmanSeed(raw_key="MKolko", number="1", full_name="M Kolko",
                     display_name="M Kolko", email="m@x.com"),
        SalesmanSeed(raw_key="AGrossman", number="2", full_name="A Grossman",
                     display_name="A Grossman", email="a@x.com"),
    ])

    class FakeDelivery:
        def __init__(self):
            self.calls = []

        def run_and_deliver(self, **kwargs):
            self.calls.append(kwargs)
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=[kwargs["recipients"]], eml_name="x.eml"),
                row_count=1,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={
            "period": "yesterday",
            "email_salesman_keys": ["MKolko", "AGrossman"],
            "split_by_salesman": True,
            "email_to_salesmen": False,
        }, layout={}, cadence={"freq": "daily", "time": "08:00"},
        recipients="manager@x.com")
    runner.run(mid, MASTER)

    assert len(delivery.calls) == 3
    assert delivery.calls[0]["recipients"] == "manager@x.com"
    assert delivery.calls[0]["params"] == {"period": "yesterday"}
    split_calls = delivery.calls[1:]
    assert [c["recipients"] for c in split_calls] == ["m@x.com", "a@x.com"]
    assert [c["params"]["salesman"] for c in split_calls] == [["MKolko"], ["AGrossman"]]
    hist = ScheduleRunRepository(db).list_for_schedule(mid, MASTER)
    assert hist[0].status == "success" and hist[0].rows == 3
    assert hist[0].debug_log.startswith("OK:")
    assert "manager@x.com" in hist[0].debug_log
    deliveries = (hist[0].output_meta or {}).get("deliveries") or []
    assert len(deliveries) == 3


def test_runner_master_skips_salesman_without_email_without_failing_run(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    SalesmanRepository(db).upsert_many([
        SalesmanSeed(raw_key="MKolko", number="1", full_name="M Kolko",
                     display_name="M Kolko", email="m@x.com"),
        SalesmanSeed(raw_key="NoMail", number="2", full_name="No Mail",
                     display_name="No Mail", email=""),
    ])

    class FakeDelivery:
        def __init__(self):
            self.calls = []

        def run_and_deliver(self, **kwargs):
            self.calls.append(kwargs)
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=[kwargs["recipients"]], eml_name="x.eml"),
                row_count=1,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={
            "salesman": ["MKolko", "NoMail"],
            "email_to_salesmen": True,
        }, layout={}, cadence={"freq": "daily", "time": "08:00"},
        recipients="manager@x.com")
    runner.run(mid, MASTER)

    assert len(delivery.calls) == 2  # management + MKolko only
    assert delivery.calls[1]["recipients"] == "m@x.com"
    hist = ScheduleRunRepository(db).list_for_schedule(mid, MASTER)
    assert hist[0].status == "success"
    assert "NoMail" in (hist[0].debug_log or "")
    assert "skipped" in (hist[0].debug_log or "").lower()
    meta = hist[0].output_meta or {}
    assert any(d.get("salesman") == "NoMail" and d.get("skipped") for d in meta.get("deliveries") or [])


# --- cron tick -------------------------------------------------------------

def test_tick_enqueues_due_and_dedups(tmp_path):
    from web.data.repositories.jobs import JobRepository
    from web.scheduling.tick import enqueue_due

    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    uid = UserRepository(db).upsert("rep@x.com", display_name="R", role="admin").id
    sid = ScheduleRepository(db).create(uid, "ordered", params={}, layout={},
                                        cadence={"freq": "daily", "time": "08:00"},
                                        recipients="a@x.com")
    job_repo = JobRepository(db)
    now = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)  # past 08:00 Eastern
    assert enqueue_due(db, job_repo, now) == 1
    # A second tick before the run completes collapses onto the same active job
    # (dedup at the job level), so no duplicate job is created.
    enqueue_due(db, job_repo, now)
    first = job_repo.claim_next()
    assert first is not None and first.type == "schedule.run"
    assert first.params["schedule_id"] == sid
    assert job_repo.claim_next() is None


def test_tick_skips_outside_window_and_inactive(tmp_path):
    from web.data.repositories.jobs import JobRepository
    from web.scheduling.tick import enqueue_due

    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    uid = UserRepository(db).upsert("rep@x.com", display_name="R", role="admin").id
    repo = ScheduleRepository(db)
    # ends in the past -> skipped
    repo.create(uid, "ordered", params={}, layout={},
                cadence={"freq": "daily", "time": "08:00"}, recipients="a@x.com",
                end_date="2020-01-01")
    # inactive -> skipped
    sid = repo.create(uid, "ordered", params={}, layout={},
                      cadence={"freq": "daily", "time": "08:00"}, recipients="a@x.com")
    repo.set_active(sid, uid, False)
    now = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    assert enqueue_due(db, JobRepository(db), now) == 0
