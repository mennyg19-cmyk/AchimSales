"""DEV_BYPASS_AUTH must not work in production or on Azure."""

import pytest

from webapp.config import dev_bypass_auth, reject_production_dev_bypass


def test_prod_rejects_dev_bypass(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DEV_BYPASS_AUTH", "true")
    monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
    monkeypatch.delenv("WEBSITE_INSTANCE_ID", raising=False)
    with pytest.raises(RuntimeError, match="DEV_BYPASS_AUTH"):
        reject_production_dev_bypass()
    assert dev_bypass_auth() is False


def test_dev_allows_dev_bypass(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("DEV_BYPASS_AUTH", "true")
    monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
    monkeypatch.delenv("WEBSITE_INSTANCE_ID", raising=False)
    reject_production_dev_bypass()
    assert dev_bypass_auth() is True


def test_azure_rejects_dev_bypass_even_if_app_env_dev(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("DEV_BYPASS_AUTH", "true")
    monkeypatch.setenv("WEBSITE_SITE_NAME", "achim-sales-reports")
    with pytest.raises(RuntimeError, match="never on Azure"):
        reject_production_dev_bypass()
    assert dev_bypass_auth() is False


def test_unset_bypass_does_not_raise(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("DEV_BYPASS_AUTH", raising=False)
    monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
    monkeypatch.delenv("WEBSITE_INSTANCE_ID", raising=False)
    reject_production_dev_bypass()
    assert dev_bypass_auth() is False
