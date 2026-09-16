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
