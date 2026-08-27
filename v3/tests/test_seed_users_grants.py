"""Live→v3 salesman grants replace revoked keys instead of only adding."""

import sqlite3

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
