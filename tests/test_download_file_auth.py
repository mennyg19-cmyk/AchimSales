"""Legacy download-file must not serve another user's workbook."""

import os

from webapp.report_download import is_under_root, resolve_history_xlsx


def test_prefix_sibling_directory_is_rejected(tmp_path):
    reports = tmp_path / "Direct Reports"
    reports.mkdir()
    sibling = tmp_path / "Direct Reports-evil"
    sibling.mkdir()
    secret = sibling / "secret.xlsx"
    secret.write_bytes(b"PK")
    assert is_under_root(str(secret), str(reports)) is False
    assert resolve_history_xlsx(str(secret), str(reports), [str(secret)]) is None


def test_owned_xlsx_under_root_is_allowed(tmp_path):
    reports = tmp_path / "Direct Reports"
    reports.mkdir()
    owned = reports / "mine.xlsx"
    owned.write_bytes(b"PK")
    assert resolve_history_xlsx(str(owned), str(reports), [str(owned)]) == os.path.realpath(owned)


def test_other_users_xlsx_under_root_is_rejected(tmp_path):
    reports = tmp_path / "Direct Reports"
    reports.mkdir()
    other = reports / "other.xlsx"
    other.write_bytes(b"PK")
    assert resolve_history_xlsx(str(other), str(reports), []) is None


def test_non_xlsx_is_rejected(tmp_path):
    reports = tmp_path / "Direct Reports"
    reports.mkdir()
    owned = reports / "mine.txt"
    owned.write_text("no")
    assert resolve_history_xlsx(str(owned), str(reports), [str(owned)]) is None
