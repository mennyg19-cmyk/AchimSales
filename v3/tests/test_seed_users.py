"""Live → home user seed: new people only; grants add, never clobber role."""

from __future__ import annotations

import sqlite3

from web import create_app
from web.config import Config
from web.data.migrate import migrate
from web.data.repositories.users import UserRepository
from web.data.seed_users import seed_users_from_live


def _cfg(tmp_path) -> Config:
    return Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="", new_app_marker=True,
        outbox_dir=tmp_path / "outbox",
    )


def _write_live(path, users, access):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE app_users (email TEXT, role TEXT, salesman_key TEXT,"
        " display_name TEXT, dashboard_enabled INTEGER, is_external INTEGER)"
    )
    conn.execute(
        "CREATE TABLE user_salesman_access (user_email TEXT, salesman_key TEXT)"
    )
    for email, role, sm_key, name in users:
        conn.execute(
            "INSERT INTO app_users VALUES (?, ?, ?, ?, 0, 0)",
            (email, role, sm_key, name),
        )
    for email, key in access:
        conn.execute(
            "INSERT INTO user_salesman_access VALUES (?, ?)", (email, key)
        )
    conn.commit()
    conn.close()


def _insert_salesman(db, key):
    with db.precious() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO salesmen(key, number, display_name, is_active)"
            " VALUES (?, '', ?, 1)",
            (key, key),
        )


def test_seed_does_not_overwrite_existing_home_role(tmp_path):
    live = tmp_path / "live.db"
    _write_live(
        live,
        [("igrossman@x.com", "manager", "IGrossman", "I Grossman")],
        [],
    )
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    db = app.config["DB"]
    users = UserRepository(db)
    users.upsert("igrossman@x.com", role="admin", display_name="I Grossman")

    seed_users_from_live(db, live)

    assert users.get_by_email("igrossman@x.com").role == "admin"


def test_seed_copies_live_salesman_access_and_keeps_home_extras(tmp_path):
    live = tmp_path / "live.db"
    _write_live(
        live,
        [("igrossman@x.com", "manager", "IGrossman", "I Grossman")],
        [
            ("igrossman@x.com", "IGrossman"),
            ("igrossman@x.com", "R.Edwards"),
            ("igrossman@x.com", "M.Kolko"),
        ],
    )
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    db = app.config["DB"]
    for key in ("igrossman", "redwards", "mkolko", "hkaufman"):
        _insert_salesman(db, key)
    users = UserRepository(db)
    home = users.upsert("igrossman@x.com", role="manager", display_name="I")
    users.add_salesman_access(home.id, ["hkaufman"])

    seed_users_from_live(db, live)

    assert users.get_by_email("igrossman@x.com").role == "manager"
    assert users.get_salesman_access(home.id) == {
        "igrossman", "redwards", "mkolko", "hkaufman",
    }


def test_seed_inserts_new_live_user(tmp_path):
    live = tmp_path / "live.db"
    _write_live(
        live,
        [("new@x.com", "salesman", "R.Edwards", "New Rep")],
        [("new@x.com", "R.Edwards")],
    )
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    db = app.config["DB"]
    _insert_salesman(db, "redwards")

    n = seed_users_from_live(db, live)

    assert n == 1
    users = UserRepository(db)
    u = users.get_by_email("new@x.com")
    assert u.role == "salesman"
    assert u.display_name == "New Rep"
    assert users.get_salesman_access(u.id) == {"redwards"}


def test_set_salesman_access_normalizes_keys(tmp_path):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    db = app.config["DB"]
    _insert_salesman(db, "redwards")
    users = UserRepository(db)
    u = users.upsert("rep@x.com", role="manager")
    users.set_salesman_access(u.id, ["R.Edwards", " r.edwards "])
    assert users.get_salesman_access(u.id) == {"redwards"}
