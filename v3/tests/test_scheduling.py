"""Scheduling: cadence math + the schedule runner (build -> deliver -> record)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from web.auth.authorization import Authorization
from web.config import Config
from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.outbox import OutboxRepository
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
from web.delivery.sharepoint import TEST_SHAREPOINT_FOLDER, SharePointService
from web.scheduling import cadence as C
from web.scheduling.runner import ScheduleRunner
from web.reporting.http_client import ReportResult
from web.reporting.salesman_directory import SalesmanDirectory
from web.reporting.cache import ReportCache
from web.reporting.runner import ReportRunner


# --- salesman master stand-in (salesmen_master SP rows) ---------------------

@dataclass
class SalesmanSeed:
    raw_key: str
    number: str = ""
    full_name: str = ""
    display_name: str = ""
    email: str = ""


class _SpClient:
    configured = True

    def __init__(self, rows):
        self.rows = rows

    def run_report(self, report_id, params):
        return ReportResult(report_id=report_id, columns=[], rows=list(self.rows),
                            row_count=len(self.rows))


def _directory(seeds):
    rows = [{"Salesman": s.raw_key, "SalesmanName": s.full_name or s.display_name,
             "Email": s.email} for s in seeds]
    return SalesmanDirectory(_SpClient(rows))


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


def test_later_iso_picks_the_newer_stamp():
    older = "2026-06-01T12:00:00+00:00"
    newer = "2026-06-01T13:00:00+00:00"
    assert C.later_iso(older, newer) == newer
    assert C.later_iso(newer, None) == newer
    assert C.later_iso(None, None) is None


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


def test_runner_personal_succeeds_when_company_views_column_missing(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)

    class FakeDelivery:
        def run_and_deliver(self, **kwargs):
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=["a@x.com"], eml_name="x.eml"),
                row_count=1,
            )

    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=FakeDelivery())  # type: ignore[arg-type]
    uid = UserRepository(db).upsert("rep@x.com", display_name="Rep", role="admin").id
    sid = ScheduleRepository(db).create(
        uid, "ordered", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="a@x.com")
    with db.precious() as conn:
        try:
            conn.execute("ALTER TABLE users DROP COLUMN can_see_company_views")
        except sqlite3.OperationalError as exc:
            pytest.skip(str(exc))
    runner.run(sid, PERSONAL)
    hist = ScheduleRunRepository(db).list_for_schedule(sid, PERSONAL)
    assert len(hist) == 1 and hist[0].status == "success"


def test_runner_default_view_uses_company_layout_when_schedule_layout_empty(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.report_defaults import ReportDefaultRepository

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
    uid = UserRepository(db).upsert("rep@x.com", display_name="Rep", role="admin").id
    ReportDefaultRepository(db).upsert(
        "ordered", params={}, layout={"active": "by_item", "views": {"by_item": {"hidden": ["x"]}}},
        updated_by=uid)
    sid = ScheduleRepository(db).create(
        uid, "ordered", params={}, layout={}, cadence={"freq": "daily", "time": "08:00"},
        recipients="a@x.com", view_name="Default")
    runner.run(sid, PERSONAL)
    assert delivery.calls[0]["layout"]["active"] == "by_item"

    mid = MasterScheduleRepository(db).create(
        "ordered", "Seeded", params={}, layout={"order": ["summary"]},
        cadence={"freq": "daily", "time": "08:00"}, recipients="b@x.com",
        view_name="Default")
    runner.run(mid, MASTER)
    seeded = [c for c in delivery.calls if c.get("recipients") == "b@x.com"][0]
    assert seeded["layout"]["order"] == ["summary"]


def test_runner_company_named_view_uses_live_layout(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.company_views import CompanyViewRepository

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
    UserRepository(db).upsert("rep@x.com", display_name="Rep", role="admin")
    live = {"active": "by_customer", "views": {"by_customer": {"group": ["Salesman", "CustomerName"]}}}
    CompanyViewRepository(db).upsert(
        "ordered", "Daily Ordered", params={"period": "all_time"},
        layout=live, updated_by=None)
    mid = MasterScheduleRepository(db).create(
        "ordered", "DailyOrderReport", params={"period": "yesterday"},
        layout={"order": ["old"]}, cadence={"freq": "daily", "time": "00:00"},
        recipients="a@x.com", view_name="Daily Ordered")
    runner.run(mid, MASTER)
    assert delivery.calls[0]["layout"]["views"]["by_customer"]["group"] == [
        "Salesman", "CustomerName"]
    assert delivery.calls[0]["params"].get("period") == "yesterday"


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
    salesmen = _directory([
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
        authz=Authorization(db), delivery=delivery, salesmen=salesmen)  # type: ignore[arg-type]
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
    salesmen = _directory([
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
        authz=Authorization(db), delivery=delivery, salesmen=salesmen)  # type: ignore[arg-type]
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
    assert all(c.get("email_on_empty") is False for c in split_calls)
    hist = ScheduleRunRepository(db).list_for_schedule(mid, MASTER)
    assert hist[0].status == "success" and hist[0].rows == 3
    assert hist[0].debug_log.startswith("OK:")
    assert "manager@x.com" in hist[0].debug_log
    deliveries = (hist[0].output_meta or {}).get("deliveries") or []
    assert len(deliveries) == 3


def test_runner_split_all_fans_out_to_salesmen_with_email(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    salesmen = _directory([
        SalesmanSeed(raw_key="MKolko", number="1", full_name="M Kolko",
                     display_name="MKolko", email="m@x.com"),
        SalesmanSeed(raw_key="AGrossman", number="2", full_name="A Grossman",
                     display_name="AGrossman", email="a@x.com"),
        SalesmanSeed(raw_key="NoMail", number="3", full_name="No Mail",
                     display_name="NoMail", email=""),
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
        authz=Authorization(db), delivery=delivery, salesmen=salesmen)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Salesmen Ordered", params={
            "period": "yesterday", "split_by_salesman": True,
        }, layout={}, cadence={"freq": "daily", "time": "09:00"},
        recipients="manager@x.com")
    runner.run(mid, MASTER)

    assert delivery.calls[0]["params"] == {"period": "yesterday"}
    split = delivery.calls[1:]
    assert [c["params"]["salesman"] for c in split] == [["AGrossman"], ["MKolko"]]
    assert [c["recipients"] for c in split] == ["a@x.com", "m@x.com"]
    assert all(c.get("email_on_empty") is False for c in split)


def test_runner_empty_split_sends_no_data_notice_not_workbook(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    salesmen = _directory([
        SalesmanSeed(raw_key="MKolko", number="1", full_name="M Kolko",
                     display_name="M Kolko", email="m@x.com"),
    ])

    class FakeDelivery:
        def __init__(self):
            self.calls = []
            self.notices = []

        def run_and_deliver(self, **kwargs):
            self.calls.append(kwargs)
            rows = 0 if kwargs.get("params", {}).get("salesman") else 5
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=[kwargs["recipients"]], eml_name="x.eml"),
                row_count=rows,
            )

        def send_no_data_notice(self, **kwargs):
            self.notices.append(kwargs)
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=[kwargs["recipients"]], eml_name="n.eml"),
                row_count=0,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery, salesmen=salesmen)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Salesmen Ordered", params={
            "period": "yesterday", "split_by_salesman": True,
        }, layout={}, cadence={"freq": "daily", "time": "09:00"},
        recipients="manager@x.com")
    runner.run(mid, MASTER)

    assert len(delivery.calls) == 2
    assert delivery.calls[1].get("email_on_empty") is False
    assert len(delivery.notices) == 1
    notice = delivery.notices[0]
    assert "No Data Found" in notice["subject"]
    assert "yesterday" in notice["subject"]
    assert "No data for this salesman" in notice["body_text"]
    assert "mkolko" in notice["body_text"].lower()
    hist = ScheduleRunRepository(db).list_for_schedule(mid, MASTER)
    assert hist[0].status == "success"


def test_runner_master_skips_salesman_without_email_without_failing_run(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    salesmen = _directory([
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
        authz=Authorization(db), delivery=delivery, salesmen=salesmen)  # type: ignore[arg-type]
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


def test_runner_master_test_mode_redirects_and_skips_sharepoint(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.app_settings import AppSettingsRepository
    AppSettingsRepository(db).set_schedule_test(
        enabled=True, emails=["menny@x.com", "other@x.com"])

    class FakeDelivery:
        def __init__(self):
            self.calls = []

        def run_and_deliver(self, **kwargs):
            self.calls.append(kwargs)
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=["menny@x.com", "other@x.com"], eml_name="x.eml"),
                row_count=2,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "DailyInvoicedReport", params={"email_cc": "cc@x.com"}, layout={},
        cadence={"freq": "daily", "time": "05:00"}, recipients="customers@x.com",
        sharepoint_path="Direct Reports/Invoiced Report/Daily")
    runner.run(mid, MASTER)
    assert len(delivery.calls) == 1
    call = delivery.calls[0]
    assert call["recipients"] == "menny@x.com; other@x.com"
    assert call["sharepoint_path"] == TEST_SHAREPOINT_FOLDER
    assert call["onedrive_user"] == ""
    assert call["cc_raw"] == ""
    assert call["subject"].startswith("[TEST] ")


def test_runner_personal_test_mode_redirects_and_skips_onedrive(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.app_settings import AppSettingsRepository
    AppSettingsRepository(db).set_schedule_test(enabled=True, emails=["menny@x.com"])
    uid = UserRepository(db).upsert("rep@x.com", display_name="Rep", role="admin").id

    class FakeDelivery:
        def __init__(self):
            self.calls = []

        def run_and_deliver(self, **kwargs):
            self.calls.append(kwargs)
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=["menny@x.com"], eml_name="x.eml"),
                row_count=1,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)  # type: ignore[arg-type]
    sid = ScheduleRepository(db).create(
        uid, "ordered", params={}, layout={}, cadence={"freq": "daily", "time": "08:00"},
        recipients="real@x.com", sharepoint_path="Personal/Reports")
    runner.run(sid, PERSONAL)
    call = delivery.calls[0]
    assert call["recipients"] == "menny@x.com"
    assert call["subject"].startswith("[TEST] ")
    assert call["onedrive_user"] == ""
    assert call["sharepoint_path"] == TEST_SHAREPOINT_FOLDER
    assert "real@x.com" not in str(delivery.calls)


def test_runner_personal_named_view_uses_live_period_not_stale_schedule(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.saved_reports import SavedReportRepository

    uid = UserRepository(db).upsert("avig@x.com", display_name="Avig", role="salesman").id
    SavedReportRepository(db).create(
        uid, "invoiced", "Yesterday invoiced", {"period": "yesterday"}, {})

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
    sid = ScheduleRepository(db).create(
        uid, "invoiced",
        params={"period": "all_time", "email_on_no_data": True, "folder_kind": "onedrive"},
        layout={}, cadence={"freq": "daily", "time": "08:00"},
        recipients="avig@x.com", view_name="Yesterday invoiced")
    runner.run(sid, PERSONAL)
    params = delivery.calls[0]["params"]
    assert params.get("period") == "yesterday"
    assert "all_time" not in str(params)
    assert delivery.calls[0]["email_on_empty"] is True


def test_runner_does_not_take_cc_from_live_saved_view(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.saved_reports import SavedReportRepository

    uid = UserRepository(db).upsert("avig@x.com", display_name="Avig", role="salesman").id
    SavedReportRepository(db).create(
        uid, "invoiced", "Yesterday invoiced",
        {"period": "yesterday", "email_cc": "sneak@x.com"}, {})

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
    sid = ScheduleRepository(db).create(
        uid, "invoiced",
        params={"period": "all_time", "email_on_no_data": True},
        layout={}, cadence={"freq": "daily", "time": "08:00"},
        recipients="avig@x.com", view_name="Yesterday invoiced")
    runner.run(sid, PERSONAL)
    call = delivery.calls[0]
    assert call["params"].get("period") == "yesterday"
    assert not (call["params"].get("email_cc") or "")
    assert (call.get("cc_raw") or "") == ""


def test_runner_personal_company_view_uses_live_period_not_stale_schedule(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.company_views import CompanyViewRepository

    uid = UserRepository(db).upsert("admin@x.com", display_name="Admin", role="admin").id
    CompanyViewRepository(db).upsert(
        "ordered", "Daily Ordered", params={"period": "yesterday"}, layout={},
        updated_by=uid)

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
    sid = ScheduleRepository(db).create(
        uid, "ordered",
        params={"period": "all_time", "email_on_no_data": True, "folder_kind": "onedrive"},
        layout={}, cadence={"freq": "daily", "time": "08:00"},
        recipients="admin@x.com", view_name="Daily Ordered")
    runner.run(sid, PERSONAL)
    params = delivery.calls[0]["params"]
    assert params.get("period") == "yesterday"
    assert "all_time" not in str(params)


def test_runner_company_view_schedule_ignores_same_named_personal_view(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.company_views import CompanyViewRepository
    from web.data.repositories.saved_reports import SavedReportRepository

    uid = UserRepository(db).upsert("admin@x.com", display_name="Admin", role="admin").id
    CompanyViewRepository(db).upsert(
        "ordered", "Collision", params={"period": "yesterday"}, layout={},
        updated_by=uid)
    SavedReportRepository(db).create(
        uid, "ordered", "Collision", {"period": "all_time"}, {})

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
    sid = ScheduleRepository(db).create(
        uid, "ordered",
        params={"view_source": "company", "email_on_no_data": True},
        layout={}, cadence={"freq": "daily", "time": "08:00"},
        recipients="admin@x.com", view_name="Collision")
    runner.run(sid, PERSONAL)
    params = delivery.calls[0]["params"]
    assert params.get("period") == "yesterday"


def test_runner_personal_layout_ignores_same_named_company_view(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.company_views import CompanyViewRepository
    from web.data.repositories.saved_reports import SavedReportRepository

    uid = UserRepository(db).upsert("admin@x.com", display_name="Admin", role="admin").id
    CompanyViewRepository(db).upsert(
        "ordered", "Collision", params={"period": "yesterday"},
        layout={"order": ["company-only"]}, updated_by=uid)
    SavedReportRepository(db).create(
        uid, "ordered", "Collision", {"period": "all_time"},
        {"order": ["personal-only"]})

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
    personal_sid = ScheduleRepository(db).create(
        uid, "ordered",
        params={"email_on_no_data": True, "folder_kind": "onedrive"},
        layout={"order": ["personal-only"]}, cadence={"freq": "daily", "time": "08:00"},
        recipients="admin@x.com", view_name="Collision")
    runner.run(personal_sid, PERSONAL)
    assert delivery.calls[-1]["layout"] == {"order": ["personal-only"]}
    company_sid = ScheduleRepository(db).create(
        uid, "ordered",
        params={"view_source": "company", "email_on_no_data": True, "folder_kind": "onedrive"},
        layout={"order": ["stale"]}, cadence={"freq": "daily", "time": "08:00"},
        recipients="admin@x.com", view_name="Collision")
    runner.run(company_sid, PERSONAL)
    assert delivery.calls[-1]["layout"] == {"order": ["company-only"]}


def test_runner_personal_filename_uses_view_name_not_report_title(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)

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
    uid = UserRepository(db).upsert("avig@x.com", display_name="Avig", role="salesman").id
    sid = ScheduleRepository(db).create(
        uid, "invoiced", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"},
        recipients="avig@x.com", view_name="Yesterday invoiced",
        filename_template="{Schedule}_{Period}")
    runner.run(sid, PERSONAL)
    call = delivery.calls[0]
    assert call["filename_template"] == "{Schedule}_{Period}"
    assert call["schedule_name"] == "Yesterday invoiced"
    assert call["report_name"] != call["schedule_name"]


def test_runner_test_mode_on_without_emails_fails(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.app_settings import AppSettingsRepository
    settings = AppSettingsRepository(db)
    settings.set_schedule_test(enabled=True, emails=["menny@x.com"])
    with db.precious() as conn:
        conn.execute("UPDATE app_settings SET value='1' WHERE key='schedule_test_mode'")
        conn.execute("UPDATE app_settings SET value='[]' WHERE key='schedule_test_emails'")
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=object())  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="team@x.com")
    with pytest.raises(RuntimeError, match="no test emails"):
        runner.run(mid, MASTER)
    hist = ScheduleRunRepository(db).list_for_schedule(mid, MASTER)
    assert hist[0].status == "failure"
    uid = UserRepository(db).upsert("rep@x.com", display_name="Rep", role="admin").id
    sid = ScheduleRepository(db).create(
        uid, "ordered", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="real@x.com")
    with pytest.raises(RuntimeError, match="no test emails"):
        runner.run(sid, PERSONAL)


def test_runner_test_mode_fans_out_splits_to_test_list(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.app_settings import AppSettingsRepository
    AppSettingsRepository(db).set_schedule_test(enabled=True, emails=["menny@x.com"])
    salesmen = _directory([
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
                result=DeliveryResult(ok=True, recipients=["menny@x.com"], eml_name="x.eml"),
                row_count=1,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery, salesmen=salesmen)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={"email_salesman_keys": ["MKolko", "AGrossman"]},
        layout={}, cadence={"freq": "daily", "time": "08:00"}, recipients="manager@x.com",
        sharepoint_path="Direct Reports/Salesman Report/Daily")
    runner.run(mid, MASTER)
    assert len(delivery.calls) == 3
    assert all(c["recipients"] == "menny@x.com" for c in delivery.calls)
    assert delivery.calls[0]["sharepoint_path"] == TEST_SHAREPOINT_FOLDER
    assert all(c["sharepoint_path"] == "" for c in delivery.calls[1:])
    assert delivery.calls[0]["subject"].startswith("[TEST] ")
    assert delivery.calls[0]["params"] == {}
    assert [c["params"].get("salesman") for c in delivery.calls[1:]] == [["MKolko"], ["AGrossman"]]
    assert delivery.calls[1]["subject"].endswith(" - MKolko")
    assert delivery.calls[1]["schedule_name"] == "Nightly - MKolko"
    assert "m@x.com" not in str(delivery.calls)
    assert "a@x.com" not in str(delivery.calls)
    assert "manager@x.com" not in str([c["recipients"] for c in delivery.calls])


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


def test_tick_skips_shabbos_and_catches_up_after(tmp_path, monkeypatch):
    from web.data.repositories.jobs import JobRepository
    from web.scheduling import tick as tick_mod
    from web.scheduling.tick import enqueue_due

    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    mid = MasterScheduleRepository(db).create(
        "ordered", "DailyInvoicedReport", params={"period": "yesterday"}, layout={},
        cadence={"freq": "daily", "time": "05:00"}, recipients="team@x.com")
    job_repo = JobRepository(db)
    now = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(tick_mod, "melacha_assur", lambda _now=None: (True, "Shabbos"))
    assert enqueue_due(db, job_repo, now) == 0
    assert job_repo.claim_next() is None
    hist = ScheduleRunRepository(db).list_for_schedule(mid, MASTER)
    assert hist[0].status == "skipped"
    assert "Shabbos" in (hist[0].debug_log or "")
    assert MasterScheduleRepository(db).get(mid).catch_up_pending is True

    monkeypatch.setattr(tick_mod, "melacha_assur", lambda _now=None: (False, ""))
    assert enqueue_due(db, job_repo, now) == 0
    assert job_repo.claim_next() is None
    assert MasterScheduleRepository(db).get(mid).catch_up_pending is True
    assert MasterScheduleRepository(db).get(mid).catch_up_for_date == "2026-06-01"

    nxt = datetime(2026, 6, 2, 13, 0, tzinfo=timezone.utc)
    assert enqueue_due(db, job_repo, nxt) == 1
    job = job_repo.claim_next()
    assert job is not None and job.params["schedule_id"] == mid
    assert job.params["catch_up_for_date"] == "2026-06-01"
    assert MasterScheduleRepository(db).get(mid).catch_up_pending is False


def test_tick_run_now_style_enqueue_still_works_when_restricted(tmp_path, monkeypatch):
    from web.data.repositories.jobs import JobRepository
    from web.scheduling import tick as tick_mod
    from web.scheduling.jobs import enqueue_schedule_run
    from web.scheduling.tick import enqueue_due

    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    monkeypatch.setattr(tick_mod, "melacha_assur", lambda _now=None: (True, "Shabbos"))
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "05:00"}, recipients="team@x.com")
    job_repo = JobRepository(db)
    now = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    assert enqueue_due(db, job_repo, now) == 0
    enqueue_schedule_run(job_repo, schedule_id=mid, schedule_type=MASTER,
                         ignore_sabbath=True)
    job = job_repo.claim_next()
    assert job is not None and job.params["ignore_sabbath"] is True


def test_manual_run_now_is_not_deduped_and_does_not_eat_the_clock(tmp_path):
    from web.data.repositories.jobs import JobRepository
    from web.scheduling.jobs import enqueue_schedule_run
    from web.scheduling.tick import enqueue_due

    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "05:00"}, recipients="team@x.com")

    class FakeDelivery:
        def run_and_deliver(self, **kwargs):
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=["team@x.com"], eml_name="x.eml"),
                row_count=1,
            )

    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=FakeDelivery())  # type: ignore[arg-type]
    runner.run(mid, MASTER, manual=True)
    runs = ScheduleRunRepository(db)
    assert runs.last_run_at(mid, MASTER) is None
    assert runs.list_for_schedule(mid, MASTER)[0].output_meta.get("manual") is True

    job_repo = JobRepository(db)
    first = enqueue_schedule_run(job_repo, schedule_id=mid, schedule_type=MASTER, manual=True)
    second = enqueue_schedule_run(job_repo, schedule_id=mid, schedule_type=MASTER, manual=True)
    assert first != second
    now = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    assert enqueue_due(db, job_repo, now) == 1


def test_tick_mtd_friday_skip_waits_until_monday_same_clock(tmp_path, monkeypatch):
    from web.data.repositories.jobs import JobRepository
    from web.scheduling import tick as tick_mod
    from web.scheduling.tick import enqueue_due

    eastern = ZoneInfo("America/New_York")
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    mid = MasterScheduleRepository(db).create(
        "ordered", "MTD 10pm", params={"period": "mtd"}, layout={},
        cadence={"freq": "daily", "time": "22:00"}, recipients="team@x.com")
    job_repo = JobRepository(db)
    monkeypatch.setattr(tick_mod, "melacha_assur", lambda _now=None: (True, "Shabbos"))
    friday = datetime(2026, 1, 30, 22, 5, tzinfo=eastern)
    assert enqueue_due(db, job_repo, friday) == 0
    row = MasterScheduleRepository(db).get(mid)
    assert row.catch_up_pending is True and row.catch_up_for_date == "2026-01-30"

    monkeypatch.setattr(tick_mod, "melacha_assur", lambda _now=None: (False, ""))
    saturday_night = datetime(2026, 1, 31, 22, 5, tzinfo=eastern)
    assert enqueue_due(db, job_repo, saturday_night) == 0
    sunday = datetime(2026, 2, 1, 22, 5, tzinfo=eastern)
    assert enqueue_due(db, job_repo, sunday) == 0
    monday = datetime(2026, 2, 2, 22, 5, tzinfo=eastern)
    assert enqueue_due(db, job_repo, monday) == 1
    job = job_repo.claim_next()
    assert job is not None
    assert job.params["catch_up_for_date"] == "2026-01-30"
    assert job.params["include_regular"] is True


def test_runner_mtd_catch_up_sends_skipped_day_and_month_end(tmp_path, monkeypatch):
    from web.scheduling import runner as runner_mod

    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)

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
    monkeypatch.setattr(runner_mod, "melacha_assur", lambda _now=None: (False, ""))
    mid = MasterScheduleRepository(db).create(
        "ordered", "MTD 10pm", params={"period": "mtd"}, layout={},
        cadence={"freq": "daily", "time": "22:00"}, recipients="team@x.com")
    monkeypatch.setattr(runner_mod.C, "eastern_date_iso", lambda _now=None: "2026-02-02")
    runner.run(mid, MASTER, catch_up_for_date="2026-01-30", include_regular=True)
    periods = [(c["params"].get("period"), c["params"].get("end_date")) for c in delivery.calls]
    assert periods == [
        ("custom", "2026-01-30"),
        ("custom", "2026-01-31"),
        ("mtd", None),
    ]
    assert "2026-01-30" in delivery.calls[0]["schedule_name"]
    assert "2026-01-31" in delivery.calls[1]["schedule_name"]


def test_clock_ready_ignores_weekday():
    cad = {"freq": "weekly", "time": "22:00", "weekdays": [4]}  # Friday
    monday_clock = datetime(2026, 2, 3, 3, 5, tzinfo=timezone.utc)  # Mon 22:05 EST
    assert C.clock_ready(cad, "2026-01-30T22:05:00-05:00", monday_clock) is True
    assert C.due_now(cad, "2026-01-30T22:05:00-05:00", monday_clock) is False


def test_next_matching_date_skips_to_next_friday():
    cad = {"freq": "weekly", "time": "22:00", "weekdays": [4]}
    assert C.next_matching_date(cad, date(2026, 1, 31)) == date(2026, 2, 6)


def test_already_on_overdue_schedule_still_catch_up_fires(tmp_path):
    from web.data.repositories.jobs import JobRepository
    from web.scheduling.tick import enqueue_due

    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="team@x.com")
    now = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    assert enqueue_due(db, JobRepository(db), now) == 1


def test_hold_until_next_slot_stops_same_day_catch_up(tmp_path):
    from web.data.repositories.jobs import JobRepository
    from web.scheduling.tick import enqueue_due, hold_until_next_slot

    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="team@x.com")
    now = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    sched = MasterScheduleRepository(db).get(mid)
    assert hold_until_next_slot(
        MasterScheduleRepository(db), ScheduleRunRepository(db), sched, MASTER, now,
    ) is True
    assert enqueue_due(db, JobRepository(db), now) == 0
    later = datetime(2026, 6, 2, 13, 0, tzinfo=timezone.utc)
    assert enqueue_due(db, JobRepository(db), later) == 1


def test_hold_before_slot_still_fires_when_time_arrives(tmp_path):
    from web.data.repositories.jobs import JobRepository
    from web.scheduling.tick import enqueue_due, hold_until_next_slot

    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="team@x.com")
    morning = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    after = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    sched = MasterScheduleRepository(db).get(mid)
    assert hold_until_next_slot(
        MasterScheduleRepository(db), ScheduleRunRepository(db), sched, MASTER, morning,
    ) is False
    assert enqueue_due(db, JobRepository(db), morning) == 0
    assert enqueue_due(db, JobRepository(db), after) == 1


def test_runner_failure_holds_fail_mail_until_flush(tmp_path, monkeypatch):
    monkeypatch.setattr("web.scheduling.runner._TRANSIENT_RETRY_WAIT_S", 0)
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.app_settings import AppSettingsRepository
    AppSettingsRepository(db).set_schedule_test(enabled=False, emails=["menny@x.com"])

    class FakeEmail:
        def __init__(self):
            self.notices = []

        def send_notice(self, **kwargs):
            self.notices.append(kwargs)

    class FakeDelivery:
        def __init__(self):
            self.email = FakeEmail()

        def run_and_deliver(self, **kwargs):
            return DeliveryOutcome(
                result=DeliveryResult(ok=False, error="SharePoint dropped"),
                row_count=0,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="team@x.com")
    from web.jobs.trace import bind, step, unbind

    class _LogSink:
        def append_log(self, job_id, entry):
            return None

        def get(self, job_id):
            return None

    bind("job-fail-1", _LogSink())
    step("api", "Reporting API POST ordered")
    try:
        with pytest.raises(RuntimeError, match="SharePoint dropped"):
            runner.run(mid, MASTER, job_id="job-fail-1")
    finally:
        unbind()
    failed = ScheduleRunRepository(db).list_for_schedule(mid, MASTER)[0]
    assert failed.output_meta.get("job_id") == "job-fail-1"
    log = failed.output_meta.get("job_log") or []
    assert log and log[0]["step"] == "api"
    assert delivery.email.notices == []
    assert runner.flush_pending_fail_notices(wait_s=0) == 1
    assert delivery.email.notices == [{
        "to": ["menny@x.com"],
        "subject": "[FAIL] Nightly",
        "body_text": (
            "Company schedule failed.\n\n"
            "Schedule: Nightly\n"
            "Report: ordered\n"
            "Error: SharePoint dropped\n"
        ),
    }]


def test_runner_failure_notice_does_not_hide_original_error(tmp_path, monkeypatch):
    monkeypatch.setattr("web.scheduling.runner._TRANSIENT_RETRY_WAIT_S", 0)
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.app_settings import AppSettingsRepository
    AppSettingsRepository(db).set_schedule_test(enabled=True, emails=["menny@x.com"])

    class FakeEmail:
        def send_notice(self, **kwargs):
            raise RuntimeError("mail down")

    class FakeDelivery:
        email = FakeEmail()

        def run_and_deliver(self, **kwargs):
            return DeliveryOutcome(
                result=DeliveryResult(ok=False, error="SharePoint dropped"),
                row_count=0,
            )

    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=FakeDelivery())  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="team@x.com")
    with pytest.raises(RuntimeError, match="SharePoint dropped"):
        runner.run(mid, MASTER)
    runner.flush_pending_fail_notices(wait_s=0)


def test_runner_retries_once_then_succeeds_without_fail_mail(tmp_path, monkeypatch):
    monkeypatch.setattr("web.scheduling.runner._TRANSIENT_RETRY_WAIT_S", 0)
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.app_settings import AppSettingsRepository
    AppSettingsRepository(db).set_schedule_test(enabled=False, emails=["menny@x.com"])

    class FakeEmail:
        def __init__(self):
            self.notices = []

        def send_notice(self, **kwargs):
            self.notices.append(kwargs)

    class FakeDelivery:
        def __init__(self):
            self.calls = 0
            self.kwargs = []
            self.email = FakeEmail()

        def run_and_deliver(self, **kwargs):
            self.calls += 1
            self.kwargs.append(kwargs)
            if self.calls == 1:
                return DeliveryOutcome(
                    result=DeliveryResult(ok=False, error="SharePoint dropped"),
                    row_count=0,
                )
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=["team@x.com"], eml_name="x.eml"),
                row_count=1,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="team@x.com")
    runner.run(mid, MASTER)
    hist = ScheduleRunRepository(db).list_for_schedule(mid, MASTER)
    assert delivery.calls == 2
    assert len(hist) == 1 and hist[0].status == "success"
    assert delivery.email.notices == []
    sent = delivery.kwargs[1]
    assert "retried after a failure" in sent["subject"]
    assert "SharePoint dropped" in sent["body_text"]
    assert "retried and succeeded" in sent["body_text"]


def test_runner_does_not_resend_when_mail_already_went_out(tmp_path, monkeypatch):
    monkeypatch.setattr("web.scheduling.runner._TRANSIENT_RETRY_WAIT_S", 0)
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.app_settings import AppSettingsRepository
    AppSettingsRepository(db).set_schedule_test(enabled=True, emails=["menny@x.com"])

    class FakeEmail:
        def __init__(self):
            self.notices = []

        def send_notice(self, **kwargs):
            self.notices.append(kwargs)

    class FakeDelivery:
        def __init__(self):
            self.calls = 0
            self.email = FakeEmail()

        def run_and_deliver(self, **kwargs):
            self.calls += 1
            return DeliveryOutcome(
                result=DeliveryResult(
                    ok=False, error="SharePoint upload failed",
                    recipients=["menny@x.com"], sent_via_smtp=True,
                    send_channel="graph",
                ),
                row_count=1,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"},
        recipients="customers@x.com",
        sharepoint_path="Direct Reports/Invoiced Report/Daily")
    runner.run(mid, MASTER)
    assert delivery.calls == 1
    assert delivery.email.notices == []
    hist = ScheduleRunRepository(db).list_for_schedule(mid, MASTER)
    assert hist[0].status == "success"


def test_recovered_run_skips_when_already_sent_today(tmp_path, monkeypatch):
    monkeypatch.setattr("web.scheduling.runner._TRANSIENT_RETRY_WAIT_S", 0)
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)

    class FakeDelivery:
        def __init__(self):
            self.calls = 0

        def run_and_deliver(self, **kwargs):
            self.calls += 1
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=["team@x.com"], eml_name="x.eml"),
                row_count=1,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="team@x.com")
    runner.run(mid, MASTER)
    assert delivery.calls == 1
    runner.run(mid, MASTER, recovered=True)
    assert delivery.calls == 1
    hist = ScheduleRunRepository(db).list_for_schedule(mid, MASTER)
    assert [row.status for row in hist] == ["skipped", "success"]
    runner.run(mid, MASTER)
    assert delivery.calls == 2
    runner.run(mid, MASTER, recovered=True, manual=True)
    assert delivery.calls == 3


def test_recovered_run_notes_retry_when_not_already_sent(tmp_path, monkeypatch):
    monkeypatch.setattr("web.scheduling.runner._TRANSIENT_RETRY_WAIT_S", 0)
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)

    class FakeDelivery:
        def __init__(self):
            self.sent = []

        def run_and_deliver(self, **kwargs):
            self.sent.append(kwargs)
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=["team@x.com"], eml_name="x.eml"),
                row_count=1,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="team@x.com")
    runner.run(mid, MASTER, recovered=True)
    assert len(delivery.sent) == 1
    assert "retried after a failure" in delivery.sent[0]["subject"]
    assert "earlier worker run failed" in delivery.sent[0]["body_text"]


def test_later_success_after_failure_skips_fail_mail(tmp_path, monkeypatch):
    monkeypatch.setattr("web.scheduling.runner._TRANSIENT_RETRY_WAIT_S", 0)
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.app_settings import AppSettingsRepository
    AppSettingsRepository(db).set_schedule_test(enabled=False, emails=["menny@x.com"])

    class FakeEmail:
        def __init__(self):
            self.notices = []

        def send_notice(self, **kwargs):
            self.notices.append(kwargs)

    class FakeDelivery:
        def __init__(self):
            self.calls = 0
            self.kwargs = []
            self.email = FakeEmail()

        def run_and_deliver(self, **kwargs):
            self.calls += 1
            self.kwargs.append(kwargs)
            if self.calls <= 2:
                return DeliveryOutcome(
                    result=DeliveryResult(ok=False, error="SharePoint dropped"),
                    row_count=0,
                )
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=["team@x.com"], eml_name="x.eml"),
                row_count=1,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="team@x.com")
    with pytest.raises(RuntimeError, match="SharePoint dropped"):
        runner.run(mid, MASTER)
    assert delivery.email.notices == []
    runner.run(mid, MASTER)
    assert delivery.email.notices == []
    sent = delivery.kwargs[-1]
    assert "retried after a failure" in sent["subject"]
    assert "earlier run of this schedule failed today" in sent["body_text"]
    assert runner.flush_pending_fail_notices(wait_s=0) == 0
    assert delivery.email.notices == []


def test_catchup_window_fail_then_regular_success_is_one_mail(tmp_path, monkeypatch):
    monkeypatch.setattr("web.scheduling.runner._TRANSIENT_RETRY_WAIT_S", 0)
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    from web.data.repositories.app_settings import AppSettingsRepository
    AppSettingsRepository(db).set_schedule_test(enabled=False, emails=["menny@x.com"])

    class FakeEmail:
        def __init__(self):
            self.notices = []

        def send_notice(self, **kwargs):
            self.notices.append(kwargs)

    class FakeDelivery:
        def __init__(self):
            self.calls = 0
            self.kwargs = []
            self.email = FakeEmail()

        def run_and_deliver(self, **kwargs):
            self.calls += 1
            self.kwargs.append(kwargs)
            if self.calls <= 2:
                return DeliveryOutcome(
                    result=DeliveryResult(ok=False, error="catch-up boom"),
                    row_count=0,
                )
            return DeliveryOutcome(
                result=DeliveryResult(ok=True, recipients=["team@x.com"], eml_name="x.eml"),
                row_count=1,
            )

    delivery = FakeDelivery()
    runner = ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery)  # type: ignore[arg-type]
    mid = MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={"period": "mtd"}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="team@x.com")
    runner.run(mid, MASTER, catch_up_for_date="2026-01-30")
    assert delivery.calls >= 3
    assert delivery.email.notices == []
    hist = ScheduleRunRepository(db).list_for_schedule(mid, MASTER)
    assert hist[0].status == "success"
    assert "later window succeeded" in (hist[0].debug_log or "")
    success_sends = [
        k for k in delivery.kwargs if "retried after a failure" in k.get("subject", "")
    ]
    assert success_sends
    assert "catch-up boom" in success_sends[0]["body_text"]
    assert runner.flush_pending_fail_notices(wait_s=0) == 0


def test_tick_flushes_pending_fail_notices(tmp_path):
    from web.data.repositories.jobs import JobRepository
    from web.scheduling.tick import make_tick

    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    flushed = []

    class FakeRunner:
        def flush_pending_fail_notices(self):
            flushed.append(1)
            return 0

    make_tick(db, JobRepository(db), FakeRunner())()
    assert flushed == [1]


def test_schedulable_view_rules():
    from web.data.repositories.saved_reports import SavedReport
    from web.scheduling.personal_views import is_custom_date_params, is_schedulable_saved_view

    def preset(**kw):
        base = dict(id=1, user_id=1, report_key="ordered", name="Last month",
                    params={"period": "last_month"}, layout={}, created_at="")
        base.update(kw)
        return SavedReport(**base)

    assert is_schedulable_saved_view(preset())
    assert not is_schedulable_saved_view(preset(name="Default"))
    assert is_schedulable_saved_view(preset(
        report_key="customer_activity", name="My activity", params={}))
    assert not is_schedulable_saved_view(preset(
        report_key="customer_activity", name="Default", params={}))
    assert is_custom_date_params({"period": "custom"})
    assert is_custom_date_params({"from": "2026-01-01", "to": "2026-01-31"})
    assert not is_custom_date_params({"period": "last_month", "from": "x", "to": "y"})
    assert not is_schedulable_saved_view(preset(params={"period": "custom"}))


def test_convert_personal_schedules_snapshots_default_and_strips_extras(stack):
    db, _runner = stack
    from web.data.repositories.saved_reports import SavedReportRepository
    from web.scheduling.personal_views import convert_personal_schedules, is_schedulable_saved_view

    users = UserRepository(db)
    uid = users.upsert("rep@x.com", display_name="Rep", role="salesman").id
    sid = ScheduleRepository(db).create(
        uid, "ordered", params={"period": "last_month"}, layout={"order": ["summary"]},
        cadence={"freq": "daily", "time": "08:00"},
        recipients="a@x.com, extra@x.com", view_name="Default")
    mid = MasterScheduleRepository(db).create(
        "ordered", "Office nightly", params={}, layout={},
        cadence={"freq": "daily", "time": "06:00"}, recipients="team@x.com")
    assert convert_personal_schedules(db) == 1
    row = ScheduleRepository(db).get(sid, uid)
    assert row.view_name != "Default"
    assert row.recipients == "rep@x.com"
    saved = SavedReportRepository(db).get_by_name(uid, "ordered", row.view_name)
    assert saved is not None and is_schedulable_saved_view(saved)
    assert convert_personal_schedules(db) == 0
    master = MasterScheduleRepository(db).get(mid)
    assert master.view_name == "Default"
    assert master.recipients == "team@x.com"


def test_convert_keeps_custom_date_view_off_picker(stack):
    db, _runner = stack
    from web.data.repositories.saved_reports import SavedReportRepository
    from web.scheduling.personal_views import convert_personal_schedules, is_schedulable_saved_view

    users = UserRepository(db)
    uid = users.upsert("admin@x.com", display_name="Admin", role="admin").id
    sid = ScheduleRepository(db).create(
        uid, "ordered",
        params={"from": "2026-01-01", "to": "2026-01-31"}, layout={},
        cadence={"freq": "daily", "time": "08:00"},
        recipients="admin@x.com", view_name="Default")
    convert_personal_schedules(db)
    row = ScheduleRepository(db).get(sid, uid)
    saved = SavedReportRepository(db).get_by_name(uid, "ordered", row.view_name)
    assert saved is not None
    assert not is_schedulable_saved_view(saved)


