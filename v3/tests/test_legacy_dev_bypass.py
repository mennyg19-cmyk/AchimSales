"""Legacy app development-auth guard."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from webapp import config


def test_dev_bypass_refuses_azure_and_prod(monkeypatch):
    monkeypatch.setenv("DEV_BYPASS_AUTH", "true")
    monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert config._dev_bypass_enabled()

    monkeypatch.setenv("WEBSITE_SITE_NAME", "achim-sales-reports")
    assert not config._dev_bypass_enabled()

    monkeypatch.delenv("WEBSITE_SITE_NAME")
    monkeypatch.setenv("APP_ENV", "PrOd")
    assert not config._dev_bypass_enabled()
