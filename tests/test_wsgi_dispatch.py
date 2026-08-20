"""WSGI path routing: Beta at /, Live at /legacy, /beta redirects, Entra at /auth."""

from __future__ import annotations

from werkzeug.test import Client
from werkzeug.wrappers import Response

from wsgi_dispatch import mount_beta_as_home


def _named(name: str):
    def app(environ, start_response):
        body = (
            f"{name}|sn={environ.get('SCRIPT_NAME', '')}|pi={environ.get('PATH_INFO', '')}"
        ).encode()
        start_response(
            "200 OK",
            [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))],
        )
        return [body]

    return app


def _client():
    return Client(
        mount_beta_as_home(
            _named("beta"),
            _named("live"),
            {"/test": _named("test")},
        ),
        Response,
    )


def test_root_is_beta():
    resp = _client().get("/")
    assert resp.status_code == 200
    assert resp.get_data(as_text=True).startswith("beta|")
    assert "|pi=/" in resp.get_data(as_text=True) or "|pi=" in resp.get_data(as_text=True)


def test_legacy_is_live_with_script_name():
    resp = _client().get("/legacy/reports")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert text.startswith("live|")
    assert "sn=/legacy" in text
    assert "pi=/reports" in text


def test_legacy_bare_redirects_to_slash():
    resp = _client().get("/legacy", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/legacy/"


def test_beta_prefix_redirects():
    resp = _client().get("/beta/reports?x=1", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/reports?x=1"
    resp2 = _client().get("/beta", follow_redirects=False)
    assert resp2.status_code == 302
    assert resp2.headers["Location"] == "/"


def test_auth_callback_hits_live_at_root():
    resp = _client().get("/auth/callback")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert text.startswith("live|")
    assert "sn=" in text
    assert "pi=/auth/callback" in text
    # Must not be under /legacy — Entra URI is /auth/callback.
    assert "sn=/legacy" not in text


def test_login_redirects_to_legacy_login():
    resp = _client().get("/login?next=/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["Location"] == "/legacy/login?next=/"


def test_test_mount_unchanged():
    resp = _client().get("/test/healthz")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert text.startswith("test|")
    assert "sn=/test" in text
    assert "pi=/healthz" in text
