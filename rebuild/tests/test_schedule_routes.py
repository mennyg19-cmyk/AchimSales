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


def _make_schedule(app, **overrides):
    from rebuild.app import get_db
    from rebuild.data.repositories.schedules import KIND_SELF, SchedulesRepository
    from rebuild.data.repositories.user_scope import UserScopeRepository

    db = get_db(app)
    UserScopeRepository(db).set_salesmen("rep@x.com", ["10"])
    fields = dict(
        owner_email="rep@x.com", report_key="invoiced", title="S", kind=KIND_SELF,
        filters={}, cadence={"freq": "daily", "time": "08:00"}, recipients=[], salesmen=[],
        tab_key=None, skip_sabbath=True,
    )
    fields.update(overrides)
    return SchedulesRepository(db).create(**fields)


def test_sabbath_skip_flags_a_catch_up_then_the_poller_queues_it_after(app, monkeypatch):
    from datetime import datetime, timezone

    from rebuild.app import get_config, get_db
    from rebuild.data.repositories.jobs import JobRepository
    from rebuild.data.repositories.schedules import SchedulesRepository
    from rebuild.scheduling import poller as poller_mod
    from rebuild.scheduling import run as run_mod
    from rebuild.scheduling.poller import enqueue_due

    db = get_db(app)
    schedule = _make_schedule(app)
    now = datetime(2026, 6, 20, 16, 0, tzinfo=timezone.utc)  # a Saturday afternoon

    # During Shabbos the run is skipped and a catch-up is flagged, not lost.
    monkeypatch.setattr(run_mod, "melacha_assur", lambda _now=None: (True, "Shabbos"))
    run_mod.run_schedule(db, get_config(app), schedule.id, now=now)
    after_skip = SchedulesRepository(db).get(schedule.id)
    assert after_skip.catch_up_pending is True
    assert after_skip.last_run_at is not None

    # Once Shabbos is over, the poller queues the catch-up even though the cadence
    # already "ran" (was skipped) today.
    monkeypatch.setattr(poller_mod, "melacha_assur", lambda _now=None: (False, ""))
    jobs = JobRepository(db, get_config(app).job_queue_max, get_config(app).job_stale_seconds)
    later = datetime(2026, 6, 20, 23, 30, tzinfo=timezone.utc)  # Saturday night
    assert enqueue_due(db, jobs, later) == 1


def test_cancelled_catch_up_run_keeps_the_flag_set_so_the_poller_retries(app, monkeypatch):
    # A catch-up that gets cancelled/timed out before it sends must NOT clear the
    # catch_up_pending flag -- otherwise the owed Shabbos send is silently dropped.
    # The real flow: (1) mark_skipped sets the flag, (2) the poller clears it AND
    # passes was_catch_up=True in the job params, (3) the job is cancelled before
    # settling, (4) run_schedule must RE-SET the flag from the param (it can't read
    # it from the DB because the poller already cleared it).
    from rebuild.app import get_config, get_db
    from rebuild.data.repositories.schedules import SchedulesRepository
    from rebuild.scheduling import run as run_mod

    db = get_db(app)
    schedule = _make_schedule(app)
    repo = SchedulesRepository(db)
    repo.mark_skipped_for_sabbath(schedule.id, "2026-06-20T20:00:00+00:00")
    assert repo.get(schedule.id).catch_up_pending is True

    # Simulate what the poller does: clear the flag, then run with was_catch_up.
    repo.clear_catch_up(schedule.id)
    assert repo.get(schedule.id).catch_up_pending is False  # DB is cleared

    # Worker runs with was_catch_up=True (from job params) but is cancelled.
    monkeypatch.setattr(run_mod, "melacha_assur", lambda _now=None: (False, ""))
    run_mod.run_schedule(
        db, get_config(app), schedule.id,
        should_continue=lambda: False, was_catch_up=True,
    )
    # The flag was restored even though the DB had it cleared.
    assert repo.get(schedule.id).catch_up_pending is True


def test_a_whole_failed_run_notifies_a_private_schedule_owner(app, monkeypatch):
    from rebuild.app import get_config, get_db
    from rebuild.data.repositories.notifications import NotificationsRepository
    from rebuild.scheduling import run as run_mod

    db = get_db(app)
    schedule = _make_schedule(app, skip_sabbath=False)

    def _boom(*_a, **_k):
        raise RuntimeError("reporting API down")

    monkeypatch.setattr(run_mod, "build_report_snapshot", _boom)
    run_mod.run_schedule(db, get_config(app), schedule.id)

    unread = NotificationsRepository(db).list_unread("rep@x.com")
    assert len(unread) == 1
    assert unread[0]["schedule_id"] == schedule.id


