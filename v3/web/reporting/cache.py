"""THE one report payload cache + the single source of truth for cache keys.

Cache-scope safety (REVIEW-LOG section 2): the key is derived from
(report_key, identity, scope_token, builder_version, source, params). Because the
principal's scope_token is part of the key, two users with different scope can
NEVER read each other's cached payload - different scope => different key. This
function is the ONLY place a report cache key is built.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

log = logging.getLogger(__name__)

from web.data.connection import Database

# Reserved scope tokens. "" is never a valid scope (would silently widen access).
SCOPE_ALL = "ALL"     # privileged: unrestricted
SCOPE_NONE = "NONE"   # known user with no salesman keys: sees nothing


def canonical_scope_token(visible_salesman_keys: Iterable[str] | None) -> str:
    """Canonical, order-stable scope token (part of the single source of truth).

    None (privileged/unrestricted) -> SCOPE_ALL; empty -> SCOPE_NONE; otherwise the
    sorted, comma-joined keys so {"b","a"} and {"a","b"} always hash identically.
    This is the ONLY blessed way to turn an authorization scope into a cache token.
    """
    if visible_salesman_keys is None:
        return SCOPE_ALL
    keys = sorted({(k or "").strip().lower() for k in visible_salesman_keys if (k or "").strip()})
    return ",".join(keys) if keys else SCOPE_NONE


def _stable_hash(value: Any) -> str:
    canonical = json.dumps(value or {}, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def _source_token(report_key: str, source: str | None) -> str:
    if source is not None:
        return (source or "").strip().lower()
    try:
        from web.beta_sources import get_source
        return (get_source(report_key) or "").strip().lower()
    except Exception:  # noqa: BLE001 - key still works without an app context
        return ""


def _json_safe(value: Any) -> Any:
    """Replace NaN/Inf so cache JSON stays standard (allow_nan=False)."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    try:
        if value != value:  # NaN, including numpy
            return None
    except Exception:  # noqa: BLE001
        pass
    return value


def build_cache_key(*, report_key: str, identity: str, scope_token: str,
                    builder_version: int, params: dict[str, Any],
                    source: str | None = None) -> str:
    """Single source of truth for report cache keys. Scope-aware by construction.

    `scope_token` must come from canonical_scope_token(); an empty token is
    rejected so a caller can never accidentally produce an unscoped key.
    SQL vs OData is part of the key so flipping a report source cannot reuse
    the other origin's payload.
    """
    if not scope_token:
        raise ValueError("scope_token is required (use canonical_scope_token())")
    raw = "|".join([
        report_key or "",
        identity or "",
        scope_token,
        str(builder_version),
        _source_token(report_key, source),
        _stable_hash(params),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


@dataclass
class CachedPayload:
    payload: dict
    built_at: str

    def age_seconds(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        try:
            built = datetime.fromisoformat(self.built_at)
        except ValueError:
            return float("inf")
        if built.tzinfo is None:
            built = built.replace(tzinfo=timezone.utc)
        return (now - built).total_seconds()


class ReportCache:
    def __init__(self, db: Database):
        self.db = db

    def _self_heal(self, exc: Exception) -> bool:
        """cache.db is disposable: the file can be deleted (or land on a fresh
        instance) while the app is running, leaving a schema-less DB. If a cache
        operation hits a missing table, re-apply the cache migrations and tell
        the caller to retry once instead of failing the whole report run."""
        if "no such table" not in str(exc):
            return False
        from web.data.migrate import migrate_cache_only

        log.warning("report cache schema missing (%s); re-creating it", exc)
        migrate_cache_only(self.db)
        return True

    def get(self, cache_key: str) -> CachedPayload | None:
        try:
            row = self._select(cache_key)
        except sqlite3.OperationalError as exc:
            if not self._self_heal(exc):
                raise
            row = self._select(cache_key)
        if not row:
            return None
        try:
            return CachedPayload(json.loads(row["payload_json"]), row["built_at"])
        except json.JSONDecodeError:
            # Quarantine the corrupt row so we don't rebuild on every read forever.
            log.warning("report_payload_cache: corrupt JSON for %s; deleting row", cache_key)
            with self.db.cache() as conn:
                conn.execute("DELETE FROM report_payload_cache WHERE cache_key = ?", (cache_key,))
            return None

    def _select(self, cache_key: str):
        with self.db.cache() as conn:
            return conn.execute(
                "SELECT payload_json, built_at FROM report_payload_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()

    def exists(self, cache_key: str) -> bool:
        """Cheap presence check that does NOT deserialize the (possibly large)
        payload - used to validate an export request before enqueuing the job."""
        try:
            with self.db.cache() as conn:
                row = conn.execute(
                    "SELECT 1 FROM report_payload_cache WHERE cache_key = ? LIMIT 1", (cache_key,)
                ).fetchone()
        except sqlite3.OperationalError as exc:
            if not self._self_heal(exc):
                raise
            return False  # schema was just re-created, so the row can't exist
        return row is not None

    def put(self, cache_key: str, report_key: str, payload: dict) -> None:
        try:
            self._insert(cache_key, report_key, payload)
        except sqlite3.OperationalError as exc:
            if not self._self_heal(exc):
                raise
            self._insert(cache_key, report_key, payload)

    def _insert(self, cache_key: str, report_key: str, payload: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        blob = json.dumps(_json_safe(payload), default=str, allow_nan=False)
        with self.db.cache() as conn:
            conn.execute(
                "INSERT INTO report_payload_cache(cache_key, report_key, payload_json, built_at)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(cache_key) DO UPDATE SET"
                "   payload_json=excluded.payload_json, built_at=excluded.built_at",
                (cache_key, report_key, blob, now),
            )

    def prune(self, older_than_seconds: float) -> int:
        """Delete cache rows older than the cutoff (for a scheduled reaper). Returns count."""
        cutoff = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() - older_than_seconds, tz=timezone.utc
        ).isoformat()
        with self.db.cache() as conn:
            cur = conn.execute("DELETE FROM report_payload_cache WHERE built_at < ?", (cutoff,))
            return cur.rowcount
