"""Security: the app must fail closed on insecure production config (rule 6)."""

from pathlib import Path

import pytest

from web.config import Config, ConfigError


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
        precious_db_path=Path("/tmp/v3data/precious.db"),
        cache_db_path=Path("/tmp/v3data/cache.db"),
        litestream_blob_url="abs://container/precious",
        litestream_azure_account_name="acct",
        litestream_azure_account_key="key",
        litestream_azure_container="container",
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


def test_prod_rejects_missing_litestream_azure_key():
    with pytest.raises(ConfigError, match="LITESTREAM_AZURE_ACCOUNT_KEY"):
        _cfg(litestream_azure_account_key="").validate()


def test_prod_rejects_missing_litestream_account_name():
    with pytest.raises(ConfigError, match="LITESTREAM_AZURE_ACCOUNT_NAME"):
        _cfg(litestream_azure_account_name="").validate()


def test_prod_blob_url_alone_is_not_enough():
    with pytest.raises(ConfigError, match="LITESTREAM_AZURE"):
        _cfg(
            litestream_blob_url="abs://container/precious",
            litestream_azure_account_key="",
            litestream_azure_account_name="",
            litestream_azure_container="",
        ).validate()


def test_prod_rejects_unc_db_path():
    with pytest.raises(ConfigError, match="UNC/SMB"):
        _cfg(precious_db_path=Path(r"\\fileserver\share\precious.db")).validate()


def test_prod_rejects_home_share_db_path():
    # /home on App Service is Azure Files (SMB); SQLite WAL breaks the job worker
    # there. This is the exact regression that stalled the queue in June 2026.
    with pytest.raises(ConfigError, match="/home share"):
        _cfg(precious_db_path=Path("/home/site/v3data/precious.db")).validate()


def test_prod_rejects_home_share_via_dotdot():
    with pytest.raises(ConfigError, match="/home share"):
        _cfg(precious_db_path=Path("/tmp/../home/site/v3data/precious.db")).validate()


def test_prod_rejects_relative_db_path():
    with pytest.raises(ConfigError, match="absolute local-disk path"):
        _cfg(precious_db_path=Path("./.data/precious.db")).validate()


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


def test_reports_only_alias_tracks_is_beta():
    assert _cfg(is_beta=True).reports_only is True
    assert _cfg().reports_only is False


def test_prod_home_rejects_home_share_db_path():
    with pytest.raises(ConfigError, match="SITE_PRECIOUS_DB_PATH"):
        _cfg(
            is_beta=True,
            precious_db_path=Path("/home/site/v3data/precious.db"),
            litestream_azure_replica_path="site-precious.db",
        ).validate()


def _prod_home_env(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("AUTH_MODE", "msal")
    monkeypatch.setenv("FLASK_SECRET_KEY", "a-strong-secret")
    monkeypatch.setenv("GRAPH_TENANT_ID", "t")
    monkeypatch.setenv("GRAPH_CLIENT_ID", "c")
    monkeypatch.setenv("GRAPH_CLIENT_SECRET", "s")
    monkeypatch.setenv("REPORTING_API_BASE_URL", "https://api.example")
    monkeypatch.setenv("REPORTING_API_KEY", "k")
    monkeypatch.setenv("LITESTREAM_AZURE_ACCOUNT_NAME", "acct")
    monkeypatch.setenv("LITESTREAM_AZURE_ACCOUNT_KEY", "key")
    monkeypatch.setenv("LITESTREAM_AZURE_CONTAINER", "container")
    monkeypatch.setenv("SITE_PRECIOUS_DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setenv("SITE_CACHE_DB_PATH", str(tmp_path / "c.db"))
    monkeypatch.setenv("LITESTREAM_AZURE_SITE_PATH", "site-precious.db")
    monkeypatch.delenv("PRECIOUS_DB_PATH", raising=False)
    monkeypatch.delenv("CACHE_DB_PATH", raising=False)
    monkeypatch.delenv("LITESTREAM_AZURE_PATH", raising=False)
    monkeypatch.delenv("BETA_PRECIOUS_DB_PATH", raising=False)
    monkeypatch.delenv("BETA_CACHE_DB_PATH", raising=False)
    monkeypatch.delenv("LITESTREAM_AZURE_BETA_PATH", raising=False)


def test_load_config_prefers_site_over_beta(monkeypatch, tmp_path):
    from web.config import load_config

    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    site = tmp_path / "site.db"
    monkeypatch.setenv("SITE_PRECIOUS_DB_PATH", str(site))
    monkeypatch.setenv("BETA_PRECIOUS_DB_PATH", str(tmp_path / "beta.db"))
    monkeypatch.setenv("SITE_CACHE_DB_PATH", str(tmp_path / "sc.db"))
    cfg = load_config(is_beta=True)
    assert cfg.precious_db_path == site


def test_load_config_beta_alias_when_site_unset(monkeypatch, tmp_path):
    from web.config import load_config

    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.delenv("SITE_PRECIOUS_DB_PATH", raising=False)
    beta = tmp_path / "beta.db"
    monkeypatch.setenv("BETA_PRECIOUS_DB_PATH", str(beta))
    monkeypatch.setenv("BETA_CACHE_DB_PATH", str(tmp_path / "bc.db"))
    cfg = load_config(is_beta=True)
    assert cfg.precious_db_path == beta


def test_prod_home_requires_explicit_db_path(monkeypatch, tmp_path):
    from web.config import load_config

    _prod_home_env(monkeypatch, tmp_path)
    monkeypatch.delenv("SITE_PRECIOUS_DB_PATH", raising=False)
    monkeypatch.delenv("BETA_PRECIOUS_DB_PATH", raising=False)
    with pytest.raises(ConfigError, match="SITE_PRECIOUS_DB_PATH or BETA_PRECIOUS_DB_PATH"):
        load_config(is_beta=True)


def test_prod_home_requires_site_or_beta_replica_path(monkeypatch, tmp_path):
    from web.config import load_config

    _prod_home_env(monkeypatch, tmp_path)
    monkeypatch.delenv("LITESTREAM_AZURE_SITE_PATH", raising=False)
    monkeypatch.setenv("LITESTREAM_AZURE_PATH", "test-precious.db")
    with pytest.raises(ConfigError, match="LITESTREAM_AZURE_SITE_PATH"):
        load_config(is_beta=True)


def test_prod_home_does_not_require_legacy_precious_path(monkeypatch, tmp_path):
    from web.config import load_config

    _prod_home_env(monkeypatch, tmp_path)
    cfg = load_config(is_beta=True)
    assert cfg.precious_db_path == tmp_path / "p.db"
    assert cfg.litestream_azure_replica_path == "site-precious.db"


def test_prod_home_replica_beta_alias(monkeypatch, tmp_path):
    from web.config import load_config

    _prod_home_env(monkeypatch, tmp_path)
    monkeypatch.delenv("LITESTREAM_AZURE_SITE_PATH", raising=False)
    monkeypatch.setenv("LITESTREAM_AZURE_BETA_PATH", "beta-precious.db")
    cfg = load_config(is_beta=True)
    assert cfg.litestream_azure_replica_path == "beta-precious.db"
