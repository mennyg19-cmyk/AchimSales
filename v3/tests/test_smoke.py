"""Smoke: app boots in dev, health is minimal, CSRF guards writes."""

from pathlib import Path

import pytest

from web import create_app
from web.config import Config


def _prod_cfg(tmp_path) -> Config:
    return Config(
        app_env="prod",
        auth_mode="msal",
        flask_secret="test-secret",
        tenant_id="t",
        client_id="c",
        client_secret="s",
        reporting_api_base_url="https://api.example",
        reporting_api_key="k",
        precious_db_path=tmp_path / "precious.db",
        cache_db_path=tmp_path / "cache.db",
        litestream_blob_url="",
        litestream_azure_account_name="acct",
        litestream_azure_account_key="key",
        litestream_azure_container="container",
    )


@pytest.fixture
def app():
    cfg = Config(
        app_env="dev",
        auth_mode="dev",
        flask_secret="test-secret",
        tenant_id="",
        client_id="",
        client_secret="",
        reporting_api_base_url="",
        reporting_api_key="",
        precious_db_path=Path("./.data/precious.db"),
        cache_db_path=Path("./.data/cache.db"),
        litestream_blob_url="",
    )
    return create_app(cfg)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def app_with_write_route(app):
    """Register a real state-changing route so CSRF can be proven, not assumed."""
    @app.post("/_test/write")
    def _write():  # pragma: no cover - exercised via client
        return {"ok": True}

    return app


def test_healthz_is_minimal(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.get_json()
    # Must not leak anything beyond status (rule 9).
    assert body == {"status": "ok"}
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
    assert "unpkg.com" not in resp.headers["Content-Security-Policy"]
    assert "jsdelivr.net" not in resp.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in resp.headers


def test_readyz_ok_in_dev(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_readyz_503_when_bootstrap_failed(tmp_path):
    application = create_app(_prod_cfg(tmp_path))
    (tmp_path / "precious.db").touch()
    marker = tmp_path / ".bootstrap-failed"
    marker.write_text("bootstrap_background failed\n", encoding="utf-8")
    client = application.test_client()
    live = client.get("/healthz")
    ready = client.get("/readyz")
    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.get_json() == {"status": "not_ready"}


def test_readyz_503_when_prod_db_missing(tmp_path):
    application = create_app(_prod_cfg(tmp_path))
    (tmp_path / "precious.db").unlink(missing_ok=True)
    client = application.test_client()
    live = client.get("/healthz")
    ready = client.get("/readyz")
    assert live.status_code == 200
    assert live.get_json() == {"status": "ok"}
    assert ready.status_code == 503
    assert ready.get_json() == {"status": "not_ready"}


def test_readyz_503_when_prod_heartbeats_missing(tmp_path):
    from web.data.migrate import migrate

    application = create_app(_prod_cfg(tmp_path))
    migrate(application.config["DB"])
    client = application.test_client()
    assert client.get("/healthz").status_code == 200
    ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.get_json() == {"status": "not_ready"}


def test_readyz_ok_in_prod_when_heartbeats_fresh(tmp_path):
    from web.data.migrate import migrate
    from web.data.repositories.app_settings import AppSettingsRepository

    application = create_app(_prod_cfg(tmp_path))
    migrate(application.config["DB"])
    settings = AppSettingsRepository(application.config["DB"])
    settings.beat_worker(1)
    settings.beat_scheduler()
    client = application.test_client()
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.get_json() == {"status": "ok"}


def test_readyz_503_when_prod_scheduler_heartbeat_stale(tmp_path):
    from web.data.migrate import migrate
    from web.data.repositories.app_settings import AppSettingsRepository

    application = create_app(_prod_cfg(tmp_path))
    migrate(application.config["DB"])
    settings = AppSettingsRepository(application.config["DB"])
    settings.beat_worker(1)
    settings.beat_scheduler()
    with application.config["DB"].precious() as conn:
        conn.execute(
            "UPDATE app_settings SET value=? WHERE key='scheduler_heartbeat'",
            ("2000-01-01T00:00:00+00:00",),
        )
    client = application.test_client()
    assert client.get("/readyz").status_code == 503


def test_csrf_blocks_write_without_token(app_with_write_route):
    client = app_with_write_route.test_client()
    resp = client.post("/_test/write")
    assert resp.status_code == 400  # CSRF rejected, not a 405


def test_csrf_allows_write_with_valid_token(app_with_write_route):
    from web.extensions import _SESSION_KEY

    client = app_with_write_route.test_client()
    with client.session_transaction() as sess:
        sess[_SESSION_KEY] = "known-token"
    resp = client.post("/_test/write", headers={"X-CSRF-Token": "known-token"})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


def test_csrf_rejects_mismatched_token(app_with_write_route):
    from web.extensions import _SESSION_KEY

    client = app_with_write_route.test_client()
    with client.session_transaction() as sess:
        sess[_SESSION_KEY] = "known-token"
    resp = client.post("/_test/write", headers={"X-CSRF-Token": "wrong"})
    assert resp.status_code == 400


def test_vendor_assets_are_local(client):
    feather = client.get("/static/vendor/feather.min.js")
    tab_js = client.get("/static/vendor/tabulator.min.js")
    tab_css = client.get("/static/vendor/tabulator.min.css")
    assert feather.status_code == 200
    assert tab_js.status_code == 200
    assert tab_css.status_code == 200
    assert b"Tabulator" in tab_js.data
    assert b".tabulator" in tab_css.data
    assert client.get("/static/js/main.js.map").status_code == 200


def test_source_maps_hidden_in_prod(tmp_path):
    client = create_app(_prod_cfg(tmp_path)).test_client()
    assert client.get("/static/js/main.js").status_code == 200
    assert client.get("/static/js/main.js.map").status_code == 404
