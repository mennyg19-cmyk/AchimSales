"""Period-aware Shabbos makeup: skip vs reschedule, and date windows."""

from datetime import date

from web.scheduling.catchup import classify_action, overlay_windows, run_param_windows


_DAILY = {"freq": "daily", "time": "22:00"}
_MONTHLY_LAST = {"freq": "monthly", "time": "22:00", "monthdays": [-1]}


def test_mtd_friday_30_of_30_day_month_reschedules():
    # 2021-04-30 was a Friday; April has 30 days.
    skipped = date(2021, 4, 30)
    assert classify_action({"period": "mtd"}, "ordered", skipped, _DAILY) == "reschedule"
    assert classify_action({"period": "mtd"}, "ordered", skipped, _MONTHLY_LAST) == "reschedule"


def test_mtd_friday_30_of_31_day_month_reschedules():
    # 2026-01-30 Friday; Saturday the 31st is still in January and is Shabbos.
    skipped = date(2026, 1, 30)
    assert classify_action({"period": "mtd"}, "ordered", skipped, _DAILY) == "reschedule"


def test_mtd_mid_month_friday_skips_to_next_regular_slot():
    skipped = date(2026, 1, 16)  # Friday
    assert classify_action({"period": "mtd"}, "ordered", skipped, _DAILY) == "skip"


def test_yesterday_is_skip_class():
    skipped = date(2026, 1, 30)
    assert classify_action({"period": "yesterday"}, "invoiced", skipped, _DAILY) == "skip"


def test_last_month_and_last_7_days_reschedule():
    skipped = date(2026, 1, 30)
    assert classify_action({"period": "last_month"}, "invoiced", skipped, _MONTHLY_LAST) == "reschedule"
    assert classify_action({"period": "last_7_days"}, "ordered", skipped, _DAILY) == "reschedule"


def test_all_time_reports_reschedule():
    skipped = date(2026, 1, 31)
    assert classify_action({}, "salesman", skipped, _MONTHLY_LAST) == "reschedule"
    assert classify_action({}, "customer_activity", skipped, _MONTHLY_LAST) == "reschedule"


def test_mtd_cross_month_runs_skipped_day_then_month_end():
    skipped = date(2026, 1, 30)
    today = date(2026, 2, 2)
    windows = overlay_windows(
        {"period": "mtd"}, "ordered", skipped=skipped, today=today, last_success=date(2026, 1, 29),
    )
    assert [w["end_date"] for w in windows] == ["2026-01-30", "2026-01-31"]
    assert all(w["period"] == "custom" and w["start_date"] == "2026-01-01" for w in windows)


def test_mtd_cross_month_last_day_is_one_window():
    skipped = date(2026, 4, 30)
    windows = overlay_windows(
        {"period": "mtd"}, "ordered", skipped=skipped, today=date(2026, 5, 4), last_success=None,
    )
    assert len(windows) == 1
    assert windows[0]["start_date"] == "2026-04-01"
    assert windows[0]["end_date"] == "2026-04-30"


def test_mtd_same_month_keeps_named_period():
    windows = overlay_windows(
        {"period": "mtd"}, "ordered",
        skipped=date(2026, 1, 16), today=date(2026, 1, 19), last_success=None,
    )
    assert windows == [{"period": "mtd"}]


def test_yesterday_widens_from_last_success_through_yesterday():
    windows = overlay_windows(
        {"period": "yesterday"}, "invoiced",
        skipped=date(2026, 1, 30), today=date(2026, 2, 1), last_success=date(2026, 1, 29),
    )
    assert windows[0]["period"] == "custom"
    assert windows[0]["start_date"] == "2026-01-29"
    assert windows[0]["end_date"] == "2026-01-31"


def test_run_param_windows_adds_regular_mtd_when_asked():
    windows = run_param_windows(
        {"period": "mtd"}, "ordered",
        skipped_iso="2026-01-30", today=date(2026, 2, 2),
        last_success=date(2026, 1, 29), include_regular=True,
    )
    assert [w.get("end_date") or w.get("period") for w in windows] == [
        "2026-01-30", "2026-01-31", "mtd",
    ]


def test_run_param_windows_skips_regular_when_catchup_already_covers_it():
    windows = run_param_windows(
        {"period": "yesterday"}, "invoiced",
        skipped_iso="2026-01-30", today=date(2026, 2, 1),
        last_success=date(2026, 1, 29), include_regular=True,
    )
    assert len(windows) == 1
    assert windows[0]["period"] == "custom"
    assert windows[0]["start_date"] == "2026-01-29"
    assert windows[0]["end_date"] == "2026-01-31"


def test_last_month_as_of_skipped_1st_stays_named_if_still_that_month():
    # Skip 1 Jan 2026 (Thu was New Year; use 2027-08-01 Saturday).
    skipped = date(2026, 8, 1)
    today = date(2026, 8, 3)
    windows = overlay_windows(
        {"period": "last_month"}, "invoiced",
        skipped=skipped, today=today, last_success=None,
    )
    assert windows == [{"period": "last_month"}]
