"""Salesman number lookup should not stamp every row as 029."""

from config.salesman_excel import REPORT_KEYS, SalesmanRecord, excel_numbers_collapsed
from config.salesman_map import get_salesman_number


def _rec(number: str, key: str) -> SalesmanRecord:
    return SalesmanRecord(
        number=number, full_name=key, display_name=key, email="",
        subscriptions={k: False for k in REPORT_KEYS},
    )


def test_excel_numbers_collapsed_when_most_rows_share_one_code(monkeypatch):
    mapping = {f"sm{i}": _rec("029", f"sm{i}") for i in range(10)}
    monkeypatch.setattr("config.salesman_excel.load_salesman_map", lambda path=None: mapping)
    assert excel_numbers_collapsed() is True


def test_excel_numbers_not_collapsed_when_codes_differ(monkeypatch):
    mapping = {f"sm{i}": _rec(str(10 + i).zfill(3), f"sm{i}") for i in range(10)}
    monkeypatch.setattr("config.salesman_excel.load_salesman_map", lambda path=None: mapping)
    assert excel_numbers_collapsed() is False


def test_get_salesman_number_uses_builtin_map_when_excel_collapsed(monkeypatch):
    mapping = {
        "redwards": _rec("029", "REdwards"),
        "hkaufman": _rec("029", "HKaufman"),
        "mkolko": _rec("029", "MKolko"),
        "blevin": _rec("029", "BLevin"),
        "house": _rec("029", "House"),
        "pmazer": _rec("029", "PMazer"),
        "jweigand": _rec("029", "JWeigand"),
        "lcwalker": _rec("029", "LCWalker"),
    }
    monkeypatch.setattr("config.salesman_excel.load_salesman_map", lambda path=None: mapping)
    monkeypatch.setattr("config.salesman_excel.excel_numbers_collapsed", lambda: True)
    assert get_salesman_number("REdwards") == "080"
    assert get_salesman_number("HKaufman") == "029"
