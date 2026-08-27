"""Magic-link tokens: one live link, atomic claim, rate limits."""

import pytest

from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.magic_links import MagicLinkRepository


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "precious.db", tmp_path / "cache.db")
    migrate(d)
    return d


def test_new_token_invalidates_previous(db):
    tokens = MagicLinkRepository(db)
    first = tokens.create_token("rep@x.com")
    second = tokens.create_token("rep@x.com")
    assert first and second and first != second
    assert tokens.consume_token(first) is None
    assert tokens.consume_token(second) == "rep@x.com"


def test_consume_is_one_shot(db):
    tokens = MagicLinkRepository(db)
    token = tokens.create_token("rep@x.com")
    assert tokens.consume_token(token) == "rep@x.com"
    assert tokens.consume_token(token) is None


def test_email_rate_limit_after_five(db):
    tokens = MagicLinkRepository(db)
    for _ in range(5):
        assert tokens.create_token("rep@x.com")
    assert tokens.create_token("rep@x.com") is None


def test_ip_rate_limit(db):
    tokens = MagicLinkRepository(db)
    for _ in range(39):
        tokens.record_attempt("a@x.com", "1.2.3.4")
    assert tokens.ip_rate_limited("1.2.3.4") is False
    tokens.record_attempt("a@x.com", "1.2.3.4")
    assert tokens.ip_rate_limited("1.2.3.4") is True
    assert tokens.ip_rate_limited("9.9.9.9") is False
