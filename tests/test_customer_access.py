"""Customer/order access fails closed when book data is missing."""

import os
import sqlite3

from webapp.services.access import (
    check_customer_access,
    user_can_access_customer,
    visible_salesman_keys,
)


def _cache_db(tmp_path, monkeypatch, rows, grants=()):
    path = str(tmp_path / "app.db")
    if os.path.exists(path):
        os.unlink(path)
    monkeypatch.setattr("webapp.db.DB_PATH", path)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE dashboard_cache (customer_account TEXT, sales_group TEXT)"
    )
    conn.executemany(
        "INSERT INTO dashboard_cache VALUES (?, ?)",
        rows,
    )
    conn.execute(
        "CREATE TABLE user_salesman_access (user_email TEXT, salesman_key TEXT)"
    )
    conn.executemany(
        "INSERT INTO user_salesman_access VALUES (?, ?)",
        grants,
    )
    conn.commit()
    conn.close()


def test_missing_cache_is_denied(tmp_path, monkeypatch):
    _cache_db(tmp_path, monkeypatch, [])
    assert check_customer_access("mkolko", "100") is False


def test_missing_salesman_key_is_denied(tmp_path, monkeypatch):
    _cache_db(tmp_path, monkeypatch, [("100", "M Kolko")])
    assert check_customer_access(None, "100") is False
    assert check_customer_access("", "100", is_admin=False) is False
    assert check_customer_access(None, "100", is_admin=True) is True


def test_salesman_matches_book(tmp_path, monkeypatch):
    _cache_db(tmp_path, monkeypatch, [("100", "M Kolko")])
    assert check_customer_access("mkolko", "100") is True
    assert check_customer_access("hkaufman", "100") is False


def test_manager_needs_grant_and_known_book(tmp_path, monkeypatch):
    _cache_db(tmp_path, monkeypatch, [("100", "M Kolko")], grants=[("mgr@x.com", "mkolko")])
    mgr = {"email": "mgr@x.com", "role": "manager"}
    assert user_can_access_customer(mgr, "100") is True
    assert user_can_access_customer(mgr, "999") is False


def test_manager_without_matching_grant_is_denied(tmp_path, monkeypatch):
    _cache_db(tmp_path, monkeypatch, [("100", "M Kolko")], grants=[("mgr@x.com", "hkaufman")])
    mgr = {"email": "mgr@x.com", "role": "manager"}
    assert user_can_access_customer(mgr, "100") is False


def test_blank_sales_group_falls_back_to_cache(tmp_path, monkeypatch):
    _cache_db(tmp_path, monkeypatch, [("100", "M Kolko")])
    sm = {"email": "rep@x.com", "role": "salesman", "salesman_key": "mkolko"}
    assert user_can_access_customer(sm, "100", sales_group="") is True
    assert user_can_access_customer(sm, "100", sales_group=None) is True


def test_d365_sales_group_can_authorize_without_cache(tmp_path, monkeypatch):
    _cache_db(tmp_path, monkeypatch, [])
    sm = {"email": "rep@x.com", "role": "salesman", "salesman_key": "mkolko"}
    assert user_can_access_customer(sm, "100") is False
    assert user_can_access_customer(sm, "100", sales_group="M Kolko") is True


def test_visible_keys_scope_list(tmp_path, monkeypatch):
    _cache_db(tmp_path, monkeypatch, [("100", "M Kolko")], grants=[("mgr@x.com", "mkolko")])
    admin = {"email": "a@x.com", "role": "admin"}
    assert visible_salesman_keys(admin) is None
    assert visible_salesman_keys(admin, "hkaufman") == {"hkaufman"}

    mgr = {"email": "mgr@x.com", "role": "manager"}
    assert visible_salesman_keys(mgr) == {"mkolko"}
    assert visible_salesman_keys(mgr, "mkolko") == {"mkolko"}
    assert visible_salesman_keys(mgr, "hkaufman") == set()

    sm = {"email": "rep@x.com", "role": "salesman", "salesman_key": "mkolko"}
    assert visible_salesman_keys(sm) == {"mkolko"}
    assert visible_salesman_keys(sm, "hkaufman") == set()
    assert visible_salesman_keys({"email": "x@x.com", "role": "salesman"}) == set()