def test_manual_run_now_queues_a_job_and_clears_the_notification(app):
    from rebuild.app import get_db
    from rebuild.data.repositories.notifications import KIND_SCHEDULE_FAILED, NotificationsRepository
    from rebuild.jobs.types import JOB_SCHEDULE_RUN

    db = get_db(app)
    schedule = _make_schedule(app, skip_sabbath=False)
    NotificationsRepository(db).create(
        user_email="rep@x.com", kind=KIND_SCHEDULE_FAILED, title="failed", schedule_id=schedule.id,
    )

    client = app.test_client()
    _login(client, "rep@x.com")
    token = _csrf(client, "/schedules")
    resp = client.post(f"/schedules/{schedule.id}/run-now", data={"csrf_token": token})
    assert resp.status_code == 302

    with db.precious() as conn:
        row = conn.fetchone(
            "SELECT params FROM jobs WHERE job_type = ? ORDER BY created_at DESC LIMIT 1",
            (JOB_SCHEDULE_RUN,),
        )
    assert row is not None and '"manual": true' in row["params"]
    assert NotificationsRepository(db).list_unread("rep@x.com") == []


def test_manual_run_ignores_the_sabbath_skip(app, monkeypatch):
    from rebuild.app import get_config, get_db
    from rebuild.data.repositories.schedules import SchedulesRepository
    from rebuild.scheduling import run as run_mod

    db = get_db(app)
    schedule = _make_schedule(app, skip_sabbath=True)
    monkeypatch.setattr(run_mod, "melacha_assur", lambda _now=None: (True, "Shabbos"))
    # Building returns None (treated as "stopped"), so no real send is attempted --
    # we only care that the Shabbos gate did NOT short-circuit a manual run.
    monkeypatch.setattr(run_mod, "build_report_snapshot", lambda *a, **k: None)

    run_mod.run_schedule(db, get_config(app), schedule.id, ignore_sabbath=True)

    after = SchedulesRepository(db).get(schedule.id)
    assert after.catch_up_pending is False  # it didn't take the Shabbos-skip path


def test_manual_run_does_not_consume_todays_scheduled_slot(app, monkeypatch):
    from datetime import datetime, timezone

    from rebuild.app import get_config, get_db
    from rebuild.data.repositories.jobs import JobRepository
    from rebuild.data.repositories.schedules import SchedulesRepository
    from rebuild.scheduling import run as run_mod
    from rebuild.scheduling.poller import enqueue_due

    db = get_db(app)
    schedule = _make_schedule(app, skip_sabbath=False, cadence={"freq": "daily", "time": "00:00"})
    monkeypatch.setattr(run_mod, "build_report_snapshot", lambda *a, **k: None)

    # A manual run earlier in the day must NOT stamp last_run_at...
    run_mod.run_schedule(db, get_config(app), schedule.id, ignore_sabbath=True)
    assert SchedulesRepository(db).get(schedule.id).last_run_at is None

    # ...so the real scheduled run is still queued when its time comes.
    jobs = JobRepository(db, get_config(app).job_queue_max, get_config(app).job_stale_seconds)
    now = datetime(2026, 6, 17, 20, 0, tzinfo=timezone.utc)
    assert enqueue_due(db, jobs, now) == 1


def test_owed_catch_up_is_absorbed_by_the_next_normal_run(app, monkeypatch):
    from datetime import datetime, timezone

    from rebuild.app import get_config, get_db
    from rebuild.data.repositories.jobs import JobRepository
    from rebuild.data.repositories.schedules import SchedulesRepository
    from rebuild.scheduling import poller as poller_mod
    from rebuild.scheduling.poller import enqueue_due

    db = get_db(app)
    repo = SchedulesRepository(db)
    schedule = _make_schedule(app, skip_sabbath=True, cadence={"freq": "daily", "time": "00:00"})
    # Simulate "skipped yesterday for Shabbos, catch-up never fired."
    repo.mark_skipped_for_sabbath(schedule.id, "2026-06-16T20:00:00+00:00")

    monkeypatch.setattr(poller_mod, "melacha_assur", lambda _now=None: (False, ""))
    jobs = JobRepository(db, get_config(app).job_queue_max, get_config(app).job_stale_seconds)
    now = datetime(2026, 6, 17, 20, 0, tzinfo=timezone.utc)  # the next day, normal run due

    # The normal run queues ONCE and clears the owed catch-up, so a later tick the
    # same day can't also queue a catch-up (which would double-send).
    assert enqueue_due(db, jobs, now) == 1
    assert repo.get(schedule.id).catch_up_pending is False
    assert enqueue_due(db, jobs, now) == 0


def test_a_person_cannot_dismiss_someone_elses_notification(app):
    from rebuild.app import get_db
    from rebuild.data.repositories.notifications import KIND_SCHEDULE_FAILED, NotificationsRepository

    db = get_db(app)
    note_id = NotificationsRepository(db).create(
        user_email="owner@x.com", kind=KIND_SCHEDULE_FAILED, title="failed",
    )
    other = app.test_client()
    _login(other, "intruder@x.com")
    token = _csrf(other, "/schedules")
    assert other.post(f"/notifications/{note_id}/dismiss", data={"csrf_token": token}).status_code == 403
