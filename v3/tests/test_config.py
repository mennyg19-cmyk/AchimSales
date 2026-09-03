"""Security: the app must fail closed on insecure production config (rule 6)."""

from pathlib import Path

import pytest

from web.config import Config, ConfigError, load_config


def _cfg(**over):
    base = dict(
        app_env="prod",
        auth_mode="msal",
        flask_secret="a-strong-secret",
        tenant_id="t",
        client_id="c",
        client_secret="s",
        reporting_api_base_url="https://api.example",
        reporting_api_key="k",
        precious_db_path=Path("./.data/precious.db"),
        cache_db_path=Path("./.data/cache.db"),
        litestream_blob_url="abs://container/precious",
        new_app_marker=True,
    )
    base.update(over)
    return Config(**base)


def test_prod_rejects_dev_auth():
    with pytest.raises(ConfigError, match="AUTH_MODE=dev is forbidden"):
        _cfg(auth_mode="dev").validate()


def test_prod_rejects_missing_secret():
    with pytest.raises(ConfigError, match="FLASK_SECRET"):
        _cfg(flask_secret="").validate()


def test_prod_rejects_missing_reporting_api():
    with pytest.raises(ConfigError, match="REPORTING_API"):
        _cfg(reporting_api_base_url="", reporting_api_key="").validate()


def test_prod_rejects_missing_msal_creds():
    with pytest.raises(ConfigError, match="GRAPH_"):
        _cfg(client_secret="").validate()


def test_prod_rejects_missing_litestream():
    with pytest.raises(ConfigError, match="LITESTREAM_BLOB_URL"):
        _cfg(litestream_blob_url="").validate()


def test_prod_rejects_unc_db_path():
    with pytest.raises(ConfigError, match="UNC/SMB"):
        _cfg(precious_db_path=Path(r"\\fileserver\share\precious.db")).validate()


def test_prod_rejects_home_share_db_path():
    # /home on App Service is Azure Files (SMB); SQLite WAL breaks the job worker
    # there. This is the exact regression that stalled the queue in June 2026.
    with pytest.raises(ConfigError, match="/home share"):
        _cfg(precious_db_path=Path("/home/site/v3data/precious.db")).validate()


def test_prod_accepts_local_tmp_db_path():
    _cfg(
        precious_db_path=Path("/tmp/v3data/precious.db"),
        cache_db_path=Path("/tmp/v3data/cache.db"),
    ).validate()  # should not raise


def test_valid_prod_config_passes():
    _cfg().validate()  # should not raise


def test_dev_config_is_permissive():
    # Locally none of the prod guards apply (no litestream, no secret, dev auth).
    _cfg(app_env="dev", auth_mode="dev", flask_secret="", litestream_blob_url="").validate()


def test_home_config_falls_back_when_site_paths_are_unset(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("PRECIOUS_DB_PATH", "/tmp/fallback-precious.db")
    monkeypatch.setenv("CACHE_DB_PATH", "/tmp/fallback-cache.db")
    monkeypatch.delenv("SITE_PRECIOUS_DB_PATH", raising=False)
    monkeypatch.delenv("SITE_CACHE_DB_PATH", raising=False)

    cfg = load_config()

    assert cfg.precious_db_path == Path("/tmp/fallback-precious.db")
    assert cfg.cache_db_path == Path("/tmp/fallback-cache.db")


def test_home_config_prefers_site_paths(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("PRECIOUS_DB_PATH", "/tmp/fallback-precious.db")
    monkeypatch.setenv("CACHE_DB_PATH", "/tmp/fallback-cache.db")
    monkeypatch.setenv("SITE_PRECIOUS_DB_PATH", " /tmp/site-precious.db ")
    monkeypatch.setenv("SITE_CACHE_DB_PATH", " /tmp/site-cache.db ")

    cfg = load_config()

    assert cfg.precious_db_path == Path("/tmp/site-precious.db")
    assert cfg.cache_db_path == Path("/tmp/site-cache.db")


def test_prod_rejects_home_share_site_precious_path(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("AUTH_MODE", "msal")
    monkeypatch.setenv("FLASK_SECRET", "a-strong-secret")
    monkeypatch.setenv("GRAPH_TENANT_ID", "t")
    monkeypatch.setenv("GRAPH_CLIENT_ID", "c")
    monkeypatch.setenv("GRAPH_CLIENT_SECRET", "s")
    monkeypatch.setenv("REPORTING_API_BASE_URL", "https://api.example")
    monkeypatch.setenv("REPORTING_API_KEY", "k")
    monkeypatch.setenv("LITESTREAM_BLOB_URL", "abs://container/precious")
    monkeypatch.setenv("SITE_PRECIOUS_DB_PATH", "/home/site/v3data/precious.db")
    monkeypatch.setenv("CACHE_DB_PATH", "/tmp/fallback-cache.db")
    monkeypatch.delenv("SITE_CACHE_DB_PATH", raising=False)

    with pytest.raises(ConfigError, match="/home share"):
        load_config()


def test_beta_config_ignores_site_paths(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SITE_PRECIOUS_DB_PATH", "/tmp/site-precious.db")
    monkeypatch.setenv("SITE_CACHE_DB_PATH", "/tmp/site-cache.db")
    monkeypatch.setenv("BETA_PRECIOUS_DB_PATH", "/tmp/beta-precious.db")
    monkeypatch.setenv("BETA_CACHE_DB_PATH", "/tmp/beta-cache.db")

    cfg = load_config(is_beta=True)

    assert cfg.precious_db_path == Path("/tmp/beta-precious.db")
    assert cfg.cache_db_path == Path("/tmp/beta-cache.db")
