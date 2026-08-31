"""Live→v3 salesman grants replace revoked keys instead of only adding."""

import inspect
import json
import sqlite3

from web.background import bootstrap_background
from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.users import UserRepository
from web.data.seed_users import copy_live_users, read_live_users


def _live_db(path, *, key: str, extra_keys=()):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE app_users (
            email TEXT PRIMARY KEY,
            role TEXT,
            salesman_key TEXT,
            display_name TEXT,
            dashboard_enabled INTEGER,
            is_external INTEGER
        );
        CREATE TABLE user_salesman_access (
            user_email TEXT,
            salesman_key TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO app_users VALUES ('rep@x.com', 'salesman', ?, 'Rep', 1, 0)",
        (key,),
    )
    conn.execute(
        "INSERT INTO user_salesman_access VALUES ('rep@x.com', ?)",
        (key,),
    )
    for extra in extra_keys:
        conn.execute(
            "INSERT INTO user_salesman_access VALUES ('rep@x.com', ?)",
            (extra,),
        )
    conn.commit()
    conn.close()


def _cli_app(tmp_path):
    from web import create_app
    from web.config import Config

    cfg = Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="",
    )
    app = create_app(cfg)
    migrate(app.config["DB"])
    return app


def test_second_copy_drops_revoked_salesman_grant(tmp_path):
    live = tmp_path / "live.db"
    _live_db(live, key="akey")
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    with db.precious() as conn:
        conn.execute("INSERT INTO salesmen(key) VALUES ('akey'), ('bkey')")

    copy_live_users(db, read_live_users(live))
    uid = UserRepository(db).get_by_email("rep@x.com").id
    with db.precious() as conn:
        keys = {r[0] for r in conn.execute(
            "SELECT salesman_key FROM user_salesman_access WHERE user_id = ?", (uid,)
        )}
    assert keys == {"akey"}

    live.unlink()
    _live_db(live, key="bkey")
    copy_live_users(db, read_live_users(live))
    with db.precious() as conn:
        keys = {r[0] for r in conn.execute(
            "SELECT salesman_key FROM user_salesman_access WHERE user_id = ?", (uid,)
        )}
    assert keys == {"bkey"}


def test_bootstrap_does_not_seed_from_live():
    src = inspect.getsource(bootstrap_background)
    assert "seed_users_from_live" not in src
    assert "_seed_users_from_live" not in src


def test_import_live_users_cli_records_marker(tmp_path, monkeypatch):
    live = tmp_path / "live.db"
    _live_db(live, key="akey")
    app = _cli_app(tmp_path)
    with app.config["DB"].precious() as conn:
        conn.execute("INSERT INTO salesmen(key) VALUES ('akey')")
    monkeypatch.setenv("LIVE_DB_PATH", str(live))
    result = app.test_cli_runner().invoke(args=["import-live-users"])
    assert result.exit_code == 0
    assert "Imported" in (result.output or "")
    with app.config["DB"].precious() as conn:
        raw = conn.execute(
            "SELECT value FROM app_settings WHERE key='live_user_import'"
        ).fetchone()[0]
        n_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        n_grants = conn.execute("SELECT COUNT(*) FROM user_salesman_access").fetchone()[0]
    data = json.loads(raw)
    assert data["users"] == n_users == 1
    assert data["grants"] == n_grants == 1
    assert str(live) in data["path"]
    assert data["at"]


def test_import_live_users_cli_fails_when_source_missing(tmp_path, monkeypatch):
    app = _cli_app(tmp_path)
    missing = tmp_path / "no-such.db"
    monkeypatch.setenv("LIVE_DB_PATH", str(missing))
    result = app.test_cli_runner().invoke(args=["import-live-users"])
    assert result.exit_code != 0
    text = f"{result.output or ''}{result.exception or ''}".lower()
    assert "not found" in text
    with app.config["DB"].precious() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key='live_user_import'"
        ).fetchone()
    assert row is None


def test_import_live_users_cli_records_imported_grants_not_table_total(tmp_path, monkeypatch):
    live = tmp_path / "live.db"
    _live_db(live, key="akey")
    app = _cli_app(tmp_path)
    db = app.config["DB"]
    other = UserRepository(db).upsert("other@x.com", role="salesman")
    with db.precious() as conn:
        conn.execute("INSERT INTO salesmen(key) VALUES ('akey'), ('zkey')")
        conn.execute(
            "INSERT INTO user_salesman_access(user_id, salesman_key) VALUES (?, 'zkey')",
            (other.id,),
        )
    monkeypatch.setenv("LIVE_DB_PATH", str(live))
    result = app.test_cli_runner().invoke(args=["import-live-users"])
    assert result.exit_code == 0
    with db.precious() as conn:
        raw = conn.execute(
            "SELECT value FROM app_settings WHERE key='live_user_import'"
        ).fetchone()[0]
        table_grants = conn.execute("SELECT COUNT(*) FROM user_salesman_access").fetchone()[0]
    data = json.loads(raw)
    assert table_grants == 2
    assert data["users"] == 1
    assert data["grants"] == 1
