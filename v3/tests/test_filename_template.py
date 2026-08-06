"""Filename template token expansion."""

from datetime import datetime
from zoneinfo import ZoneInfo

from web.delivery.filename_template import resolve_filename_template

_ET = ZoneInfo("America/New_York")


def test_default_template_when_blank():
    when = datetime(2026, 7, 15, 9, 30, tzinfo=_ET)
    name = resolve_filename_template("", report_name="Ordered", when=when)
    assert name == "Ordered_20260715.xlsx"


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
