"""Smoke: app boots in dev, health is minimal, CSRF guards writes."""

from pathlib import Path

import pytest

from web import create_app
from web.config import Config


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
        new_app_marker=True,
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
