"""Chips, catch-up, Graph drive mock, keep cap, theme, Litestream boot, precious import."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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


def test_format_stamp_eastern_short():
    assert cadence.format_stamp(None) == "never"
    assert cadence.format_stamp("2026-09-02T16:30:19.512041+00:00") == "2026-09-02 12:30"


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
    assert home_store.get_user("preview@achimonline.com") is None
    assert home_store.get_user("manager@achimonline.com") is None
    assert home_store.get_user("salesman@achimonline.com") is None
    assert home_store.get_user("external@example.com") is None
    again = import_users(source, dest)
    assert again["inserted"] == 0
    assert again["skipped"] >= 1


def test_purge_dummy_people_keeps_live_users(tmp_path, monkeypatch):
    dest = tmp_path / "home.sqlite"
    monkeypatch.setenv("APP_DB_PATH", str(dest))
    init_db()
    home_store.add_user("avig@achimonline.com", "Avi", "admin", 0, "")
    home_store.add_user("loopa-reviewer@local.test", "LoopA", "salesman", 0, "")
    home_store.set_setting("schedule_test_mode", "1")
    from db import db, purge_dummy_people

    with db() as conn:
        removed = purge_dummy_people(conn)
    assert removed >= 5
    assert home_store.get_user("avig@achimonline.com") is not None
    assert home_store.get_user("preview@achimonline.com") is None
    assert home_store.get_user("loopa-reviewer@local.test") is None
    assert home_store.setting("schedule_test_mode") == "0"


def test_purge_turns_off_empty_test_mode(tmp_path, monkeypatch):
    dest = tmp_path / "home.sqlite"
    monkeypatch.setenv("APP_DB_PATH", str(dest))
    init_db()
    from db import db, purge_dummy_people

    with db() as conn:
        purge_dummy_people(conn)
    home_store.set_setting("schedule_test_mode", "1")
    home_store.set_setting("test_emails", "")
    with db() as conn:
        purge_dummy_people(conn)
    assert home_store.setting("schedule_test_mode") == "0"


def test_import_precious_normalized_views_and_schedules(tmp_path, monkeypatch):
    from import_precious import import_precious

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
            handle TEXT
        );
        CREATE TABLE views (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            report_key TEXT NOT NULL,
            name TEXT NOT NULL,
            owner_handle TEXT,
            period TEXT,
            start_date TEXT,
            end_date TEXT,
            year TEXT,
            mode TEXT,
            active_tab_key TEXT
        );
        CREATE TABLE view_salesmen (
            view_id TEXT NOT NULL,
            salesman TEXT NOT NULL
        );
        CREATE TABLE view_statuses (
            view_id TEXT NOT NULL,
            status TEXT NOT NULL
        );
        CREATE TABLE layout_tabs (
            id TEXT PRIMARY KEY,
            view_id TEXT NOT NULL,
            tab_key TEXT NOT NULL,
            position INTEGER,
            clone_of_tab_key TEXT,
            tab_name TEXT,
            has_view INTEGER NOT NULL DEFAULT 0,
            groups_explicit INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE layout_tab_groups (
            tab_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            column_name TEXT NOT NULL
        );
        CREATE TABLE layout_tab_sorters (
            tab_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            column_name TEXT NOT NULL,
            dir TEXT NOT NULL
        );
        CREATE TABLE layout_columns (
            tab_id TEXT NOT NULL,
            field TEXT NOT NULL,
            position INTEGER,
            hidden INTEGER NOT NULL DEFAULT 0,
            frozen INTEGER NOT NULL DEFAULT 0,
            width REAL
        );
        CREATE TABLE layout_column_filters (
            tab_id TEXT NOT NULL,
            field TEXT NOT NULL,
            op TEXT NOT NULL DEFAULT 'contains',
            v TEXT,
            v2 TEXT
        );
        CREATE TABLE report_schedules (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            view_id TEXT NOT NULL,
            owner_handle TEXT,
            name TEXT NOT NULL DEFAULT '',
            freq TEXT NOT NULL,
            time TEXT NOT NULL DEFAULT '08:00',
            sharepoint_path TEXT NOT NULL DEFAULT '',
            filename_template TEXT NOT NULL DEFAULT '',
            folder_kind TEXT NOT NULL DEFAULT 'sharepoint',
            email_subject TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            catch_up_pending INTEGER NOT NULL DEFAULT 0,
            catch_up_for_date TEXT,
            last_claimed_at TEXT,
            window_period TEXT
        );
        CREATE TABLE schedule_weekdays (
            schedule_id TEXT NOT NULL,
            weekday INTEGER NOT NULL
        );
        CREATE TABLE schedule_monthdays (
            schedule_id TEXT NOT NULL,
            monthday INTEGER NOT NULL
        );
        CREATE TABLE schedule_recipients (
            id TEXT PRIMARY KEY,
            schedule_id TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL
        );
        CREATE TABLE schedule_email_salesmen (
            schedule_id TEXT NOT NULL,
            salesman TEXT NOT NULL
        );
        INSERT INTO users (id, email, display_name, role, handle)
        VALUES (1, 'heshey@achimonline.com', 'Heshey', 'admin', 'heshey');
        INSERT INTO views (id, kind, report_key, name, owner_handle, period)
        VALUES ('v-daily', 'company', 'ordered', 'Daily Ordered', NULL, 'this_week');
        INSERT INTO view_salesmen (view_id, salesman) VALUES ('v-daily', 'HKaufman');
        INSERT INTO view_statuses (view_id, status) VALUES ('v-daily', 'Invoiced'), ('v-daily', 'Open');
        INSERT INTO layout_tabs (id, view_id, tab_key, position, has_view)
        VALUES ('t1', 'v-daily', 'summary', 1, 1);
        INSERT INTO layout_tab_groups (tab_id, position, column_name) VALUES ('t1', 1, 'Salesman');
        INSERT INTO layout_tab_sorters (tab_id, position, column_name, dir)
        VALUES ('t1', 1, 'SalesAmount', 'desc');
        INSERT INTO layout_columns (tab_id, field, position, hidden)
        VALUES ('t1', 'SalesAmount', 1, 1);
        INSERT INTO layout_column_filters (tab_id, field, op, v)
        VALUES ('t1', 'CustomerName', 'contains', 'HD');
        INSERT INTO report_schedules (
            id, kind, view_id, owner_handle, name, freq, time, sharepoint_path,
            filename_template, email_subject, window_period
        ) VALUES (
            's1', 'company', 'v-daily', 'heshey', 'Monday Ordered', 'weekly', '09:00',
            'Direct Reports/Ordered Report', '{Schedule}.xlsx', '{Schedule} {Period}', 'this_week'
        );
        INSERT INTO schedule_weekdays (schedule_id, weekday) VALUES ('s1', 0);
        INSERT INTO schedule_monthdays (schedule_id, monthday) VALUES ('s1', 15);
        INSERT INTO schedule_recipients (id, schedule_id, email, role)
        VALUES ('r1', 's1', 'reports@achimonline.com', 'to'),
               ('r2', 's1', 'cc@achimonline.com', 'cc');
        INSERT INTO schedule_email_salesmen (schedule_id, salesman) VALUES ('s1', 'HKaufman');
        """
    )
    conn.commit()
    conn.close()
    result = import_precious(source, dest)
    assert result["users_inserted"] == 1
    assert result["views_inserted"] >= 1
    view = next(v for v in home_store.list_views("heshey@achimonline.com", True) if v["name"] == "Daily Ordered")
    assert view["params"]["period"] == "this_week"
    assert view["params"]["salesmen"] == ["HKaufman"]
    assert view["params"]["status"] == "Invoiced"
    assert "SalesAmount" in (view["layout"]["views"]["summary"]["hidden"] or [])
    assert view["layout"]["views"]["summary"]["group"] == ["Salesman"]
    assert view["layout"]["views"]["summary"]["sorters"] == [{"column": "SalesAmount", "dir": "desc"}]
    assert view["layout"]["views"]["summary"]["columnFilters"]["CustomerName"]["v"] == "HD"
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM view_statuses").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM layout_tab_groups").fetchone()[0] == 1
    rows = home_store.list_schedules()
    assert not any(s["name"] == "Monday Ordered" for s in rows)
    assert result["schedules_skipped"] >= 1


