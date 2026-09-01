"""Phase 7: serving-db integrity before/after migrate."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from web.data.connection import Database
from web.data.migrate import apply_migrations, migrate, precious_migration_stems
from web.data.precious_integrity import (
    SENTINEL_KEY,
    SENTINEL_VALUE,
    PreciousIntegrityError,
    assert_after_migrate,
    assert_before_migrate,
    file_quick_check_ok,
)

_PRECIOUS_SQL = (
    Path(__file__).resolve().parents[1] / "web" / "data" / "migrations" / "precious"
)


def _insert_user(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO users(email, display_name, role, is_active)"
        " VALUES ('ops@achimonline.com','Ops','admin',1)"
    )
    conn.commit()
    conn.close()


def test_question_mark_filename_opens_the_named_file(tmp_path):
    path = tmp_path / "site?copy.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    conn.execute("INSERT INTO users(email) VALUES ('ops@achimonline.com')")
    conn.commit()
    conn.close()
    assert_before_migrate(path)
    assert not (tmp_path / "site").exists()
    assert file_quick_check_ok(path) is True


def test_missing_file_fails_before_migrate(tmp_path):
    with pytest.raises(PreciousIntegrityError, match="missing"):
        assert_before_migrate(tmp_path / "nope.db")
    assert file_quick_check_ok(tmp_path / "nope.db") is False


def test_zero_byte_file_fails_before_migrate(tmp_path):
    path = tmp_path / "precious.db"
    path.write_bytes(b"")
    with pytest.raises(PreciousIntegrityError, match="zero bytes"):
        assert_before_migrate(path)
    assert file_quick_check_ok(path) is False


def test_corrupt_file_fails_quick_check(tmp_path):
    path = tmp_path / "precious.db"
    path.write_bytes(b"not a sqlite database")
    with pytest.raises(PreciousIntegrityError, match="quick_check"):
        assert_before_migrate(path)
    assert file_quick_check_ok(path) is False


def test_schema_without_users_is_rejected(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    with pytest.raises(PreciousIntegrityError, match="no users"):
        assert_before_migrate(tmp_path / "p.db")
    assert file_quick_check_ok(tmp_path / "p.db") is True


def test_wrong_sentinel_is_rejected(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    _insert_user(tmp_path / "p.db")
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO app_settings(key, value) VALUES (?, ?)",
            (SENTINEL_KEY, "test"),
        )
    with pytest.raises(PreciousIntegrityError, match="site_db_role"):
        assert_after_migrate(tmp_path / "p.db")


def test_after_migrate_writes_home_sentinel(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    _insert_user(tmp_path / "p.db")
    assert_after_migrate(tmp_path / "p.db")
    with db.precious() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key=?",
            (SENTINEL_KEY,),
        ).fetchone()
    assert row["value"] == SENTINEL_VALUE


def test_archived_pre_0016_migrates_through_0016_and_later(tmp_path):
    precious = tmp_path / "precious.db"
    cache = tmp_path / "cache.db"
    early = tmp_path / "early"
    early.mkdir()
    for sql in _PRECIOUS_SQL.glob("*.sql"):
        if int(sql.stem[:4]) < 16:
            (early / sql.name).write_text(sql.read_text(encoding="utf-8"), encoding="utf-8")
    applied = apply_migrations(precious, early)
    assert "0015_company_views" in applied
    assert not any(v.startswith("0016") for v in applied)
    _insert_user(precious)
    assert_before_migrate(precious)
    result = migrate(Database(precious, cache))
    latest = precious_migration_stems()[-1]
    assert any(v.startswith("0016") for v in result["precious"])
    assert latest in result["precious"]
    assert_after_migrate(precious)
