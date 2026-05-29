"""Engine helpers preserve the audited originals' behaviour (parity foundation)."""

from report_engine import lib


def test_num_blanks_are_zero():
    for blank in (None, "", "NULL"):
        assert lib.num(blank) == 0.0


def test_num_coerces_and_survives_junk():
    assert lib.num("12.5") == 12.5
    assert lib.num(3) == 3.0
    assert lib.num("not-a-number") == 0.0


def test_as_int_rounds():
    assert lib.as_int("2.6") == 3
    assert lib.as_int(None) == 0


def test_text_blanks():
    assert lib.text(None) == ""
    assert lib.text("NULL") == ""
    assert lib.text(5) == "5"


def test_first_of_skips_blanks():
    row = {"A": None, "B": "NULL", "C": "x", "D": "y"}
    assert lib.first_of(row, "A", "B", "C", "D") == "x"
    assert lib.first_of(row, "A", "B") is None


def test_date_only_trims():
    assert lib.date_only("2026-04-30T12:00:00") == "2026-04-30"
    assert lib.date_only("2026-04-30") == "2026-04-30"


def test_salesman_key_normalizes():
    assert lib.salesman_key(" M Kolko ") == "mkolko"
    assert lib.salesman_key("H-Kaufman") == "hkaufman"
    assert lib.salesman_key(None) == ""