def test_import_ignores_json_blob_tables(tmp_path, monkeypatch):
    from import_precious import import_precious, summarize

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
            role TEXT NOT NULL
        );
        CREATE TABLE saved_reports (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            report_key TEXT NOT NULL,
            name TEXT NOT NULL,
            params_json TEXT NOT NULL,
            layout_json TEXT NOT NULL
        );
        CREATE TABLE master_schedules (
            id INTEGER PRIMARY KEY,
            report_key TEXT NOT NULL,
            name TEXT NOT NULL,
            cadence TEXT NOT NULL,
            recipients TEXT NOT NULL,
            params_json TEXT
        );
        INSERT INTO users (id, email, display_name, role)
        VALUES (1, 'meir@achimonline.com', 'Meir', 'salesman');
        INSERT INTO saved_reports (user_id, report_key, name, params_json, layout_json)
        VALUES (1, 'invoiced', 'My Invoiced', '{"period":"mtd"}', '{}');
        INSERT INTO master_schedules (report_key, name, cadence, recipients, params_json)
        VALUES ('invoiced', 'JSON Only', '{"freq":"daily","time":"07:30"}', 'meir@achimonline.com', '{}');
        """
    )
    conn.commit()
    conn.close()
    result = import_precious(source, dest)
    assert result["source_views"] == 0
    assert result["source_schedules"] == 0
    assert result["views_inserted"] == 0
    assert result["schedules_inserted"] == 0
    names = {v["name"] for v in home_store.list_views("meir@achimonline.com", True)}
    assert "My Invoiced" not in names
    assert not any(s["name"] == "JSON Only" for s in home_store.list_schedules())
    with db() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "saved_reports" not in tables
        assert "master_schedules" not in tables
        assert "params_json" not in {row[1] for row in conn.execute("PRAGMA table_info(views)")}
    flash = summarize(result)
    assert "views 0→" in flash
    assert "report_schedules 0→" in flash
    assert "/tmp/v3data" in flash
    assert "BETA_PRECIOUS_DB_PATH" in flash


def test_summarize_warns_on_seed_counts_not_live():
    from import_precious import summarize

    seed = summarize(
        {
            "users_inserted": 0,
            "users_skipped": 13,
            "views_inserted": 9,
            "views_updated": 0,
            "views_skipped": 0,
            "schedules_inserted": 13,
            "schedules_updated": 0,
            "schedules_skipped": 0,
            "source_tables": {
                "views": 9,
                "layout_tabs": 18,
                "report_schedules": 13,
            },
            "dest_tables": {
                "views": 9,
                "layout_tabs": 18,
                "report_schedules": 13,
            },
        }
    )
    assert "views 9→9" in seed
    assert "/tmp/v3data" in seed
    assert "BETA_PRECIOUS_DB_PATH" in seed
    live = summarize(
        {
            "users_inserted": 3,
            "users_skipped": 13,
            "views_inserted": 97,
            "views_updated": 0,
            "views_skipped": 0,
            "schedules_inserted": 58,
            "schedules_updated": 0,
            "schedules_skipped": 0,
            "source_tables": {
                "views": 97,
                "layout_tabs": 592,
                "report_schedules": 58,
            },
            "dest_tables": {
                "views": 97,
                "layout_tabs": 592,
                "report_schedules": 58,
            },
        }
    )
    assert "views 97→97" in live
    assert "report_schedules 58→58" in live
    assert "Azure seed/freeze" not in live
    assert "/tmp/v3data" not in live


def test_import_every_normalized_view_skips_json_blobs(tmp_path, monkeypatch):
    from import_precious import import_precious

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
            handle TEXT
        );
        CREATE TABLE views (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            report_key TEXT NOT NULL,
            name TEXT NOT NULL,
            owner_handle TEXT,
            period TEXT
        );
        CREATE TABLE saved_reports (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            report_key TEXT NOT NULL,
            name TEXT NOT NULL,
            params_json TEXT NOT NULL,
            layout_json TEXT NOT NULL
        );
        CREATE TABLE company_views (
            id INTEGER PRIMARY KEY,
            report_key TEXT NOT NULL,
            name TEXT NOT NULL,
            params_json TEXT NOT NULL
        );
        INSERT INTO users (id, email, display_name, role, handle)
        VALUES (1, 'heshey@achimonline.com', 'Heshey', 'admin', 'heshey'),
               (2, 'tina@achimonline.com', 'Tina', 'manager', 'tina');
        INSERT INTO views (id, kind, report_key, name, owner_handle, period)
        VALUES ('df-ordered', 'default', 'ordered', 'Default', NULL, 'this_week'),
               ('co-ordered-daily', 'company', 'ordered', 'Daily Ordered', NULL, 'this_week'),
               ('pe-heshey-open', 'personal', 'ordered', 'Heshey Open Orders', 'heshey', 'ytd'),
               ('pe-tina-mtd', 'personal', 'invoiced', 'Tina MTD', 'tina', 'mtd');
        INSERT INTO saved_reports (user_id, report_key, name, params_json, layout_json)
        VALUES (1, 'ordered', 'Blob Only View', '{}', '{}');
        INSERT INTO company_views (report_key, name, params_json)
        VALUES ('ordered', 'Blob Company', '{}');
        """
    )
    conn.commit()
    conn.close()
    result = import_precious(source, dest)
    assert result["source_views"] == 4
    assert result["views_inserted"] == 4
    names = {v["name"] for v in home_store.list_views("heshey@achimonline.com", True)}
    assert "Default" in names
    assert "Daily Ordered" in names
    assert "Heshey Open Orders" in names
    assert "Tina MTD" in names
    assert "Blob Only View" not in names
    assert "Blob Company" not in names
    tina = next(v for v in home_store.list_views("tina@achimonline.com", True) if v["name"] == "Tina MTD")
    assert tina["owner_email"] == "tina@achimonline.com"
    assert tina["kind"] == "personal"


