"""
Date freezing utilities for deterministic report testing.

Patches ``core.dates.get_now_eastern`` and ``get_today_eastern`` so every
piece of report logic sees the fake date instead of the real clock.
"""

from contextlib import contextmanager
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")


@contextmanager
def freeze_today(fake_date: date):
    """Context manager that freezes ``get_today_eastern()`` to *fake_date*.

    ``get_now_eastern()`` returns midnight Eastern on the same date so that
    any ``datetime.now``-style access is also deterministic.
    """
    fake_now = datetime(fake_date.year, fake_date.month, fake_date.day,
                        12, 0, 0, tzinfo=EASTERN)

    with (
        patch("core.dates.get_now_eastern", return_value=fake_now),
        patch("core.dates.get_today_eastern", return_value=fake_date),
    ):
        yield fake_date
