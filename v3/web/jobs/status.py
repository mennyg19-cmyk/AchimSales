"""Durable worker bootstrap and heartbeat state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from web.data.connection import Database

_BOOTSTRAP_FINISHED = "worker_bootstrap_finished"
_WORKER_HEARTBEAT = "worker_heartbeat"


def mark_bootstrap_finished(db: Database) -> None:
    _set(db, _BOOTSTRAP_FINISHED, _now())


def beat(db: Database) -> None:
    _set(db, _WORKER_HEARTBEAT, _now())


def is_ready(db: Database, *, max_age_seconds: int = 90) -> bool:
    try:
        with db.precious() as conn:
            rows = conn.execute(
                "SELECT key, value FROM app_settings WHERE key IN (?, ?)",
                (_BOOTSTRAP_FINISHED, _WORKER_HEARTBEAT),
            ).fetchall()
    except Exception:
        return False
    values = {row["key"]: row["value"] for row in rows}
    heartbeat = _parse(values.get(_WORKER_HEARTBEAT, ""))
    return bool(values.get(_BOOTSTRAP_FINISHED)) and heartbeat is not None and heartbeat >= _cutoff(max_age_seconds)


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


def _cutoff(max_age_seconds: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
