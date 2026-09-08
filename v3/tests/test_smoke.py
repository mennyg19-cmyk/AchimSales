"""Smoke: app boots in dev, health is minimal, CSRF guards writes."""

import pytest

from web import create_app
from web.config import Config


@pytest.fixture
def app(tmp_path):
    cfg = Config(
        app_env="dev",
        auth_mode="dev",
        flask_secret="test-secret",
        tenant_id="",
        client_id="",
        client_secret="",
        reporting_api_base_url="",
        reporting_api_key="",
        precious_db_path=tmp_path / "precious.db",
        cache_db_path=tmp_path / "cache.db",
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


def test_factory_returns_without_starting_background_services(app):
    assert app.config["JOB_WORKER"].running is False
    assert "SCHEDULER" not in app.config


def test_readyz_requires_bootstrap_and_fresh_worker_heartbeat(app, client):
    from web.data.migrate import migrate
    from web.jobs.status import beat, beat_scheduler, mark_bootstrap_finished

    assert client.get("/readyz").status_code == 503
    migrate(app.config["DB"])
    mark_bootstrap_finished(app.config["DB"])
    assert client.get("/readyz").status_code == 503
    beat(app.config["DB"])
    assert client.get("/readyz").status_code == 503
    beat_scheduler(app.config["DB"])
    assert client.get("/readyz").status_code == 200
    assert client.get("/readyz").get_json() == {"status": "ready"}


def test_readyz_rejects_missing_or_stale_scheduler_heartbeat(app, client):
    from web.data.migrate import migrate
    from web.jobs.status import beat, beat_scheduler, mark_bootstrap_finished

    migrate(app.config["DB"])
    mark_bootstrap_finished(app.config["DB"])
    beat(app.config["DB"])
    assert client.get("/readyz").status_code == 503
    beat_scheduler(app.config["DB"])
    with app.config["DB"].precious() as conn:
        conn.execute(
            "UPDATE app_settings SET value=datetime('now', '-2 minutes')"
            " WHERE key='scheduler_heartbeat'"
        )
    assert client.get("/readyz").status_code == 503
    assert client.get("/readyz").get_json() == {"status": "starting"}


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