def test_import_copies_assemble_children_not_json_schedules(tmp_path, monkeypatch):
    from import_precious import import_precious, summarize

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
            handle TEXT
        );
        CREATE TABLE views (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            report_key TEXT NOT NULL,
            name TEXT NOT NULL,
            owner_handle TEXT,
            period TEXT
        );
        CREATE TABLE layout_tabs (
            id TEXT PRIMARY KEY,
            view_id TEXT NOT NULL,
            tab_key TEXT NOT NULL,
            position INTEGER,
            has_view INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE layout_tab_groups (
            tab_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            column_name TEXT NOT NULL
        );
        CREATE TABLE report_schedules (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            view_id TEXT NOT NULL,
            owner_handle TEXT,
            name TEXT NOT NULL DEFAULT '',
            freq TEXT NOT NULL,
            time TEXT NOT NULL DEFAULT '08:00',
            is_active INTEGER NOT NULL DEFAULT 1,
            split_by_salesman INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE schedule_recipients (
            id TEXT PRIMARY KEY,
            schedule_id TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL
        );
        CREATE TABLE schedule_weekdays (
            schedule_id TEXT NOT NULL,
            weekday INTEGER NOT NULL
        );
        CREATE TABLE master_schedules (
            id INTEGER PRIMARY KEY,
            report_key TEXT NOT NULL,
            name TEXT NOT NULL,
            cadence TEXT NOT NULL,
            recipients TEXT NOT NULL
        );
        INSERT INTO users (id, email, display_name, role, handle)
        VALUES (1, 'heshey@achimonline.com', 'Heshey', 'admin', 'heshey');
        INSERT INTO views (id, kind, report_key, name, owner_handle, period)
        VALUES ('v1', 'personal', 'ordered', 'Heshey Open', 'heshey', 'ytd');
        INSERT INTO layout_tabs (id, view_id, tab_key, position, has_view)
        VALUES ('t1', 'v1', 'summary', 0, 1), ('t2', 'v1', 'detail', 1, 0);
        INSERT INTO layout_tab_groups (tab_id, position, column_name)
        VALUES ('t1', 0, 'Salesman');
        INSERT INTO report_schedules (id, kind, view_id, owner_handle, name, freq, time, split_by_salesman)
        VALUES ('s1', 'personal', 'v1', 'heshey', 'Heshey Open', 'weekly', '08:00', 1);
        INSERT INTO schedule_recipients (id, schedule_id, email, role)
        VALUES ('r1', 's1', 'heshey@achimonline.com', 'to');
        INSERT INTO schedule_weekdays (schedule_id, weekday) VALUES ('s1', 0);
        INSERT INTO master_schedules (report_key, name, cadence, recipients)
        VALUES ('ordered', 'JSON Extra', '{"freq":"daily","time":"09:00"}', 'blob@achimonline.com');
        """
    )
    conn.commit()
    conn.close()
    result = import_precious(source, dest)
    assert result["source_tables"]["views"] == 1
    assert result["source_tables"]["layout_tabs"] == 2
    assert result["source_tables"]["layout_tab_groups"] == 1
    assert result["source_tables"]["report_schedules"] == 1
    assert result["dest_tables"]["layout_tabs"] == 2
    assert result["dest_tables"]["layout_tab_groups"] == 1
    assert result["dest_tables"]["report_schedules"] == 1
    assert result["views_inserted"] == 1
    assert result["schedules_inserted"] == 1
    flash = summarize(result)
    assert "layout_tabs 2→2" in flash
    assert "report_schedules 1→1" in flash
    names = {v["name"] for v in home_store.list_views("heshey@achimonline.com", True)}
    assert names == {"Heshey Open"}
    rows = home_store.list_schedules()
    assert len(rows) == 1
    assert rows[0]["name"] == "Heshey Open"
    assert rows[0]["weekdays"] == "mon"
    assert "heshey@achimonline.com" in rows[0]["recipients"]
    assert rows[0]["split_by_salesman"] == 1
    assert not any("blob@achimonline.com" in (row["recipients"] or "") for row in rows)
    with db() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "master_schedules" not in tables
        assert conn.execute("SELECT COUNT(*) FROM layout_tabs").fetchone()[0] == 2


def test_import_uses_live_admin_and_column_recipients(tmp_path, monkeypatch):
    from import_precious import import_precious

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
            handle TEXT
        );
        CREATE TABLE views (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            report_key TEXT NOT NULL,
            name TEXT NOT NULL,
            owner_handle TEXT
        );
        CREATE TABLE report_schedules (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            view_id TEXT NOT NULL,
            owner_handle TEXT,
            name TEXT NOT NULL DEFAULT '',
            freq TEXT NOT NULL,
            time TEXT NOT NULL DEFAULT '08:00',
            sharepoint_path TEXT,
            folder_kind TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE schedule_recipients (
            id TEXT PRIMARY KEY,
            schedule_id TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL
        );
        INSERT INTO users (id, email, display_name, role, handle)
        VALUES (1, 'heshey@achimonline.com', 'Heshey', 'admin', 'heshey');
        INSERT INTO views (id, kind, report_key, name, owner_handle)
        VALUES ('v1', 'company', 'ordered', 'Daily Ordered', NULL);
        INSERT INTO report_schedules (id, kind, view_id, owner_handle, name, freq, time, sharepoint_path, folder_kind)
        VALUES ('s1', 'personal', 'v1', NULL, 'Daily Ordered Report', 'daily', '00:00', 'Ordered Report/Daily', 'onedrive');
        INSERT INTO schedule_recipients (id, schedule_id, email, role)
        VALUES ('r1', 's1', 'reports@achimonline.com', 'to');
        """
    )
    conn.commit()
    conn.close()
    import_precious(source, dest)
    rows = home_store.list_schedules()
    assert len(rows) == 1
    assert rows[0]["owner_email"] == "heshey@achimonline.com"
    assert "reports@achimonline.com" in rows[0]["recipients"]
    with TestClient(create_app()) as client:
        login(client)
        html = client.get("/schedules").text
    assert "Daily Ordered Report" in html
    assert "reports@achimonline.com" in html
    assert "paused" not in html


def test_import_keeps_two_schedules_on_same_view_and_time(tmp_path, monkeypatch):
    from import_precious import import_precious

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
            handle TEXT
        );
        CREATE TABLE views (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            report_key TEXT NOT NULL,
            name TEXT NOT NULL,
            owner_handle TEXT,
            period TEXT
        );
        CREATE TABLE report_schedules (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            view_id TEXT NOT NULL,
            owner_handle TEXT,
            name TEXT NOT NULL DEFAULT '',
            freq TEXT NOT NULL,
            time TEXT NOT NULL DEFAULT '08:00',
            is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE schedule_recipients (
            id TEXT PRIMARY KEY,
            schedule_id TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL
        );
        INSERT INTO users (id, email, display_name, role, handle)
        VALUES (1, 'heshey@achimonline.com', 'Heshey', 'admin', 'heshey'),
               (2, 'tina@achimonline.com', 'Tina', 'manager', 'tina');
        INSERT INTO views (id, kind, report_key, name, owner_handle, period)
        VALUES ('v1', 'company', 'ordered', 'Daily Ordered', NULL, 'this_week');
        INSERT INTO report_schedules (id, kind, view_id, owner_handle, name, freq, time)
        VALUES ('s1', 'company', 'v1', 'heshey', 'Morning Ordered', 'daily', '09:00'),
               ('s2', 'personal', 'v1', 'tina', 'Tina copy', 'daily', '09:00');
        INSERT INTO schedule_recipients (id, schedule_id, email, role)
        VALUES ('r1', 's1', 'reports@achimonline.com', 'to'),
               ('r2', 's2', 'tina@achimonline.com', 'to');
        """
    )
    conn.commit()
    conn.close()
    result = import_precious(source, dest)
    assert result["source_schedules"] == 2
    assert result["schedules_inserted"] == 1
    rows = home_store.list_schedules()
    assert len(rows) == 1
    names = {row["name"] for row in rows}
    assert names == {"Tina copy"}
    owners = {row["owner_email"] for row in rows}
    assert owners == {"tina@achimonline.com"}
    assert not any("reports@achimonline.com" in (row["recipients"] or "") for row in rows)
    with TestClient(create_app()) as client:
        login(client)
        html = client.get("/schedules").text
    assert "Tina copy" in html
    assert "Morning Ordered" not in html
    assert "tina@achimonline.com" in html


def test_import_keeps_schedule_windows_on_shared_view(tmp_path, monkeypatch):
    from deliver import _run_params
    from import_precious import import_precious

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
            handle TEXT
        );
        CREATE TABLE views (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            report_key TEXT NOT NULL,
            name TEXT NOT NULL,
            owner_handle TEXT,
            period TEXT
        );
        CREATE TABLE report_schedules (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            view_id TEXT NOT NULL,
            owner_handle TEXT,
            name TEXT NOT NULL DEFAULT '',
            freq TEXT NOT NULL,
            time TEXT NOT NULL DEFAULT '08:00',
            window_period TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        );
        INSERT INTO users (id, email, display_name, role, handle)
        VALUES (1, 'heshey@achimonline.com', 'Heshey', 'admin', 'heshey');
        INSERT INTO views (id, kind, report_key, name, owner_handle, period)
        VALUES ('df-invoiced', 'default', 'invoiced', 'Default', NULL, NULL);
        INSERT INTO report_schedules (id, kind, view_id, owner_handle, name, freq, time, window_period)
        VALUES
            ('s-daily', 'personal', 'df-invoiced', NULL, 'Daily Invoiced', 'daily', '05:00', 'yesterday'),
            ('s-month', 'personal', 'df-invoiced', NULL, 'Monthly Invoiced', 'monthly', '05:00', 'month');
        """
    )
    conn.commit()
    conn.close()
    import_precious(source, dest)
    view = next(v for v in home_store.list_views("heshey@achimonline.com", True) if v["name"] == "Default")
    assert not view["params"].get("period")
    rows = {row["name"]: row for row in home_store.list_schedules()}
    assert rows["Daily Invoiced"]["window_period"] == "yesterday"
    assert rows["Monthly Invoiced"]["window_period"] == "month"
    daily = home_store.get_schedule(rows["Daily Invoiced"]["id"])
    monthly = home_store.get_schedule(rows["Monthly Invoiced"]["id"])
    assert _run_params(daily, None)["period"] == "yesterday"
    assert _run_params(monthly, None)["period"] == "month"


