"""Catch-up workbooks are what the daily email should attach."""
from datetime import date

from webapp.services.email_distributions import choose_report_item

YESTERDAY = date(2026, 11, 21)
PREFIX = "Ordered_Report_"


def _item(name, modified):
    return {"name": name, "id": name, "lastModifiedDateTime": modified}


def test_catchup_beats_newer_single_day():
    chosen = choose_report_item([
        _item("Ordered_Report_2026-11-21.xlsx", "2026-11-22T05:08:06Z"),
        _item("Ordered_Report_2026-11-20_to_2026-11-21.xlsx", "2026-11-22T05:07:38Z"),
        _item("Ordered_Report_2026-11-20_to_2026-11-21_MKolko.xlsx", "2026-11-22T14:08:03Z"),
    ], PREFIX, YESTERDAY)
    assert chosen["name"] == "Ordered_Report_2026-11-20_to_2026-11-21.xlsx"


def test_single_day_when_no_catchup():
    chosen = choose_report_item([
        _item("Ordered_Report_2026-11-21.xlsx", "2026-11-22T05:08:06Z"),
        _item("Ordered_Report_MTD_2026-11-22.xlsx", "2026-11-22T05:16:47Z"),
        _item("Ordered_Report_Week_2026-11-15_to_2026-11-21.xlsx", "2026-11-22T05:10:00Z"),
    ], PREFIX, YESTERDAY)
    assert chosen["name"] == "Ordered_Report_2026-11-21.xlsx"


def test_covering_range_when_nothing_ends_on_yesterday():
    chosen = choose_report_item([
        _item("Ordered_Report_2026-11-18_to_2026-11-22.xlsx", "2026-11-22T05:07:38Z"),
    ], PREFIX, YESTERDAY)
    assert chosen["name"] == "Ordered_Report_2026-11-18_to_2026-11-22.xlsx"


def test_no_match():
    assert choose_report_item([
        _item("Ordered_Report_2026-11-19.xlsx", "2026-11-20T05:07:56Z"),
    ], PREFIX, YESTERDAY) is None
