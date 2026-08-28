"""Whole-job retry for the Azure universal runbook."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runbooks"))

from universal_runbook import (  # noqa: E402
    _compose_status_alerts,
    _send_alert,
    run_with_retry,
)


def _alert(subject, body, html=False):
    return {
        "subject": subject,
        "body": body,
        "tenant_id": "t",
        "client_id": "c",
        "client_secret": "s",
        "from_addr": "from@x.com",
        "recipients": ["ops@x.com"],
        "content_type": "HTML" if html else "Text",
    }


def _alert_kwargs():
    return dict(
        tenant_id="t", client_id="c", client_secret="s",
        from_addr="from@x.com", recipients=["ops@x.com"],
    )


def test_run_with_retry_returns_on_first_success():
    calls = []

    def ok():
        calls.append(1)
        return 0

    slept = []
    assert run_with_retry(ok, attempts=2, wait_s=30, sleeper=slept.append) == 0
    assert calls == [1]
    assert slept == []


def test_run_with_retry_retries_nonzero_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        return 1 if len(calls) == 1 else 0

    slept = []
    assert run_with_retry(flaky, attempts=2, wait_s=5, sleeper=slept.append) == 0
    assert calls == [1, 1]
    assert slept == [5]


def test_run_with_retry_reraises_after_last_exception():
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("blip")

    slept = []
    try:
        run_with_retry(boom, attempts=2, wait_s=5, sleeper=slept.append)
        raise AssertionError("should have raised")
    except RuntimeError as exc:
        assert str(exc) == "blip"
    assert calls == [1, 1]
    assert slept == [5]


def test_compose_first_success_keeps_heartbeat():
    hb = _alert("Runbook Heartbeat: ordered", "<p>ok</p>", html=True)
    out = _compose_status_alerts([
        {"n": 1, "ok": True, "code": 0, "alerts": [hb], "error": None},
    ])
    assert out == [hb]


def test_compose_fail_then_success_is_one_retry_mail():
    fail = _alert("FAILURE: ordered", "Graph dropped")
    hb_fail = _alert("FAILURE: ordered", "<p>failed</p>", html=True)
    hb_ok = _alert("Runbook Heartbeat: ordered", "<p>ok</p>", html=True)
    out = _compose_status_alerts([
        {"n": 1, "ok": False, "code": 1, "alerts": [fail, hb_fail], "error": None},
        {"n": 2, "ok": True, "code": 0, "alerts": [hb_ok], "error": None},
    ])
    assert len(out) == 1
    assert out[0]["subject"] == (
        "Runbook Heartbeat: ordered (failed, then retried and succeeded)"
    )
    assert "Graph dropped" in out[0]["body"]
    assert "only status email" in out[0]["body"]
    assert "<p>ok</p>" in out[0]["body"]


def test_compose_catchup_fail_then_success_heartbeat_is_one_mail():
    catch = _alert("FAILURE: ordered catch-up", "catch-up boom")
    hb = _alert("Runbook Heartbeat: ordered", "<p>ok</p>", html=True)
    out = _compose_status_alerts([
        {"n": 1, "ok": True, "code": 0, "alerts": [catch, hb], "error": None},
    ])
    assert len(out) == 1
    assert "later step succeeded" in out[0]["subject"]
    assert "catch-up boom" in out[0]["body"]
    assert "<p>ok</p>" in out[0]["body"]


def test_compose_final_failure_after_retry_is_one_mail():
    a1 = _alert("FAILURE: ordered (daily)", "daily boom")
    a2 = _alert("FAILURE: ordered", "<p>failed</p>", html=True)
    b1 = _alert("FAILURE: ordered (daily)", "daily boom again")
    b2 = _alert("FAILURE: ordered", "<p>failed again</p>", html=True)
    out = _compose_status_alerts([
        {"n": 1, "ok": False, "code": 1, "alerts": [a1, a2], "error": None},
        {"n": 2, "ok": False, "code": 1, "alerts": [b1, b2], "error": None},
    ])
    assert len(out) == 1
    assert out[0]["subject"] == "FAILURE: ordered (failed after retry)"
    assert "daily boom" in out[0]["body"]


def test_retry_success_sends_one_combined_alert(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "universal_runbook._deliver_alert",
        lambda **kw: sent.append(kw),
    )
    n = {"i": 0}

    def flaky():
        n["i"] += 1
        if n["i"] == 1:
            _send_alert("FAILURE: ordered", "Graph dropped", **_alert_kwargs())
            _send_alert(
                "FAILURE: ordered", "<p>fail hb</p>",
                **_alert_kwargs(), content_type="HTML",
            )
            return 1
        _send_alert(
            "Runbook Heartbeat: ordered", "<p>ok hb</p>",
            **_alert_kwargs(), content_type="HTML",
        )
        return 0

    assert run_with_retry(flaky, attempts=2, wait_s=0, sleeper=lambda _: None) == 0
    assert len(sent) == 1
    assert "retried and succeeded" in sent[0]["subject"]
    assert "Graph dropped" in sent[0]["body"]
    assert "ok hb" in sent[0]["body"]
