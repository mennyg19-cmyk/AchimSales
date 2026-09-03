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


def test_public_base_url_missing_in_prod(monkeypatch):
    monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    assert not config._public_base_url_missing_in_prod()

    monkeypatch.setenv("APP_ENV", "prod")
    assert config._public_base_url_missing_in_prod()

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://reports.achimonline.com")
    assert not config._public_base_url_missing_in_prod()

    monkeypatch.delenv("PUBLIC_BASE_URL")
    monkeypatch.delenv("APP_ENV")
    monkeypatch.setenv("WEBSITE_SITE_NAME", "achim-sales-reports")
    assert config._public_base_url_missing_in_prod()


def test_preset_copy_rejects_path_traversal():
    from webapp.report_api import _safe_path_part

    assert _safe_path_part("../../../tmp", "shared") == "shared"
    assert _safe_path_part("MKolko", "shared") == "MKolko"
    assert _safe_path_part("a/b", "shared") == "shared"
