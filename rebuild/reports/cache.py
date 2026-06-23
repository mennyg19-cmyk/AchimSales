"""Stores and reads finished report results in the throwaway cache database."""

# === What's in this file ===
# A finished report (all its tabs) is saved here so re-opening it is instant and
# so the worker can hand the result to the web side. The cache key folds in who
# asked and their scope, so one person's results can never be served to someone
# who shouldn't see them. cache.db is disposable -- losing it just means reports
# get re-run.
#
# build_cache_key() -- a stable id from report + identity + scope + SP params
# ResultCache.store() -- save (or overwrite) one report's result
# ResultCache.read() -- load a saved result, or None (no ownership check)
# ResultCache.read_for_identity() -- load ONLY if this person + scope owns it
#   (the cache key already folds in identity, but this re-checks the stored
#   identity/scope so a derived or guessed key can never leak another's rows)

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from ..data.connection import Database, utc_now_iso


def build_cache_key(report_key: str, identity_email: Optional[str], scope_token: Optional[str], sp_params: dict) -> str:
    basis = json.dumps(
        {
            "report": report_key,
            "identity": (identity_email or "").strip().lower(),
            "scope": scope_token or "",
            "params": sp_params,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


class ResultCache:
    def __init__(self, db: Database) -> None:
        self._db = db

    def store(self, cache_key: str, report_key: str, snapshot: dict[str, Any]) -> None:
        # allow_nan=False so a stray NaN/Infinity can never be written as invalid
        # JSON that later breaks the reader or the browser parse.
        payload = json.dumps(snapshot, default=str, allow_nan=False)
        with self._db.cache() as conn:
            conn.execute(
                "INSERT INTO report_snapshots (cache_key, report_key, created_at, payload) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(cache_key) DO UPDATE SET report_key=excluded.report_key, "
                "created_at=excluded.created_at, payload=excluded.payload",
                (cache_key, report_key, utc_now_iso(), payload),
            )

    def read(self, cache_key: str) -> Optional[dict[str, Any]]:
        with self._db.cache() as conn:
            row = conn.fetchone(
                "SELECT payload, created_at FROM report_snapshots WHERE cache_key = ?", (cache_key,)
            )
            if not row:
                return None
            snapshot = json.loads(row["payload"])
            snapshot["_cached_at"] = row["created_at"]
            return snapshot

    def read_for_identity(self, cache_key: str, identity_email: Optional[str], scope_token: Optional[str]) -> Optional[dict[str, Any]]:
        snapshot = self.read(cache_key)
        if snapshot is None:
            return None
        owner = (snapshot.get("identity") or "").strip().lower()
        if owner != (identity_email or "").strip().lower():
            return None
        if (snapshot.get("scope") or "") != (scope_token or ""):
            return None
        return snapshot
