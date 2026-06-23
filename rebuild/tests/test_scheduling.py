"""Regression tests for the scheduling engine.

Covers the three pure pieces the scheduler leans on: cadence (is a schedule due
now, and only once a day), the Shabbos/Yom Tov window check, and turning a
schedule into the concrete sends it produces (scope + recipients). No database,
no network -- the window check is fed canned Hebcal items.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rebuild.data.repositories.schedules import KIND_MASTER, KIND_SELF, Schedule
from rebuild.scheduling import cadence as C
from rebuild.scheduling.run import expand_deliveries
from rebuild.scheduling.sabbath import _assur_from_items

# Wednesday, June 17 2026. 20:00 UTC == 16:00 US/Eastern (EDT). 09:00 UTC == 05:00 EDT.
_WED_AFTERNOON = datetime(2026, 6, 17, 20, 0, tzinfo=timezone.utc)
_WED_EARLY = datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc)


# -- cadence ----------------------------------------------------------------

def test_normalize_rejects_unknown_frequency():
    with pytest.raises(ValueError):
        C.normalize({"freq": "hourly"})


def test_weekly_needs_at_least_one_weekday():
    with pytest.raises(ValueError):
        C.normalize({"freq": "weekly", "weekdays": []})


def test_normalize_cleans_time_and_clamps_monthday():
    assert C.normalize({"freq": "daily", "time": "8:5"}) == {"freq": "daily", "time": "08:05"}
    assert C.normalize({"freq": "monthly", "monthday": 99})["monthday"] == 28
    assert C.normalize({"freq": "monthly", "monthday": -1})["monthday"] == -1


def test_describe_reads_in_plain_english():
    assert C.describe({"freq": "weekly", "time": "08:00", "weekdays": [0, 2]}) == "Weekly (Mon, Wed) at 08:00"
    assert C.describe({"freq": "monthly", "time": "07:30", "monthday": -1}) == "Monthly on last day at 07:30"


def test_daily_is_due_after_its_time_but_not_before():
    daily = {"freq": "daily", "time": "08:00"}
    assert C.due_now(daily, None, _WED_AFTERNOON)
    assert not C.due_now(daily, None, _WED_EARLY)


def test_weekly_fires_only_on_its_weekday():
    wednesday_only = {"freq": "weekly", "time": "08:00", "weekdays": [2]}
    tuesday_only = {"freq": "weekly", "time": "08:00", "weekdays": [1]}
    assert C.due_now(wednesday_only, None, _WED_AFTERNOON)
    assert not C.due_now(tuesday_only, None, _WED_AFTERNOON)


def test_a_schedule_does_not_fire_twice_in_one_day():
    daily = {"freq": "daily", "time": "08:00"}
    already_ran = _WED_AFTERNOON.isoformat()
    assert not C.due_now(daily, already_ran, _WED_AFTERNOON)


# -- Shabbos / Yom Tov window ----------------------------------------------

def _eastern(*args) -> datetime:
    return datetime(*args, tzinfo=timezone(_minus4()))


def _minus4():
    from datetime import timedelta
    return timedelta(hours=-4)


def test_inside_a_shabbos_window_is_restricted():
    items = [
        {"category": "candles", "date": "2026-06-19T20:00:00-04:00", "memo": ""},
        {"category": "havdalah", "date": "2026-06-20T21:00:00-04:00"},
    ]
    now = _eastern(2026, 6, 20, 12, 0)
    assur, reason = _assur_from_items(items, now)
    assert assur and reason == "Shabbos"


def test_a_yom_tov_window_names_the_holiday():
    items = [
        {"category": "candles", "date": "2026-06-19T20:00:00-04:00", "memo": ""},
        {"category": "havdalah", "date": "2026-06-20T21:00:00-04:00"},
        {"yomtov": True, "date": "2026-06-20", "title": "Shavuot"},
    ]
    now = _eastern(2026, 6, 20, 12, 0)
    assur, reason = _assur_from_items(items, now)
    assert assur and reason == "Yom Tov: Shavuot"


def test_outside_any_window_is_not_restricted():
    items = [
        {"category": "candles", "date": "2026-06-19T20:00:00-04:00", "memo": ""},
        {"category": "havdalah", "date": "2026-06-20T21:00:00-04:00"},
    ]
    now = _eastern(2026, 6, 18, 12, 0)  # Thursday, before candle-lighting
    assert _assur_from_items(items, now) == (False, "")


# -- delivery expansion -----------------------------------------------------

class _FakeScope:
    def __init__(self, by_email=None, by_salesman=None) -> None:
        self._by_email = by_email or {}
        self._by_salesman = by_salesman or {}

    def salesmen_for(self, email: str) -> list[str]:
        return list(self._by_email.get((email or "").strip().lower(), []))

    def emails_for_salesman(self, number: str) -> list[str]:
        return list(self._by_salesman.get((number or "").strip(), []))


class _FakeConfig:
    developer_emails = frozenset({"boss@x.com"})


def _schedule(**kw) -> Schedule:
    base = dict(
        id="s1", owner_email="rep@x.com", report_key="invoiced", title="My invoiced",
        kind=KIND_SELF, filters={}, cadence={"freq": "daily", "time": "08:00"},
        recipients=[], salesmen=[], tab_key=None, skip_sabbath=True, enabled=True,
        last_run_at=None, created_at="t", updated_at="t",
    )
    base.update(kw)
    return Schedule(**base)


def test_self_schedule_scopes_to_the_owner_and_includes_extra_recipients():
    scope = _FakeScope(by_email={"rep@x.com": ["10", "20"]})
    sched = _schedule(recipients=["teammate@x.com"])
    deliveries = expand_deliveries(sched, scope, _FakeConfig())
    assert len(deliveries) == 1
    d = deliveries[0]
    assert d.scope_token == "sm:10,20"
    assert d.recipients == ["rep@x.com", "teammate@x.com"]
    assert d.reply_to == "rep@x.com"


def test_self_schedule_for_unmapped_owner_produces_no_delivery():
    sched = _schedule(owner_email="nobody@x.com")
    assert expand_deliveries(sched, _FakeScope(), _FakeConfig()) == []


def test_privileged_owner_self_schedule_sees_everything():
    sched = _schedule(owner_email="boss@x.com")
    deliveries = expand_deliveries(sched, _FakeScope(), _FakeConfig())
    assert deliveries[0].scope_token == "all"


def test_master_schedule_splits_per_salesman_and_skips_empty_recipients():
    scope = _FakeScope(by_salesman={"10": ["a@x.com"], "20": []})
    sched = _schedule(
        kind=KIND_MASTER, owner_email="boss@x.com", salesmen=["10", "20"],
        recipients=["cc@x.com"],
    )
    deliveries = expand_deliveries(sched, scope, _FakeConfig())
    # 20 has no mapped users but the admin listed an extra recipient, so it still
    # sends; both go out, each scoped to its own salesman.
    assert {d.scope_token for d in deliveries} == {"sm:10", "sm:20"}
    by_token = {d.scope_token: d for d in deliveries}
    assert by_token["sm:10"].recipients == ["a@x.com", "cc@x.com"]
    assert by_token["sm:20"].recipients == ["cc@x.com"]


def test_master_schedule_skips_salesman_with_no_recipients_at_all():
    scope = _FakeScope(by_salesman={"30": []})
    sched = _schedule(kind=KIND_MASTER, owner_email="boss@x.com", salesmen=["30"], recipients=[])
    assert expand_deliveries(sched, scope, _FakeConfig()) == []


def test_sabbath_check_fails_open_on_a_malformed_response(monkeypatch):
    # A successful fetch that returns junk must not raise (which would fail the
    # whole scheduled job) -- it falls open to "not restricted".
    from rebuild.scheduling import sabbath
    monkeypatch.setattr(sabbath, "_fetch_items", lambda now: [{"category": "candles", "date": "not-a-date"}])
    assert sabbath.melacha_assur(_WED_AFTERNOON) == (False, "")
