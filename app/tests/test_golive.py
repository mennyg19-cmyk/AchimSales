"""Chips, catch-up, Graph drive mock, keep cap, theme, Litestream boot, precious import."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import cadence
import catchup
import chips
import clock
import config
import drive
import store as home_store
from db import db, init_db
from import_precious import import_users
from main import create_app
from test_home import csrf_headers, login


@pytest.fixture
def home_db(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "home.sqlite"))
    monkeypatch.delenv("REPORTING_API_KEY", raising=False)
    monkeypatch.delenv("GRAPH_TENANT_ID", raising=False)
    monkeypatch.delenv("GRAPH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GRAPH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    init_db()
    return tmp_path


def test_chips_expand_subject_and_html_button():
    subject = chips.expand(
        "{Schedule} {Period} {DownloadButton}",
        schedule_name="Daily Ordered",
        period="this_week",
        download_url="https://example.com/file.xlsx",
    )
    assert subject == "Daily Ordered this week https://example.com/file.xlsx"
    button = chips.download_button_html("https://example.com/file.xlsx")
    assert "https://example.com/file.xlsx" in button
    assert "<table" in button
    assert chips.still_has_chips("{Schedule} leftover") is True
    assert chips.still_has_chips("Daily Ordered") is False


def test_filename_date_chips_are_eastern_not_api():
    when = datetime(2026, 8, 17, 22, 30, tzinfo=cadence.EASTERN)
    name = chips.expand_filename(
        "",
        schedule_name="Daily 9am",
        report_name="Ordered Report",
        when=when,
    )
    assert name == "Daily_9am_08-17-2026.xlsx"
    named = chips.expand_filename(
        "{Schedule}_{Report}_{YYYY}{MM}{DD}_{Weekday}",
        schedule_name="Daily Ordered",
        report_name="Ordered Report",
        params={"period": "last_7_days"},
        when=when,
    )
    assert named == "Daily_Ordered_Ordered_Report_20260817_Monday.xlsx"
    folder = chips.expand_folder(
        "Salesman Report/Customer Activity/{Month} {YYYY}",
        report_name="Customer Activity",
        when=when,
    )
    assert folder == "Salesman Report/Customer Activity/August 2026"
    subject = chips.expand(
        "{Schedule} {Month} {YYYY}",
        schedule_name="Daily Ordered",
        report_name="Ordered Report",
        when=when,
    )
    assert subject == "Daily Ordered August 2026"


def test_chip_math_shifts_eastern_clock():
    august = datetime(2026, 8, 17, 22, 30, tzinfo=cadence.EASTERN)
    assert chips.expand("{Month-1}", when=august) == "July"
    assert chips.expand("{{month-1}}", when=august) == "July"
    assert chips.expand("{{Month-1 YYYY}}", when=august) == "July 2026"
    assert chips.expand("{Weekday-1}", when=august) == "Sunday"
    assert chips.expand("{MM}", when=august) == "08"
    assert chips.expand("{mm}", when=august) == "30"
    assert chips.expand("{DD-1}", when=august) == "16"
    january = datetime(2026, 1, 5, 9, 0, tzinfo=cadence.EASTERN)
    assert chips.expand("{Month-1}", when=january) == "December"
    assert chips.expand("{{Month-1 YYYY}}", when=january) == "December 2025"
    folder = chips.expand_folder(
        "Salesman Report/Customer Activity/{{Month-1 YYYY}}",
        when=january,
    )
    assert folder == "Salesman Report/Customer Activity/December 2025"
    name = chips.expand_filename("{Schedule}_{Month-1}_{YYYY}", schedule_name="Daily", when=january)
    assert name == "Daily_December_2026.xlsx"


def test_clock_ready_ignores_weekday():
    cad = {"freq": "weekly", "time": "08:00", "weekdays": [4]}  # Friday
    monday = datetime(2026, 6, 22, 16, 0, tzinfo=timezone.utc)
    assert cadence.due_now(cad, None, monday) is False
    assert cadence.clock_ready(cad, "2026-06-19T16:00:00Z", monday) is True
    skipped = catchup.as_date("2026-06-19T16:00:00Z")
    assert skipped is not None
    assert catchup.classify_action({"period": "last_7_days"}, "ordered", skipped, cad) == "reschedule"
    assert catchup.makeup_due(cad, "2026-06-19T16:00:00Z", monday, action="reschedule", assur=False)


def test_clock_skip_sets_catch_up(home_db, monkeypatch):
    monkeypatch.setattr("hebcal.restriction", lambda now=None: ("assur", "Shabbos"))
    now = datetime(2026, 6, 20, 16, 0, tzinfo=timezone.utc)
    assert clock.tick(now) >= 1
    with db() as conn:
        row = conn.execute(
            "SELECT catch_up_pending, catch_up_for_date, last_status FROM schedules ORDER BY id LIMIT 1"
        ).fetchone()
    assert row["catch_up_pending"] == 1
    assert row["catch_up_for_date"] == "2026-06-20"
    assert row["last_status"] == "skipped"


def test_clock_reschedule_makeup_on_monday(home_db, monkeypatch):
    with db() as conn:
        conn.execute("UPDATE schedules SET freq = 'weekly', weekdays = 'fri', run_time = '08:00'")
        view_id = conn.execute("SELECT view_id FROM schedules ORDER BY id LIMIT 1").fetchone()[0]
        conn.execute("UPDATE views SET period = 'last_7_days' WHERE id = ?", (view_id,))
    monkeypatch.setattr("hebcal.restriction", lambda now=None: ("assur", "Shabbos"))
    friday = datetime(2026, 6, 19, 16, 0, tzinfo=timezone.utc)
    assert clock.tick(friday) >= 1
    called = []
    monkeypatch.setattr("hebcal.restriction", lambda now=None: ("ok", ""))
    monkeypatch.setattr(
        "clock.deliver_schedule",
        lambda schedule, user, at=None: called.append(schedule) or "success",
    )
    monday = datetime(2026, 6, 22, 16, 0, tzinfo=timezone.utc)
    assert clock.tick(monday) >= 1
    assert called
    assert called[0].get("catch_up_for_date") == "2026-06-19"
    with db() as conn:
        row = conn.execute("SELECT catch_up_pending FROM schedules ORDER BY id LIMIT 1").fetchone()
    assert row["catch_up_pending"] == 0


def test_sharepoint_mock_when_graph_off(home_db):
    result = drive.upload_sharepoint("Direct Reports/Ordered Report", "x.xlsx", b"PK")
    assert result["mock"] is True
    assert result["name"] == "x.xlsx"


def test_sharepoint_production_fail_closed(home_db, monkeypatch):
    monkeypatch.setattr("config.PRODUCTION", True)
    with pytest.raises(drive.DriveError):
        drive.upload_sharepoint("Ordered Report", "x.xlsx", b"PK")


def test_session_secret_accepts_flask_secret(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setenv("FLASK_SECRET", "from-live-app-setting")
    monkeypatch.setattr("config.PRODUCTION", False)
    assert config.session_secret() == "from-live-app-setting"


def test_production_refuses_missing_litestream(monkeypatch):
    monkeypatch.setattr("config.PRODUCTION", True)
    monkeypatch.setenv("SESSION_SECRET", "a-real-production-secret")
    monkeypatch.delenv("LITESTREAM_AZURE_ACCOUNT_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LITESTREAM_AZURE_ACCOUNT_KEY"):
        config.validate_boot()


def test_keep_cap_drops_oldest(home_db):
    owner = "preview@achimonline.com"
    ids = [
        home_store.save_job("invoiced", f"run {i}", {"data": {}}, owner_email=owner)
        for i in range(3)
    ]
    home_store.keep_job(ids[0], "Alpha", cap=2)
    home_store.keep_job(ids[1], "Beta", cap=2)
    home_store.keep_job(ids[2], "Gamma", cap=2)
    kept = home_store.list_jobs(kept_only=True, owner_email=owner)
    names = {row["keep_name"] for row in kept}
    assert "Gamma" in names
    assert "Beta" in names
    assert "Alpha" not in names


def test_theme_persists_on_user(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "home.sqlite"))
    with TestClient(create_app()) as client:
        login(client)
        res = client.post(
            "/api/settings/theme",
            json={"theme": "dark"},
            headers=csrf_headers(client),
        )
        assert res.json()["ok"] is True
        row = home_store.get_user("preview@achimonline.com")
        assert row["theme"] == "dark"


def test_import_precious_users(tmp_path, monkeypatch):
    dest = tmp_path / "home.sqlite"
    monkeypatch.setenv("APP_DB_PATH", str(dest))
    init_db()
    source = tmp_path / "precious.db"
    conn = sqlite3.connect(source)
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_external INTEGER NOT NULL DEFAULT 0,
            sales_group TEXT NOT NULL DEFAULT '',
            sharepoint_access INTEGER NOT NULL DEFAULT 0,
            dashboard_enabled INTEGER NOT NULL DEFAULT 0,
            test_access INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE user_preferences (
            user_id INTEGER PRIMARY KEY,
            theme TEXT NOT NULL DEFAULT 'light'
        );
        INSERT INTO users (email, display_name, role, sales_group)
        VALUES ('live.user@achimonline.com', 'Live User', 'manager', 'HKaufman');
        INSERT INTO user_preferences (user_id, theme) VALUES (1, 'dark');
        """
    )
    conn.commit()
    conn.close()
    result = import_users(source, dest)
    assert result["inserted"] == 1
    row = home_store.get_user("live.user@achimonline.com")
    assert row["role"] == "manager"
    assert row["sales_group"] == "HKaufman"
    assert row["theme"] == "dark"
    again = import_users(source, dest)
    assert again["inserted"] == 0
    assert again["skipped"] >= 1


def test_deliver_expands_chips_and_mocks_upload(home_db, monkeypatch):
    from deliver import deliver_schedule

    monkeypatch.setattr("hebcal.restriction", lambda now=None: ("ok", ""))
    with db() as conn:
        conn.execute(
            """UPDATE schedules SET subject = '{Schedule} {Period}',
               filename = '{Schedule}.xlsx', sharepoint_folder = 'Ordered Report'"""
        )
    row = home_store.get_schedule(home_store.list_schedules()[0]["id"])
    owner = home_store.get_user(row["owner_email"])
    assert deliver_schedule(row, owner) == "success"
    with db() as conn:
        out = conn.execute("SELECT subject, body FROM outbox ORDER BY id DESC LIMIT 1").fetchone()
        run = conn.execute("SELECT message FROM schedule_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert "Daily Ordered" in out["subject"]
    assert "mock://" in run["message"]
    assert "SharePoint/OneDrive upload is not Graph-wired yet" not in out["body"]
