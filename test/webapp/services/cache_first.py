"""Shared stale-while-revalidate helpers for slow API-backed reads.

The key behavior: wait briefly for a fresh payload; if it is still
running, return the most recent SQLite-cached payload and keep the fresh
work alive in a background thread.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from test.webapp.db import connect

log = logging.getLogger(__name__)

DEFAULT_WAIT_SECONDS = 5.0

_jobs_lock = threading.Lock()
_running_by_cache_key: dict[str, str] = {}
_job_comparisons: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_hash(value: Any) -> str:
    canonical = json.dumps(value or {}, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def payload_row_count(payload: dict[str, Any] | None) -> int:
    """Compare report payloads by total tab rows, matching run-log semantics."""
    if not isinstance(payload, dict):
        return 0
    total = 0
    for tab in payload.get("tabs") or []:
        if isinstance(tab, dict):
            rows = tab.get("rows")
            if isinstance(rows, list):
                total += len(rows)
    return total


def make_cache_key(kind: str, identity: str, user_scope: str, params: Any) -> str:
    params_hash = stable_hash(params)
    raw = "|".join([kind or "", identity or "", user_scope or "", params_hash])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def get_cached_payload(cache_key: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM api_payload_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["payload_json"])
    except json.JSONDecodeError:
        log.warning("api_payload_cache row had invalid JSON: %s", cache_key)
        return None
    return {
        "payload": payload,
        "refreshed_utc": row["refreshed_utc"],
        "source": json.loads(row["source_json"] or "{}"),
    }


def set_cached_payload(
    *,
    cache_key: str,
    kind: str,
    identity: str,
    user_scope: str,
    params: Any,
    payload: dict[str, Any],
) -> None:
    now = _now()
    source = payload.get("data_source") if isinstance(payload, dict) else {}
    with connect() as conn:
        existing = conn.execute(
            "SELECT created_utc FROM api_payload_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        created = existing["created_utc"] if existing else now
        conn.execute(
            """
            INSERT INTO api_payload_cache (
                cache_key, kind, identity, user_scope, params_hash,
                payload_json, source_json, created_utc, refreshed_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload_json = excluded.payload_json,
                source_json = excluded.source_json,
                refreshed_utc = excluded.refreshed_utc
            """,
            (
                cache_key,
                kind,
                identity,
                user_scope,
                stable_hash(params),
                json.dumps(payload, default=str),
                json.dumps(source or {}, default=str),
                created,
                now,
            ),
        )


def _insert_job(job_id: str, cache_key: str, kind: str, identity: str, user_scope: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO api_async_jobs (
                job_id, cache_key, kind, identity, user_scope,
                status, started_utc
            ) VALUES (?, ?, ?, ?, ?, 'running', ?)
            """,
            (job_id, cache_key, kind, identity, user_scope, _now()),
        )


