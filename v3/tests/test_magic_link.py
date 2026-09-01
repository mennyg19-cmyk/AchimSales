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


def test_token_not_stored_plaintext(db):
    tokens = MagicLinkRepository(db)
    token = tokens.create_token("rep@x.com")
    assert token
    with db.precious() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(magic_link_tokens)")]
        blob = " ".join(
            str(r["token_hash"]) for r in conn.execute("SELECT token_hash FROM magic_link_tokens")
        )
    assert "token_hash" in cols
    assert "token" not in cols
    assert token not in blob


def test_prune_old_attempts_and_tokens(db):
    tokens = MagicLinkRepository(db)
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO magic_link_attempts (email, ip, created_at) "
            "VALUES ('a@x.com','1.1.1.1','2000-01-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO magic_link_tokens "
            "(token_hash, email, created_at, expires_at) "
            "VALUES ('deadbeef','a@x.com','2000-01-01T00:00:00+00:00',"
            "'2000-01-01T00:15:00+00:00')"
        )
    assert tokens.prune(older_than_days=90) >= 2


def test_redact_magic_link_filter():
    import logging

    from web.auth.log_redact import RedactMagicLinkFilter

    rec = logging.LogRecord(
        "x", logging.INFO, "", 0,
        "GET /login/magic-link/abcDEF123xyz HTTP/1.1", (), None,
    )
    assert RedactMagicLinkFilter().filter(rec)
    assert "<redacted>" in rec.getMessage()
    assert "abcDEF123xyz" not in rec.getMessage()
