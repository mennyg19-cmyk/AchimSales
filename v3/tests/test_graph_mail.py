"""Graph sendMail retries 429/503 using Retry-After."""

from __future__ import annotations

import io
import urllib.error

from web.delivery.graph_mail import GraphMailer


class _Ok:
    def read(self):
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_graph_send_retries_429_then_succeeds(monkeypatch):
    calls = {"n": 0}
    mailer = GraphMailer("tid", "cid", "secret")
    monkeypatch.setattr(mailer, "_token", lambda: "tok")
    monkeypatch.setattr("web.delivery.graph_mail.time.sleep", lambda _s: None)

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                req.full_url, 429, "throttle", {"Retry-After": "0"}, io.BytesIO(b"slow"),
            )
        return _Ok()

    monkeypatch.setattr("web.delivery.graph_mail.urllib.request.urlopen", fake_urlopen)
    mailer.send(sender="from@x.com", to=["a@x.com"], subject="Hi", body_text="x")
    assert calls["n"] == 2
