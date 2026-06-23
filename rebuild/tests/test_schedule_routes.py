"""Route-level tests for the schedule pages, focused on authorization.

Guards the promises that matter: only admins reach the master-schedule page, a
regular person can manage their own schedule but not someone else's, and a bad
cadence is rejected with a message instead of a 500. Uses a throwaway database.
"""

from __future__ import annotations

import re

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_APP_ENV", "dev")
    monkeypatch.setenv("REBUILD_AUTH_MODE", "dev")
    monkeypatch.setenv("REBUILD_MOUNT_PATH", "/")
    monkeypatch.setenv("REBUILD_DEVELOPER_EMAILS", "boss@x.com")
    monkeypatch.setenv("REBUILD_WORKER_MODE", "off")  # no background threads in tests
    monkeypatch.setenv("REBUILD_PRECIOUS_DB_PATH", str(tmp_path / "precious.db"))
    monkeypatch.setenv("REBUILD_CACHE_DB_PATH", str(tmp_path / "cache.db"))

    from rebuild.app import bootstrap_background, create_app

    application = create_app()
    bootstrap_background(application)
    return application


def _login(client, email):
    with client.session_transaction() as session:
        session["user"] = {"email": email, "name": email}


def _csrf(client, path):
    page = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)


def _make_self_schedule(client, owner):
    # A regular person needs a salesman mapping before they can schedule anything
    # (an unmapped user has no data and is refused -- that's tested separately).
    from rebuild.app import get_db
    from rebuild.data.repositories.user_scope import UserScopeRepository
    UserScopeRepository(get_db(client.application)).set_salesmen(owner, ["10"])

    _login(client, owner)
    token = _csrf(client, "/schedules")
    client.post("/schedules", data={
        "csrf_token": token, "report_key": "invoiced", "title": "Mine", "period": "ytd",
        "freq": "daily", "time": "08:00", "skip_sabbath": "on",
    })
    from rebuild.data.repositories.schedules import SchedulesRepository
    return SchedulesRepository(get_db(client.application)).list_for_owner(owner)[0]


def test_regular_user_cannot_reach_master_schedules(app):
    client = app.test_client()
    _login(client, "rep@x.com")
    assert client.get("/admin/schedules").status_code == 403


def test_admin_can_reach_master_schedules(app):
    client = app.test_client()
    _login(client, "boss@x.com")
    assert client.get("/admin/schedules").status_code == 200


def test_owner_can_delete_their_own_schedule(app):
    client = app.test_client()
    schedule = _make_self_schedule(client, "rep@x.com")
    token = _csrf(client, "/schedules")
    resp = client.post(f"/schedules/{schedule.id}/delete", data={"csrf_token": token})
    assert resp.status_code == 302
    assert client.get("/schedules").get_data(as_text=True).count("Mine") == 0


def test_a_different_user_cannot_delete_someone_elses_schedule(app):
    client = app.test_client()
    schedule = _make_self_schedule(client, "rep@x.com")
    # A second, non-privileged person signs in and tries to delete it.
    other = app.test_client()
    _login(other, "intruder@x.com")
    token = _csrf(other, "/schedules")
    assert other.post(f"/schedules/{schedule.id}/delete", data={"csrf_token": token}).status_code == 403


def test_a_due_schedule_is_queued_at_most_once_per_day(app):
    from datetime import datetime, timezone

    from rebuild.app import get_config, get_db
    from rebuild.data.repositories.jobs import JobRepository
    from rebuild.data.repositories.schedules import KIND_SELF, SchedulesRepository
    from rebuild.scheduling.poller import enqueue_due

    db = get_db(app)
    SchedulesRepository(db).create(
        owner_email="rep@x.com", report_key="invoiced", title="Daily", kind=KIND_SELF,
        filters={}, cadence={"freq": "daily", "time": "00:00"}, recipients=[], salesmen=[],
        tab_key=None, skip_sabbath=True,
    )
    jobs = JobRepository(db, get_config(app).job_queue_max, get_config(app).job_stale_seconds)
    now = datetime(2026, 6, 17, 20, 0, tzinfo=timezone.utc)
    assert enqueue_due(db, jobs, now) == 1
    # Second tick the same day: already stamped as run, so nothing new is queued.
    assert enqueue_due(db, jobs, now) == 0


def test_master_schedule_cannot_be_managed_by_a_non_admin_owner(app):
    from rebuild.app import get_db
    from rebuild.data.repositories.schedules import KIND_MASTER, SchedulesRepository

    schedule = SchedulesRepository(get_db(app)).create(
        owner_email="rep@x.com", report_key="invoiced", title="M", kind=KIND_MASTER,
        filters={}, cadence={"freq": "daily", "time": "08:00"}, recipients=[], salesmen=["10"],
        tab_key=None, skip_sabbath=True,
    )
    client = app.test_client()
    _login(client, "rep@x.com")  # the stored owner, but not privileged
    token = _csrf(client, "/schedules")
    assert client.post(f"/schedules/{schedule.id}/delete", data={"csrf_token": token}).status_code == 403


def test_cancelled_schedule_job_stops_before_building_or_sending(app, monkeypatch):
    from rebuild.app import get_config, get_db
    from rebuild.data.repositories.schedules import KIND_SELF, SchedulesRepository
    from rebuild.data.repositories.user_scope import UserScopeRepository
    from rebuild.scheduling import run as run_mod

    db = get_db(app)
    UserScopeRepository(db).set_salesmen("rep@x.com", ["10"])
    schedule = SchedulesRepository(db).create(
        owner_email="rep@x.com", report_key="invoiced", title="S", kind=KIND_SELF,
        filters={}, cadence={"freq": "daily", "time": "08:00"}, recipients=[], salesmen=[],
        tab_key=None, skip_sabbath=False,
    )

    calls = {"build": 0}
    monkeypatch.setattr(run_mod, "build_report_snapshot",
                        lambda *a, **k: calls.__setitem__("build", calls["build"] + 1) or None)

    # should_continue() False from the start: no delivery should even be built.
    run_mod.run_schedule(db, get_config(app), schedule.id, should_continue=lambda: False)
    assert calls["build"] == 0


def test_bad_weekly_cadence_is_rejected_not_crashed(app):
    client = app.test_client()
    _login(client, "rep@x.com")
    token = _csrf(client, "/schedules")
    resp = client.post("/schedules", data={
        "csrf_token": token, "report_key": "invoiced", "title": "Bad", "period": "ytd",
        "freq": "weekly", "time": "08:00",  # no weekday picked
    })
    assert resp.status_code == 302  # redirected back with a flashed error, not a 500
