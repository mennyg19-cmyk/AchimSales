"""Legacy session role is re-read from app_users, not trusted from the cookie."""

import sqlite3

from webapp.helpers import refresh_session_user


def _users_db(tmp_path, monkeypatch, rows):
    path = str(tmp_path / "app.db")
    monkeypatch.setattr("webapp.db.DB_PATH", path)
    monkeypatch.setattr("webapp.config.dev_bypass_auth", lambda: False)
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE app_users (
            id INTEGER PRIMARY KEY,
            email TEXT,
            role TEXT,
            salesman_key TEXT,
            display_name TEXT,
            is_external INTEGER DEFAULT 0
        )"""
    )
    conn.executemany(
        "INSERT INTO app_users (email, role, salesman_key, display_name) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return path


def test_demoted_admin_cookie_becomes_salesman(tmp_path, monkeypatch):
    _users_db(tmp_path, monkeypatch, [("a@x.com", "salesman", "akey", "A")])
    out = refresh_session_user({"email": "a@x.com", "name": "A", "role": "admin"})
    assert out["role"] == "salesman"
    assert out["salesman_key"] == "akey"


def test_deleted_user_session_is_dropped(tmp_path, monkeypatch):
    _users_db(tmp_path, monkeypatch, [])
    assert refresh_session_user({"email": "gone@x.com", "role": "admin"}) is None


def test_demoted_developer_impersonation_flag_is_dropped(tmp_path, monkeypatch):
    _users_db(tmp_path, monkeypatch, [("dev@x.com", "salesman", None, "Dev")])
    out = refresh_session_user({
        "email": "dev@x.com", "role": "developer",
        "_dev": True, "_dev_email": "dev@x.com", "_dev_name": "Dev",
    })
    assert out is None
