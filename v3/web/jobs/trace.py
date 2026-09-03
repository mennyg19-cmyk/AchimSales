"""Thread-local live job log. The worker binds it; callers just call step().

Keeps a copy on the thread so schedule history can snapshot the same steps.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

LOG_CAP = 250
DETAIL_CAP = 2000
_local = threading.local()


def bind(job_id: str, repo: Any) -> None:
    _local.job_id = job_id
    _local.repo = repo
    _local.t0 = time.monotonic()
    _local.entries: list[dict] = []


def unbind() -> None:
    _local.job_id = None
    _local.repo = None
    _local.entries = []


def snapshot() -> list[dict]:
    return list(getattr(_local, "entries", None) or [])


def step(name: str, detail: str = "", *, ms: float | None = None) -> None:
    t0 = getattr(_local, "t0", None)
    elapsed = int((time.monotonic() - t0) * 1000) if t0 is not None else 0
    entry: dict[str, Any] = {
        "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "step": name,
        "detail": (detail or "")[:DETAIL_CAP],
        "elapsed_ms": elapsed,
    }
    if ms is not None:
        entry["ms"] = int(ms)
    job_id = getattr(_local, "job_id", None)
    log.info("job %s %s %s elapsed=%dms", job_id or "-", name, detail, elapsed)
    entries = getattr(_local, "entries", None)
    if entries is not None:
        entries.append(entry)
        if len(entries) > LOG_CAP:
            del entries[:-LOG_CAP]
    repo = getattr(_local, "repo", None)
    if repo is not None and job_id:
        repo.append_log(job_id, entry)
