"""The V3_DEVELOPER_EMAILS seed: developers are created if missing and win over
the admin seed (so an email in both V2_ADMIN_EMAILS and V3_DEVELOPER_EMAILS ends
up 'developer', not 'admin')."""

from __future__ import annotations

from web import _seed_admins, _seed_developers, create_app
from web.config import Config
from web.data.migrate import migrate
from web.data.repositories.users import UserRepository


def _cfg(tmp_path) -> Config:
    return Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="", new_app_marker=True,
        outbox_dir=tmp_path / "outbox",
    )


def test_developer_seed_creates_and_outranks_admin(tmp_path, monkeypatch):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    db = app.config["DB"]
    users = UserRepository(db)

    # mennyg@achimonline.com is in the admin env (forced admin); mennyg@ad... is
    # not in any directory yet (must be created by the developer seed).
    monkeypatch.setenv("V2_ADMIN_EMAILS", "mennyg@achimonline.com")
    monkeypatch.delenv("V3_ADMIN_EMAILS", raising=False)
    monkeypatch.setenv(
        "V3_DEVELOPER_EMAILS",
        "mennyg@achimonline.com, mennyg@ad.achimonline.com",
    )

    _seed_admins(app, db)       # would leave the first email as 'admin'
    _seed_developers(app, db)   # runs last -> both become developers

    assert users.get_by_email("mennyg@achimonline.com").role == "developer"
    assert users.get_by_email("mennyg@ad.achimonline.com").role == "developer"
    assert users.get_by_email("mennyg@achimonline.com").can_see_company_views is True
    assert users.get_by_email("mennyg@ad.achimonline.com").can_see_company_views is True


def test_developer_seed_noop_without_env(tmp_path, monkeypatch):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    db = app.config["DB"]
    monkeypatch.delenv("V3_DEVELOPER_EMAILS", raising=False)

    _seed_developers(app, db)  # nothing configured -> no rows

    assert UserRepository(db).get_by_email("mennyg@achimonline.com") is None


def test_copy_live_users_sets_developer_flag_on_insert_only(tmp_path):
    from web.data.seed_users import copy_live_users

    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    db = app.config["DB"]
    users = UserRepository(db)
    copy_live_users(db, [
        {"email": "dev@x.com", "role": "developer", "salesman_key": None,
         "display_name": "Dev", "dashboard_enabled": 1, "is_external": 0},
        {"email": "sm@x.com", "role": "salesman", "salesman_key": None,
         "display_name": "Sm", "dashboard_enabled": 0, "is_external": 0},
    ])
    assert users.get_by_email("dev@x.com").can_see_company_views is True
    assert users.get_by_email("sm@x.com").can_see_company_views is False
    users.update(users.get_by_email("dev@x.com").id, can_see_company_views=False)
    copy_live_users(db, [
        {"email": "dev@x.com", "role": "developer", "salesman_key": None,
         "display_name": "Dev", "dashboard_enabled": 1, "is_external": 0},
    ])
    assert users.get_by_email("dev@x.com").can_see_company_views is False
    users.update(users.get_by_email("dev@x.com").id, display_name="Renamed Dev")
    copy_live_users(db, [
        {"email": "dev@x.com", "role": "developer", "salesman_key": None,
         "display_name": "Dev", "dashboard_enabled": 1, "is_external": 0},
    ])
    assert users.get_by_email("dev@x.com").display_name == "Renamed Dev"


def test_copy_live_users_keeps_existing_v3_role(tmp_path):
    from web.data.seed_users import copy_live_users

    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    db = app.config["DB"]
    users = UserRepository(db)
    copy_live_users(db, [
        {"email": "rep@x.com", "role": "salesman", "salesman_key": None,
         "display_name": "Rep", "dashboard_enabled": 0, "is_external": 0},
    ])
    users.update(users.get_by_email("rep@x.com").id, role="manager")
    copy_live_users(db, [
        {"email": "rep@x.com", "role": "salesman", "salesman_key": None,
         "display_name": "Rep", "dashboard_enabled": 0, "is_external": 0},
    ])
    assert users.get_by_email("rep@x.com").role == "manager"


def test_copy_live_users_grants_salesman_key_without_salesmen_row(tmp_path):
    from web.data.seed_users import copy_live_users

    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    db = app.config["DB"]
    copy_live_users(db, [
        {"email": "hk@x.com", "role": "salesman", "salesman_key": "HKaufman",
         "display_name": "Heshy", "dashboard_enabled": 0, "is_external": 0},
    ])
    users = UserRepository(db)
    uid = users.get_by_email("hk@x.com").id
    assert users.get_salesman_access(uid) == {"hkaufman"}