def test_import_wipes_dummy_views_and_keeps_personal_views(tmp_path, monkeypatch):
    from import_precious import import_precious

    dest = tmp_path / "home.sqlite"
    monkeypatch.setenv("APP_DB_PATH", str(dest))
    init_db()
    dummy_names = {v["name"] for v in home_store.list_views("preview@achimonline.com", True)}
    assert "Daily Invoiced" in dummy_names
    source = tmp_path / "precious.db"
    conn = sqlite3.connect(source)
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            handle TEXT
        );
        CREATE TABLE views (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            report_key TEXT NOT NULL,
            name TEXT NOT NULL,
            owner_handle TEXT,
            period TEXT
        );
        CREATE TABLE report_schedules (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            view_id TEXT NOT NULL,
            owner_handle TEXT,
            freq TEXT NOT NULL,
            time TEXT NOT NULL DEFAULT '08:00',
            is_active INTEGER NOT NULL DEFAULT 1
        );
        INSERT INTO users (id, email, display_name, role, handle)
        VALUES (1, 'heshey@achimonline.com', 'Heshey', 'admin', 'heshey');
        INSERT INTO views (id, kind, report_key, name, owner_handle, period)
        VALUES ('v-ghost', 'personal', 'invoiced', 'Ghost Handle View', 'no-such-handle', 'mtd'),
               ('v-extra', 'personal', 'ordered', 'Heshey Extra', 'heshey', 'ytd');
        INSERT INTO report_schedules (id, kind, view_id, owner_handle, freq, time)
        VALUES ('s-ghost', 'personal', 'v-ghost', 'no-such-handle', 'daily', '06:15');
        """
    )
    conn.commit()
    conn.close()
    result = import_precious(source, dest)
    assert result["views_inserted"] >= 2
    names = {v["name"] for v in home_store.list_views("heshey@achimonline.com", True)}
    assert "Daily Invoiced" not in names
    assert "Daily Ordered" not in names
    assert "Ghost Handle View" in names
    assert "Heshey Extra" in names
    ghost = next(v for v in home_store.list_views("heshey@achimonline.com", True) if v["name"] == "Ghost Handle View")
    assert ghost["owner_email"] in {"heshey@achimonline.com", "preview@achimonline.com"}
    extra = next(v for v in home_store.list_views("heshey@achimonline.com", True) if v["name"] == "Heshey Extra")
    assert extra["params"]["period"] == "ytd"
    times = {s["run_time"] for s in home_store.list_schedules()}
    assert times == {"06:15"}


def test_settings_import_precious_upload(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from main import create_app
    from test_home import csrf_headers, login

    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "home.sqlite"))
    monkeypatch.delenv("REPORTING_API_KEY", raising=False)
    source = tmp_path / "precious.db"
    conn = sqlite3.connect(source)
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL
        );
        INSERT INTO users (email, display_name, role)
        VALUES ('upload.user@achimonline.com', 'Upload User', 'manager');
        """
    )
    conn.commit()
    conn.close()
    with TestClient(create_app()) as client:
        login(client)
        res = client.post(
            "/settings/import-precious",
            data={"csrf": client.csrf},
            files={"file": ("precious.db", source.read_bytes(), "application/octet-stream")},
            follow_redirects=False,
        )
        assert res.status_code == 303
    assert home_store.get_user("upload.user@achimonline.com") is not None


