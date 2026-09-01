from web.auth.public_origin import public_origin


def test_azure_defaults_to_public_reports_host(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("WEBSITE_SITE_NAME", "achim-sales-reports")
    assert public_origin() == "https://reports.achimonline.com"


def test_explicit_public_base_url_wins(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test/")
    monkeypatch.setenv("WEBSITE_SITE_NAME", "achim-sales-reports")
    assert public_origin() == "https://example.test"


def test_local_dev_uses_loopback_origin(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
    monkeypatch.delenv("WEBSITE_INSTANCE_ID", raising=False)
    assert public_origin() == "http://127.0.0.1:5001"
