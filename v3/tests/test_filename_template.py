"""Filename template token expansion."""

from datetime import datetime
from zoneinfo import ZoneInfo

from web.delivery.filename_template import resolve_filename_template, resolve_folder_template

_ET = ZoneInfo("America/New_York")


def test_default_template_uses_schedule_name_and_time():
    when = datetime(2026, 8, 17, 22, 30, tzinfo=_ET)
    name = resolve_filename_template(
        "", report_name="Ordered Report",
        schedule_name="Daily 9am", when=when,
    )
    assert name == "Daily_9am_2026-08-17_2230.xlsx"


def test_blank_template_does_not_collide_across_schedules():
    when = datetime(2026, 8, 17, 9, 0, tzinfo=_ET)
    a = resolve_filename_template(
        "", report_name="Ordered Report",
        schedule_name="Daily 9am", when=when,
    )
    b = resolve_filename_template(
        "", report_name="Ordered Report",
        schedule_name="DailyOrderReport", when=when,
    )
    assert a == "Daily_9am_2026-08-17_0900.xlsx"
    assert b == "DailyOrderReport_2026-08-17_0900.xlsx"


def test_blank_template_falls_back_to_report_when_no_schedule():
    when = datetime(2026, 7, 15, 9, 30, tzinfo=_ET)
    name = resolve_filename_template("", report_name="Ordered", when=when)
    assert name == "Ordered_2026-07-15_0930.xlsx"


def test_month_number_and_name():
    when = datetime(2026, 7, 4, 8, 0, tzinfo=_ET)
    name = resolve_filename_template(
        "{MM}_{Month}_{Report}", report_name="Salesman Report", when=when,
    )
    assert name == "07_July_Salesman_Report.xlsx"


def test_period_from_params():
    when = datetime(2026, 1, 1, tzinfo=_ET)
    name = resolve_filename_template(
        "{Report}_{Period}", report_name="Ordered",
        params={"period": "last_month"}, when=when,
    )
    assert name == "Ordered_last_month.xlsx"


def test_schedule_name_token():
    when = datetime(2026, 8, 17, 8, 0, tzinfo=_ET)
    name = resolve_filename_template(
        "{Schedule}_{Report}_{YYYY}{MM}{DD}",
        report_name="Ordered Report",
        schedule_name="Daily Ordered Report",
        when=when,
    )
    assert name == "Daily_Ordered_Report_Ordered_Report_20260817.xlsx"


def test_report_title_is_slugged():
    when = datetime(2026, 8, 17, tzinfo=_ET)
    name = resolve_filename_template(
        "{Report}_{YYYY}{MM}{DD}", report_name="Ordered Report", when=when,
    )
    assert name == "Ordered_Report_20260817.xlsx"


def test_folder_template_keeps_spaces_and_slashes():
    when = datetime(2026, 8, 19, 12, 0, tzinfo=_ET)
    path = resolve_folder_template(
        "Salesman Report/Customer Activity/{Month} {YYYY}",
        report_name="Customer Activity", when=when,
    )
    assert path == "Salesman Report/Customer Activity/August 2026"


def test_folder_template_blank_is_empty():
    assert resolve_folder_template("") == ""
    assert resolve_folder_template("  /  ") == ""
