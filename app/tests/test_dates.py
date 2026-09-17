"""Report cells use iso_date (YYYY-MM-DD calendar day)."""

from datetime import date, datetime

import dates


def test_iso_date_parses_rfc_and_common_formats():
    assert dates.iso_date("Tue, 15 Sep 2026 16:21:16 GMT") == "2026-09-15"
    assert dates.iso_date("Mon, 27 Jul 2026 00:00:00 GMT") == "2026-07-27"
    assert dates.iso_date("2026-04-30T12:00:00") == "2026-04-30"
    assert dates.iso_date("2026-09-02 10:00:00") == "2026-09-02"
    assert dates.iso_date("04/30/2026") == "2026-04-30"
    assert dates.iso_date("N/A") == "N/A"
    assert dates.iso_date(None) == ""
    assert dates.iso_date(date(2026, 9, 15)) == "2026-09-15"
    assert dates.iso_date(datetime(2026, 9, 15, 16, 21, 16)) == "2026-09-15"
    assert dates.date_only("Tue, 15 Sep 2026 16:21:16 GMT") == "2026-09-15"


def test_eastern_datetime_keeps_time_and_converts_from_gmt():
    assert dates.eastern_datetime("Tue, 15 Sep 2026 16:21:16 GMT") == "2026-09-15 12:21:16"
    assert dates.eastern_datetime("2026-09-15") == "2026-09-15"
    assert dates.eastern_datetime("2026-09-02 10:00:00") == "2026-09-02 10:00:00"
    assert dates.eastern_datetime("N/A") == "N/A"
    assert dates.eastern_datetime(None) == ""
    assert dates.eastern_datetime("Thu, 15 Jan 2026 16:21:16 GMT") == "2026-01-15 11:21:16"
