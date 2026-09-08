import sqlite3

from flask import Flask

from webapp import db as live_db
from webapp.blueprints import auth as live_auth


def test_magic_link_tokens_store_hash_and_consume_once(monkeypatch, tmp_path):
    monkeypatch.setattr(live_db, "DB_PATH", str(tmp_path / "live.db"))
    live_db.init_db()

    token = live_db.create_magic_link_token("external@x.com")
    conn = live_db.get_db()
    try:
        row = conn.execute("SELECT token_hash FROM magic_link_tokens").fetchone()
    finally:
        conn.close()

    assert row["token_hash"] != token
    assert live_db.consume_magic_link_token(token) == "external@x.com"
    assert live_db.consume_magic_link_token(token) is None


def test_magic_link_replaces_outstanding_token_for_same_email(monkeypatch, tmp_path):
    monkeypatch.setattr(live_db, "DB_PATH", str(tmp_path / "live.db"))
    live_db.init_db()
    first = live_db.create_magic_link_token("external@x.com")
    second = live_db.create_magic_link_token("external@x.com")
    assert live_db.consume_magic_link_token(first) is None
    assert live_db.consume_magic_link_token(second) == "external@x.com"


def test_magic_link_schema_replaces_plaintext_tokens(monkeypatch, tmp_path):
    db_path = tmp_path / "live.db"
    monkeypatch.setattr(live_db, "DB_PATH", str(db_path))
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE magic_link_tokens (token TEXT PRIMARY KEY, email TEXT NOT NULL,"
            " created_at TEXT NOT NULL, expires_at TEXT NOT NULL, consumed_at TEXT)"
        )
        conn.commit()
    finally:
        conn.close()

    live_db.init_db()
    conn = live_db.get_db()
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(magic_link_tokens)")}
    finally:
        conn.close()
    assert columns == {"token_hash", "email", "created_at", "expires_at", "consumed_at"}


def test_magic_link_cleanup_prunes_old_tokens(monkeypatch, tmp_path):
    monkeypatch.setattr(live_db, "DB_PATH", str(tmp_path / "live.db"))
    live_db.init_db()
    conn = live_db.get_db()
    try:
        conn.executemany(
            "INSERT INTO magic_link_tokens(token_hash, email, created_at, expires_at)"
            " VALUES (?, ?, ?, ?)",
            [
                ("old-token", "old@x.com", "2026-06-01T00:00:00+00:00", "2026-06-01T00:15:00+00:00"),
                ("recent-token", "recent@x.com", "2099-01-01T00:00:00+00:00", "2099-01-01T00:15:00+00:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    assert live_db.prune_magic_link_tokens() == 1
    conn = live_db.get_db()
    try:
        assert [row["token_hash"] for row in conn.execute(
            "SELECT token_hash FROM magic_link_tokens"
        )] == ["recent-token"]
    finally:
        conn.close()


def test_magic_link_uses_public_base_url(monkeypatch, tmp_path):
    monkeypatch.setattr(live_db, "DB_PATH", str(tmp_path / "live.db"))
    live_db.init_db()
    live_db.add_user("external@x.com", "salesman", is_external=True)
    monkeypatch.setattr(live_auth, "get_user", lambda email: {
        "email": email, "role": "salesman",
    })
    sent = {}
    from webapp.services import magic_link

    monkeypatch.setattr(
        magic_link, "send_magic_link_email",
        lambda email, link_url: sent.update(email=email, link_url=link_url),
    )
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://reports.achimonline.com/")

    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(live_auth.auth_bp)
    response = app.test_client().post("/login/magic-link", data={"email": "external@x.com"})

    assert response.status_code == 302
    assert sent["email"] == "external@x.com"
    assert sent["link_url"].startswith("https://reports.achimonline.com/login/magic-link/")


def test_magic_link_public_base_url_keeps_legacy_script_root(monkeypatch, tmp_path):
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    from werkzeug.test import Client

    monkeypatch.setattr(live_db, "DB_PATH", str(tmp_path / "live.db"))
    live_db.init_db()
    live_db.add_user("external@x.com", "salesman", is_external=True)
    monkeypatch.setattr(live_auth, "get_user", lambda email: {
        "email": email, "role": "salesman",
    })
    sent = {}
    from webapp.services import magic_link

    monkeypatch.setattr(
        magic_link, "send_magic_link_email",
        lambda email, link_url: sent.update(email=email, link_url=link_url),
    )
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://reports.achimonline.com/")

    live_app = Flask("live")
    live_app.secret_key = "test"
    live_app.register_blueprint(live_auth.auth_bp)
    mounted = DispatcherMiddleware(Flask("root"), {"/legacy": live_app})
    response = Client(mounted).post(
        "/legacy/login/magic-link", data={"email": "external@x.com"}
    )

    assert response.status_code == 302
    assert sent["link_url"].startswith(
        "https://reports.achimonline.com/legacy/login/magic-link/"
    )
