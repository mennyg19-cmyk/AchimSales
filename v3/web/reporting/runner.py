"""Generic report runner: cache-key -> cache check -> build -> store.

Decoupled from the report rules: the caller passes a `builder` callable that
returns the tab payload (the 6 real builders are gated on human sign-off). The
runner owns only orchestration + the ONE cache + freshness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from web.reporting.cache import ReportCache, build_cache_key, canonical_scope_token

# A builder takes (params, visible_salesman_keys) and returns {tabs: [...]}.
# visible_salesman_keys is None for unrestricted (privileged) users.
Builder = Callable[[dict[str, Any], set[str] | None], dict]


@dataclass
class RunOutcome:
    payload: dict
    cache_key: str
    from_cache: bool


class ReportRunner:
    def __init__(self, cache: ReportCache):
        self.cache = cache

    def run(self, *, report_key: str, identity: str,
            visible_salesman_keys: Iterable[str] | None,
            builder_version: int, params: dict[str, Any], builder: Builder,
            fresh_within_seconds: float | None = 300.0,
            force_refresh: bool = False) -> RunOutcome:
        # Scope token is canonicalized HERE from the authorization result, so a
        # caller can never pass a raw/stale/unordered token (cache-scope safety).
        scope_token = canonical_scope_token(visible_salesman_keys)
        cache_key = build_cache_key(
            report_key=report_key, identity=identity, scope_token=scope_token,
            builder_version=builder_version, params=params,
        )
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached and (fresh_within_seconds is None or cached.age_seconds() <= fresh_within_seconds):
                return RunOutcome(cached.payload, cache_key, from_cache=True)

        payload = builder(params, visible_salesman_keys)
        if not isinstance(payload, dict):
            raise TypeError("report builder must return a dict payload")
        self.cache.put(cache_key, report_key, payload)
        return RunOutcome(payload, cache_key, from_cache=False)
