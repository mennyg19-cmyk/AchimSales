"""Graph mail, cadence, Hebcal hold/skip, clock tick, Entra/magic-link."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import cadence
import clock
import hebcal
import mail
import store as home_store
from db import db, init_db
from main import create_app


def _eastern(*args) -> datetime:
    return datetime(*args, tzinfo=timezone(timedelta(hours=-4)))


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


def test_due_now_daily_after_clock():
    cad = {"freq": "daily", "time": "08:00"}
    now = datetime(2026, 6, 17, 13, 0, tzinfo=timezone.utc)  # 09:00 ET
    assert cadence.due_now(cad, None, now) is True
    assert cadence.due_now(cad, "2026-06-17T12:00:00Z", now) is False
    early = datetime(2026, 6, 17, 11, 0, tzinfo=timezone.utc)  # 07:00 ET
    assert cadence.due_now(cad, None, early) is False


def test_due_now_weekly_uses_mon_tue_names():
    cad = cadence.from_schedule({"freq": "weekly", "run_time": "08:00", "weekdays": "mon,wed"})
    wednesday = datetime(2026, 6, 17, 13, 0, tzinfo=timezone.utc)  # Wed
    tuesday = datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)  # Tue
    assert cadence.due_now(cad, None, wednesday) is True
    assert cadence.due_now(cad, None, tuesday) is False


def test_inside_a_shabbos_window_is_restricted():
    items = [
        {"category": "candles", "date": "2026-06-19T20:00:00-04:00", "memo": ""},
        {"category": "havdalah", "date": "2026-06-20T21:00:00-04:00"},
    ]
    now = _eastern(2026, 6, 20, 12, 0)
    assur, reason = hebcal._assur_from_items(items, now)
    assert assur and reason == "Shabbos"


def test_hebcal_fetch_failure_holds(monkeypatch):
    def boom(_now):
        raise RuntimeError("hebcal down")

    monkeypatch.setattr(hebcal, "_fetch_items", boom)
    mode, reason = hebcal.restriction(datetime(2026, 6, 17, 20, 0, tzinfo=timezone.utc))
    assert mode == "hold"
    assert "could not be loaded" in reason


def test_hebcal_empty_items_hold(monkeypatch):
    monkeypatch.setattr(hebcal, "_fetch_items", lambda _now: [])
    mode, _reason = hebcal.restriction(datetime(2026, 6, 17, 20, 0, tzinfo=timezone.utc))
    assert mode == "hold"


def test_skip_sabbath_defaults_on():
    assert hebcal.skip_sabbath_enabled(None) is True
    assert hebcal.skip_sabbath_enabled({}) is True
    assert hebcal.skip_sabbath_enabled({"skip_sabbath": False}) is False


def test_clock_skips_assur_and_does_not_retry(home_db, monkeypatch):
    monkeypatch.setattr(hebcal, "restriction", lambda now=None: ("assur", "Shabbos"))
    now = datetime(2026, 6, 20, 16, 0, tzinfo=timezone.utc)
    first = clock.tick(now)
    second = clock.tick(now)
    assert first >= 1
    assert second == 0
    with db() as conn:
        row = conn.execute("SELECT last_status FROM schedules ORDER BY id LIMIT 1").fetchone()
        run = conn.execute("SELECT status FROM schedule_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert row["last_status"] == "skipped"
    assert run["status"] == "skipped"


def test_clock_hold_does_not_claim(home_db, monkeypatch):
    monkeypatch.setattr(hebcal, "restriction", lambda now=None: ("hold", "Hebcal calendar could not be loaded"))
    now = datetime(2026, 6, 17, 16, 0, tzinfo=timezone.utc)
    assert clock.tick(now) == 0
    with db() as conn:
        row = conn.execute("SELECT last_run, last_status FROM schedules ORDER BY id LIMIT 1").fetchone()
    assert row["last_run"] is None
    assert row["last_status"] is None


def test_clock_ok_delivers(home_db, monkeypatch):
    called = []
    monkeypatch.setattr(hebcal, "restriction", lambda now=None: ("ok", ""))
    monkeypatch.setattr(
        "clock.deliver_schedule",
        lambda schedule, user, at=None: called.append(schedule["id"]) or "success",
    )
    now = datetime(2026, 6, 17, 16, 0, tzinfo=timezone.utc)
    assert clock.tick(now) >= 1
    assert called


def test_graph_send_uses_stdlib(monkeypatch):
    calls = []

    class FakeResp:
        def __init__(self, body: bytes):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        if "oauth2" in request.full_url:
            return FakeResp(b'{"access_token":"tok"}')
        return FakeResp(b"")

    monkeypatch.setattr(mail.urllib.request, "urlopen", fake_urlopen)
    mailer = mail.GraphMailer("tenant", "id", "secret")
    mailer.send(
        sender="reports@achimonline.com",
        to=["preview@achimonline.com"],
        subject="Test",
        body_text="Hello",
        filename="x.xlsx",
        xlsx_bytes=b"PK",
    )
    assert len(calls) == 2
    assert "oauth2" in calls[0]
    assert "sendMail" in calls[1]


def test_magic_link_sends_when_graph_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "home.sqlite"))
    monkeypatch.setattr("config.graph_mail_configured", lambda: True)
    sent = {}

    def fake_send_or_outbox(**kwargs):
        sent.update(kwargs)
        return "graph"

    monkeypatch.setattr("main.send_or_outbox", fake_send_or_outbox)
    with TestClient(create_app()) as client:
        res = client.post(
            "/login/magic-link",
            data={"email": "external@example.com"},
            follow_redirects=False,
        )
        assert res.status_code == 303
        assert res.headers["location"].startswith("/login")
        home = client.get("/", follow_redirects=False)
        assert home.status_code == 302
    assert "token=" in sent["body"]
    assert sent["recipients"] == "external@example.com"


def test_entra_callback_refuses_unknown_person(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "home.sqlite"))
    monkeypatch.setattr(
        "entra.complete_login",
        lambda request: {"email": "nobody@achimonline.com", "name": "Nobody"},
    )
    with TestClient(create_app()) as client:
        res = client.get("/auth/callback")
        assert res.status_code == 403
    assert home_store.get_user("nobody@achimonline.com") is None


def test_entra_callback_signs_in_existing_people_row(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "home.sqlite"))
    monkeypatch.setattr(
        "entra.complete_login",
        lambda request: {"email": "preview@achimonline.com", "name": "Preview"},
    )
    with TestClient(create_app()) as client:
        res = client.get("/auth/callback", follow_redirects=False)
        assert res.status_code == 302
        assert res.headers["location"] == "/"
        home = client.get("/").text
        assert "Preview Admin" in home


def test_magic_consume_expired_token(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "home.sqlite"))
    with TestClient(create_app()) as client:
        res = client.get("/login/magic?token=not-a-token", follow_redirects=False)
        assert res.status_code == 302
        assert res.headers["location"] == "/login"


def test_clock_disabled_under_pytest():
    import config

    assert config.clock_disabled() is True
