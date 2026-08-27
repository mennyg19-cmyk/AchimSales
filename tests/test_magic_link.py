"""Magic-link tokens: one live link, atomic claim, rate limits."""

import sqlite3

import pytest

from webapp.db import (
    consume_magic_link_token,
    create_magic_link_token,
    magic_link_ip_rate_limited,
    record_magic_link_attempt,
)


@pytest.fixture
def token_db(tmp_path, monkeypatch):
    path = str(tmp_path / "app.db")
    monkeypatch.setattr("webapp.db.DB_PATH", path)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE magic_link_tokens (
            token TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            request_ip TEXT
        );
        CREATE TABLE magic_link_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            ip TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.close()
    return path


def test_new_token_invalidates_previous(token_db):
    first = create_magic_link_token("rep@x.com")
    second = create_magic_link_token("rep@x.com")
    assert first and second and first != second
    assert consume_magic_link_token(first) is None
    assert consume_magic_link_token(second) == "rep@x.com"


def test_consume_is_one_shot(token_db):
    token = create_magic_link_token("rep@x.com")
    assert consume_magic_link_token(token) == "rep@x.com"
    assert consume_magic_link_token(token) is None


def test_email_rate_limit_after_five(token_db):
    for _ in range(5):
        assert create_magic_link_token("rep@x.com")
    assert create_magic_link_token("rep@x.com") is None


def test_ip_rate_limit(token_db):
    for _ in range(39):
        record_magic_link_attempt("a@x.com", "1.2.3.4")
    assert magic_link_ip_rate_limited("1.2.3.4") is False
    record_magic_link_attempt("a@x.com", "1.2.3.4")
    assert magic_link_ip_rate_limited("1.2.3.4") is True
    assert magic_link_ip_rate_limited("9.9.9.9") is False
