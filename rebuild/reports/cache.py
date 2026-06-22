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
# ResultCache.read() -- load a saved result, or None

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
        payload = json.dumps(snapshot, default=str)
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
            data = json.loads(row["payload"])
            data["_cached_at"] = row["created_at"]
            return data
