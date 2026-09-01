"""WSGI path routing: v3 at /, old /beta bookmarks redirect."""

from __future__ import annotations

from werkzeug.test import Client
from werkzeug.wrappers import Response

from wsgi_dispatch import PrefixRedirectMiddleware


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
    return Client(PrefixRedirectMiddleware(_named("home"), "/beta"), Response)


def test_root_is_home():
    resp = _client().get("/")
    assert resp.status_code == 200
    assert resp.get_data(as_text=True).startswith("home|")


def test_login_hits_home_app():
    resp = _client().get("/login?next=/", follow_redirects=False)
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert text.startswith("home|")
    assert "pi=/login" in text


def test_auth_callback_hits_home():
    resp = _client().get("/auth/callback")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert text.startswith("home|")
    assert "pi=/auth/callback" in text


def test_login_start_hits_home():
    resp = _client().get("/login/start?next=/", follow_redirects=False)
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert text.startswith("home|")
    assert "pi=/login/start" in text


def test_beta_prefix_redirects():
    resp = _client().get("/beta/reports?x=1", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/reports?x=1"
    resp2 = _client().get("/beta", follow_redirects=False)
    assert resp2.status_code == 302
    assert resp2.headers["Location"] == "/"
