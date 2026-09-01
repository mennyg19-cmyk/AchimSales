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
        litestream_blob_url="",
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


def test_developer_seed_noop_without_env(tmp_path, monkeypatch):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    db = app.config["DB"]
    monkeypatch.delenv("V3_DEVELOPER_EMAILS", raising=False)

    _seed_developers(app, db)  # nothing configured -> no rows

    assert UserRepository(db).get_by_email("mennyg@achimonline.com") is None