def test_root_import_precious_script(tmp_path, monkeypatch):
    import subprocess
    import sys

    dest = tmp_path / "home.sqlite"
    source = tmp_path / "precious.db"
    conn = sqlite3.connect(source)
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL
        );
        INSERT INTO users (email, display_name, role)
        VALUES ('script.user@achimonline.com', 'Script User', 'manager');
        """
    )
    conn.commit()
    conn.close()
    repo = Path(__file__).resolve().parents[2]
    script = repo / "import-precious.py"
    completed = subprocess.run(
        [sys.executable, str(script), str(source), "--dest", str(dest)],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "People 1 added" in completed.stdout
    monkeypatch.setenv("APP_DB_PATH", str(dest))
    row = home_store.get_user("script.user@achimonline.com")
    assert row is not None
    assert row["role"] == "manager"


def test_import_default_dest_follows_app_db_path(tmp_path, monkeypatch):
    from import_precious import default_dest_path

    dest = tmp_path / "home.sqlite"
    monkeypatch.setenv("APP_DB_PATH", str(dest))
    assert default_dest_path() == dest


def test_import_default_dest_on_azure_without_env(monkeypatch):
    from import_precious import default_dest_path

    monkeypatch.delenv("APP_DB_PATH", raising=False)
    monkeypatch.setattr("import_precious._on_azure", lambda: True)
    assert default_dest_path() == Path("/tmp/homedata/home.sqlite")


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
