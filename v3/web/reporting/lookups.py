"""Filter-form lookup data: the salesman + customer dropdown sources.

HTTP reads the persisted customer mirror (and any in-process cache). Live
``customer_master`` refresh runs in the worker process, not a Gunicorn thread.

Salesman values are the raw ``SalesGroup`` strings the run endpoint pushes down
to the SP (so the dropdown selection round-trips correctly); the display name is
enriched from the v3 salesman master when one exists.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from report_engine.lib import salesman_key
from web.data.repositories.salesmen import SalesmanRepository
from web.reporting.report_service import ReportService


class LookupService:
    def __init__(self, service: ReportService, salesmen_repo: SalesmanRepository,
                 *, mirror_customers=None, ttl_seconds: int = 3600,
                 retry_cooldown_seconds: int = 15):
        self.service = service
        self.salesmen_repo = salesmen_repo
        # Persisted customer universe (the dashboard / lookups mirror). HTTP
        # processes read this shared sqlite table; they do not start a populate
        # thread. Callable -> iterable of objects exposing
        # .customer_account / .customer_name / .sales_group; None disables it.
        self.mirror_customers = mirror_customers
        self.ttl = ttl_seconds
        self.retry_cooldown = retry_cooldown_seconds
        self._lock = threading.Lock()
        self._rows: list | None = None          # cached CustomerFact list
        self._fetched_at = 0.0
        self._state: dict[str, Any] = {
            "status": "idle", "started_at": None, "finished_at": None,
            "elapsed_ms": None, "row_count": 0, "error": None,
        }

    # -- internals --------------------------------------------------------

    @property
    def _configured(self) -> bool:
        return bool(getattr(self.service.client, "configured", False))

    def _cached_rows(self) -> list | None:
        with self._lock:
            if self._rows is not None and (time.time() - self._fetched_at) <= self.ttl:
                return self._rows
        return None

    def _populate(self) -> None:
        started = time.monotonic()
        self._state.update(status="loading", started_at=time.time(),
                           finished_at=None, elapsed_ms=None, error=None)
        try:
            rows = self.service._customer_universe()  # facts; mirror fallback inside
            with self._lock:
                self._rows = rows
                self._fetched_at = time.time()
            self._state.update(
                status="ready", finished_at=time.time(),
                elapsed_ms=int((time.monotonic() - started) * 1000),
                row_count=len(rows), error=None,
            )
        except Exception as exc:  # noqa: BLE001 - report it, never crash the caller
            self._state.update(status="error", finished_at=time.time(),
                               elapsed_ms=int((time.monotonic() - started) * 1000),
                               error=str(exc))

    def _mirror_rows(self) -> list:
        """Persisted customer universe (dashboard mirror); [] if unavailable."""
        if self.mirror_customers is None:
            return []
        try:
            return list(self.mirror_customers())
        except Exception:  # noqa: BLE001 - the mirror is a best-effort fallback
            return []

    def _universe(self) -> list:
        """Rows that drive the dropdowns.

        Prefer this process's freshly-cached live universe; otherwise serve the
        shared persisted mirror. HTTP never starts a populate thread; the worker
        process refreshes the mirror on a cron.
        """
        rows = self._cached_rows()
        if rows is None:
            return self._mirror_rows()
        if not rows:
            return self._mirror_rows() or rows
        return rows

    def _name_map(self) -> dict[str, str]:
        """normalized salesman key -> display/full name (from the v3 master)."""
        out: dict[str, str] = {}
        for key, fact in self.salesmen_repo.all_as_facts().items():
            out[key] = fact.display_name or fact.full_name or key
        return out

    # -- public -----------------------------------------------------------

    def salesmen(self) -> list[dict]:
        """Distinct salesmen for the dropdown. Never blocks.

        Values are the raw ``SalesGroup`` strings the run endpoint pushes to the
        SP, sourced from the cached customer universe and enriched with the
        salesman master's display name. We deliberately do NOT fall back to the
        master's keys while the universe loads: those keys are normalized
        (lowercased) and would be the WRONG value to send the SP. The persisted
        mirror stores the raw SalesGroup, so it's a safe source; absent both the
        live cache and the mirror we return empty and the form polls status().
        """
        names = self._name_map()
        rows = self._universe()
        seen: set[str] = set()
        for f in rows:
            sg = (getattr(f, "sales_group", "") or "").strip()
            if sg:
                seen.add(sg)
        out = [{"key": sg, "name": names.get(salesman_key(sg)) or sg} for sg in seen]
        return sorted(out, key=lambda r: r["name"].lower())

    def customers(self, salesman: str | None = None) -> list[dict]:
        """Distinct customers (optionally narrowed to one salesman). Never blocks."""
        rows = self._universe()
        sm = (salesman or "").strip() or None
        seen: dict[str, dict] = {}
        for f in rows:
            acct = (getattr(f, "customer_account", "") or "").strip()
            if not acct:
                continue
            sg = (getattr(f, "sales_group", "") or "").strip()
            if sm and sg != sm:
                continue
            if acct in seen:
                continue
            name = (getattr(f, "customer_name", "") or "").strip()
            seen[acct] = {"key": acct, "name": name or acct, "salesman": sg}
        return sorted(seen.values(), key=lambda c: c["name"].lower())

    def customer(self, account: str) -> dict | None:
        """Authoritative customer-master record for one account (key/name/salesman),
        or None when the account is unknown.

        Callers that need to authorize a customer must use THIS (the customer
        master assigns the salesman), not the order lines - salesline_release can
        carry a blank SalesGroup, which would both deny valid customers and skip
        authorization on empty history. Uses the same universe as the dropdowns
        (live cache, falling back to the persisted mirror) so authorization works
        on any worker even before this one's live populate warms - the mirror is
        sourced from customer_master, so its SalesGroup is the same authoritative
        assignment."""
        acct = (account or "").strip()
        if not acct:
            return None
        for f in self._universe():
            if (getattr(f, "customer_account", "") or "").strip() == acct:
                return {"key": acct,
                        "name": (getattr(f, "customer_name", "") or "").strip() or acct,
                        "salesman": (getattr(f, "sales_group", "") or "").strip()}
        return None

    def customer_sales_groups(self) -> dict[str, str]:
        """{customer account -> SalesGroup} from the same universe as the dropdowns."""
        out: dict[str, str] = {}
        for f in self._universe():
            acct = (getattr(f, "customer_account", "") or "").strip()
            sg = (getattr(f, "sales_group", "") or "").strip()
            if acct and sg and acct not in out:
                out[acct] = sg
        return out

    def ensure_customers(self, accounts: list[str]) -> list[str]:
        """Validate that accounts exist in the customer universe.

        Returns the list of accounts that remain unknown after a forced resync.
        If all are known, returns []. The caller decides whether to error or proceed.
        """
        if not accounts:
            return []
        unknown = [a for a in accounts if self.customer(a) is None]
        if not unknown:
            return []
        self._populate()
        return [a for a in unknown if self.customer(a) is None]

    def status(self) -> dict[str, Any]:
        """Populate progress for the form's poll loop.

        HTTP does not start a live populate. A filled mirror (or in-process
        cache) is ready; the worker process refreshes the mirror.
        """
        state = dict(self._state)
        state["configured"] = self._configured
        cached = self._cached_rows()
        mirror = self._mirror_rows()
        state["cached_row_count"] = len(cached) if cached is not None else 0
        state["mirror_row_count"] = len(mirror)
        if state["status"] not in ("loading", "ready", "error"):
            if (cached is not None and cached) or mirror:
                state["status"] = "ready"
                if not state["cached_row_count"]:
                    state["cached_row_count"] = len(mirror)
        return state