def _finish_job(job_id: str, status: str, error: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE api_async_jobs
               SET status = ?, finished_utc = ?, error = ?
             WHERE job_id = ?
            """,
            (status, _now(), error, job_id),
        )


def _job_row(job_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM api_async_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    return dict(row) if row else None


def _existing_running_job(cache_key: str) -> str | None:
    with _jobs_lock:
        job_id = _running_by_cache_key.get(cache_key)
    if not job_id:
        return None
    row = _job_row(job_id)
    if row and row.get("status") == "running":
        return job_id
    with _jobs_lock:
        _running_by_cache_key.pop(cache_key, None)
    return None


def start_refresh_job(
    *,
    kind: str,
    identity: str,
    user_scope: str,
    params: Any,
    builder: Callable[[], dict[str, Any]],
) -> tuple[str, threading.Thread | None]:
    cache_key = make_cache_key(kind, identity, user_scope, params)
    existing = _existing_running_job(cache_key)
    if existing:
        return existing, None

    job_id = str(uuid.uuid4())
    _insert_job(job_id, cache_key, kind, identity, user_scope)

    def _run() -> None:
        try:
            payload = builder()
            if not isinstance(payload, dict):
                raise TypeError("cache-first builder must return a dict payload")
            set_cached_payload(
                cache_key=cache_key,
                kind=kind,
                identity=identity,
                user_scope=user_scope,
                params=params,
                payload=payload,
            )
            _finish_job(job_id, "success")
        except Exception as exc:
            log.exception("cache-first background job failed: %s", job_id)
            _finish_job(job_id, "failed", str(exc))
        finally:
            with _jobs_lock:
                if _running_by_cache_key.get(cache_key) == job_id:
                    _running_by_cache_key.pop(cache_key, None)

    with _jobs_lock:
        _running_by_cache_key[cache_key] = job_id
    thread = threading.Thread(target=_run, name=f"cache-first-{kind}-{job_id[:8]}", daemon=True)
    thread.start()
    return job_id, thread


def _remember_comparison_base(job_id: str, cached_before: dict[str, Any] | None) -> None:
    if not cached_before:
        base = {"cached_refreshed_utc": None, "cached_row_count": None}
    else:
        base = {
            "cached_refreshed_utc": cached_before.get("refreshed_utc"),
            "cached_row_count": payload_row_count(cached_before.get("payload")),
        }
    with _jobs_lock:
        _job_comparisons.setdefault(job_id, base)


def _comparison_for(job_id: str, fresh: dict[str, Any] | None) -> dict[str, Any]:
    with _jobs_lock:
        base = dict(_job_comparisons.get(job_id) or {})
    fresh_rows = payload_row_count(fresh.get("payload") if fresh else None)
    cached_rows = base.get("cached_row_count")
    out = {
        "cached_refreshed_utc": base.get("cached_refreshed_utc"),
        "cached_row_count": cached_rows,
        "fresh_refreshed_utc": fresh.get("refreshed_utc") if fresh else None,
        "fresh_row_count": fresh_rows,
        "row_delta": (fresh_rows - cached_rows) if isinstance(cached_rows, int) else None,
    }
    return out


def run_cache_first(
    *,
    kind: str,
    identity: str,
    user_scope: str,
    params: Any,
    builder: Callable[[], dict[str, Any]],
    wait_seconds: float = DEFAULT_WAIT_SECONDS,
) -> dict[str, Any]:
    """Start fresh work, wait briefly, then fall back to cached payload."""
    cache_key = make_cache_key(kind, identity, user_scope, params)
    cached_before = get_cached_payload(cache_key)
    job_id, thread = start_refresh_job(
        kind=kind,
        identity=identity,
        user_scope=user_scope,
        params=params,
        builder=builder,
    )
    _remember_comparison_base(job_id, cached_before)

    if thread is not None:
        thread.join(max(0.0, wait_seconds))

    row = _job_row(job_id) or {}
    if row.get("status") == "success":
        cached_after = get_cached_payload(cache_key)
        if cached_after:
            return {
                "state": "fresh",
                "payload": cached_after["payload"],
                "job_id": job_id,
                "cache_key": cache_key,
                "refreshed_utc": cached_after["refreshed_utc"],
                "total_rows": payload_row_count(cached_after["payload"]),
                **_comparison_for(job_id, cached_after),
            }

    if row.get("status") == "failed" and not cached_before:
        return {
            "state": "failed",
            "job_id": job_id,
            "cache_key": cache_key,
            "error": row.get("error") or "Refresh failed",
        }

    if cached_before:
        return {
            "state": "cached_refreshing" if row.get("status") == "running" else "cached_failed_refresh",
            "payload": cached_before["payload"],
            "job_id": job_id,
            "cache_key": cache_key,
            "refreshed_utc": cached_before["refreshed_utc"],
            "total_rows": payload_row_count(cached_before["payload"]),
            "cached_refreshed_utc": cached_before["refreshed_utc"],
            "cached_row_count": payload_row_count(cached_before["payload"]),
            "error": row.get("error"),
        }

    return {
        "state": "refreshing",
        "payload": None,
        "job_id": job_id,
        "cache_key": cache_key,
    }


def get_job_status(job_id: str) -> dict[str, Any]:
    row = _job_row(job_id)
    if not row:
        return {"found": False, "status": "missing"}
    cached = get_cached_payload(row["cache_key"]) if row.get("status") == "success" else None
    out = {
        "found": True,
        "job_id": row["job_id"],
        "cache_key": row["cache_key"],
        "kind": row["kind"],
        "identity": row["identity"],
        "status": row["status"],
        "started_utc": row["started_utc"],
        "finished_utc": row["finished_utc"],
        "error": row["error"],
    }
    if cached:
        out["payload"] = cached["payload"]
        out["refreshed_utc"] = cached["refreshed_utc"]
        out.update(_comparison_for(job_id, cached))
    return out


def cached_payload_for(
    *,
    kind: str,
    identity: str,
    user_scope: str,
    params: Any,
) -> dict[str, Any] | None:
    return get_cached_payload(make_cache_key(kind, identity, user_scope, params))
