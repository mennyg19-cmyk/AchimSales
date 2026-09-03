"""Durable worker bootstrap and heartbeat state."""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timedelta, timezone

from web.data.connection import Database

_BOOTSTRAP_FINISHED = "worker_bootstrap_finished"
_WORKER_HEARTBEAT = "worker_heartbeat"
_SCHEDULER_HEARTBEAT = "scheduler_heartbeat"
_LAST_CLEANUP = "last_cleanup"
_WORKER_PROCESS_IDENTITY = "worker_process_identity"


def mark_bootstrap_finished(db: Database) -> None:
    _set(db, _BOOTSTRAP_FINISHED, _now())


def beat(db: Database) -> None:
    _set(db, _WORKER_HEARTBEAT, _now())


def beat_scheduler(db: Database) -> None:
    _set(db, _SCHEDULER_HEARTBEAT, _now())


def mark_cleanup(db: Database) -> None:
    _set(db, _LAST_CLEANUP, _now())


def write_process_identity(db: Database) -> None:
    _set(db, _WORKER_PROCESS_IDENTITY, json.dumps({
        "pid": os.getpid(),
        "started_at": _now(),
        "hostname": socket.gethostname(),
    }))


def is_ready(db: Database, *, max_age_seconds: int = 90) -> bool:
    try:
        with db.precious() as conn:
            rows = conn.execute(
                "SELECT key, value FROM app_settings WHERE key IN (?, ?, ?)",
                (_BOOTSTRAP_FINISHED, _WORKER_HEARTBEAT, _SCHEDULER_HEARTBEAT),
            ).fetchall()
    except Exception:
        return False
    values = {row["key"]: row["value"] for row in rows}
    return (
        bool(values.get(_BOOTSTRAP_FINISHED))
        and _is_fresh(values.get(_WORKER_HEARTBEAT, ""), max_age_seconds)
        and _is_fresh(values.get(_SCHEDULER_HEARTBEAT, ""), max_age_seconds)
    )


def snapshot(db: Database, *, max_age_seconds: int = 90) -> dict:
    keys = (_WORKER_HEARTBEAT, _SCHEDULER_HEARTBEAT, _LAST_CLEANUP, _WORKER_PROCESS_IDENTITY)
    try:
        with db.precious() as conn:
            rows = conn.execute(
                "SELECT key, value FROM app_settings WHERE key IN (?, ?, ?, ?)", keys
            ).fetchall()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    values = {row["key"]: row["value"] for row in rows}
    return {
        "worker_heartbeat": values.get(_WORKER_HEARTBEAT),
        "scheduler_heartbeat": values.get(_SCHEDULER_HEARTBEAT),
        "last_cleanup": values.get(_LAST_CLEANUP),
        "process_identity": _parse_json(values.get(_WORKER_PROCESS_IDENTITY, "")),
        "worker_heartbeat_fresh": _is_fresh(values.get(_WORKER_HEARTBEAT, ""), max_age_seconds),
        "scheduler_heartbeat_fresh": _is_fresh(
            values.get(_SCHEDULER_HEARTBEAT, ""), max_age_seconds
        ),
    }


def _set(db: Database, key: str, value: str) -> None:
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO app_settings(key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_json(value: str) -> dict | None:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_fresh(value: str, max_age_seconds: int) -> bool:
    timestamp = _parse(value)
    return timestamp is not None and timestamp >= _cutoff(max_age_seconds)


def _cutoff(max_age_seconds: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
