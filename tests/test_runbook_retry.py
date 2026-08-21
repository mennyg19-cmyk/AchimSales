"""Whole-job retry for the Azure universal runbook."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runbooks"))

from universal_runbook import run_with_retry  # noqa: E402


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
