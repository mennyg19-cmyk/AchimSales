"""Deploy hook enqueue: skip a schedule that already succeeded today."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _enqueue_mod():
    path = Path(__file__).resolve().parents[2] / "tools" / "enqueue_named_master_schedules.py"
    spec = importlib.util.spec_from_file_location("enqueue_named_master_schedules", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_is_eastern_today_true_for_now_utc():
    mod = _enqueue_mod()
    assert mod._is_eastern_today(datetime.now(timezone.utc).isoformat()) is True


def test_is_eastern_today_false_for_two_days_ago():
    mod = _enqueue_mod()
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    assert mod._is_eastern_today(old) is False
