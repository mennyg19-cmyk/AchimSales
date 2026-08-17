"""Shabbos/Yom Tov window check (Hebcal items, no network)."""

from datetime import datetime, timedelta, timezone

from web.scheduling.sabbath import _assur_from_items, melacha_assur, skip_sabbath_enabled


def _eastern(*args) -> datetime:
    return datetime(*args, tzinfo=timezone(timedelta(hours=-4)))


def test_inside_a_shabbos_window_is_restricted():
    items = [
        {"category": "candles", "date": "2026-06-19T20:00:00-04:00", "memo": ""},
        {"category": "havdalah", "date": "2026-06-20T21:00:00-04:00"},
    ]
    now = _eastern(2026, 6, 20, 12, 0)
    assur, reason = _assur_from_items(items, now)
    assert assur and reason == "Shabbos"


def test_weekday_memo_on_candles_is_still_shabbos():
    items = [
        {"category": "candles", "date": "2026-06-19T20:00:00-04:00", "memo": "Saturday"},
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
    now = _eastern(2026, 6, 18, 12, 0)
    assert _assur_from_items(items, now) == (False, "")


def test_sabbath_check_fails_open_on_a_malformed_response(monkeypatch):
    from web.scheduling import sabbath
    monkeypatch.setattr(
        sabbath, "_fetch_items",
        lambda now: [{"category": "candles", "date": "not-a-date"}],
    )
    now = datetime(2026, 6, 17, 20, 0, tzinfo=timezone.utc)
    assert melacha_assur(now) == (False, "")


def test_skip_sabbath_defaults_on():
    assert skip_sabbath_enabled(None) is True
    assert skip_sabbath_enabled({}) is True
    assert skip_sabbath_enabled({"skip_sabbath": False}) is False
