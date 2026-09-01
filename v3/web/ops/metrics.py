"""Process-local counters for the developer diagnostic.

Not a metrics backend. Values reset on process recycle. Safe to call from
worker threads; snapshot() is what the diagnostic JSON reads.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_graph_throttle = 0
_graph_retry = 0
_last_report: dict = {}
_last_tick: dict = {}


def note_graph_throttle(status_code: int = 429) -> None:
    global _graph_throttle, _graph_retry
    with _lock:
        _graph_retry += 1
        if status_code == 429:
            _graph_throttle += 1


def note_report_latency(report_key: str, ms: int, *, from_cache: bool) -> None:
    global _last_report
    with _lock:
        _last_report = {
            "report_key": report_key,
            "ms": ms,
            "from_cache": from_cache,
            "at_unix": int(time.time()),
        }


def note_scheduler_tick(*, due_enqueued: int) -> None:
    global _last_tick
    with _lock:
        _last_tick = {
            "enqueued": due_enqueued,
            "at_unix": int(time.time()),
        }


def snapshot() -> dict:
    with _lock:
        return {
            "graph_throttle_count": _graph_throttle,
            "graph_retry_count": _graph_retry,
            "last_report": dict(_last_report),
            "last_scheduler_tick": dict(_last_tick),
        }
