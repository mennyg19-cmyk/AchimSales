"""Filter-form lookup data: the salesman + customer dropdown sources.

Behaviour parity with the v2 test app (WHAT, not HOW): the dropdowns must never
block a page render. We source the customer universe from the on-prem
``customer_master`` SP (through the existing ``ReportService`` - which already
falls back to a local mirror when the API is down), cache it in-process with a
TTL, and populate it on a background thread. While that's loading, callers get
whatever's cached now (possibly nothing) and the form polls ``status()`` to swap
in the live list when it's ready.

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
                 *, ttl_seconds: int = 3600, retry_cooldown_seconds: int = 15):
        self.service = service
        self.salesmen_repo = salesmen_repo
        self.ttl = ttl_seconds
        self.retry_cooldown = retry_cooldown_seconds
        self._lock = threading.Lock()
        self._rows: list | None = None          # cached CustomerFact list
        self._fetched_at = 0.0
        self._thread: threading.Thread | None = None
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

    def _kick(self) -> bool:
        """Start a background populate unless one is already running."""
        if not self._configured:
            return False
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            t = threading.Thread(target=self._populate, name="v3-lookups", daemon=True)
            self._thread = t
            t.start()
            return True

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
        except Exception as exc:  # noqa: BLE001 - report it, never crash the thread
            self._state.update(status="error", finished_at=time.time(),
                               elapsed_ms=int((time.monotonic() - started) * 1000),
                               error=str(exc))
        finally:
            with self._lock:
                self._thread = None

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
        (lowercased) and would be the WRONG value to send the SP. Instead we kick
        a background populate and return empty; the form polls status() and
        reloads when the real (raw) list is warm.
        """
        names = self._name_map()
        rows = self._cached_rows()
        if rows is None:
            self._kick()
            return []
        seen: set[str] = set()
        for f in rows:
            sg = (getattr(f, "sales_group", "") or "").strip()
            if sg:
                seen.add(sg)
        out = [{"key": sg, "name": names.get(salesman_key(sg)) or sg} for sg in seen]
        return sorted(out, key=lambda r: r["name"].lower())

    def customers(self, salesman: str | None = None) -> list[dict]:
        """Distinct customers (optionally narrowed to one salesman). Never blocks."""
        rows = self._cached_rows()
        if rows is None:
            self._kick()
            return []
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
        or None when the account is unknown OR the universe isn't warm yet.

        Callers that need to authorize a customer must use THIS (the customer
        master assigns the salesman), not the order lines - salesline_release can
        carry a blank SalesGroup, which would both deny valid customers and skip
        authorization on empty history."""
        acct = (account or "").strip()
        if not acct:
            return None
        rows = self._cached_rows()
        if rows is None:
            self._kick()
            return None
        for f in rows:
            if (getattr(f, "customer_account", "") or "").strip() == acct:
                return {"key": acct,
                        "name": (getattr(f, "customer_name", "") or "").strip() or acct,
                        "salesman": (getattr(f, "sales_group", "") or "").strip()}
        return None

    def status(self) -> dict[str, Any]:
        """Populate progress for the form's poll loop.

        Self-warming but bounded: a populate is (re)kicked only when we're idle
        or after a failed attempt's cooldown elapses. A successful populate that
        returned 0 rows is treated as "ready" (a real empty universe), NOT as a
        reason to retry forever.
        """
        state = dict(self._state)
        state["configured"] = self._configured
        cached = self._cached_rows()
        state["cached_row_count"] = len(cached) if cached is not None else 0
        # Mirror count isn't tracked separately in v3 yet (the persistent customer
        # mirror is deferred to the Phase D mirror/diagnostics work), so report 0.
        state["mirror_row_count"] = 0

        if state["configured"] and state["status"] not in ("loading", "ready"):
            # idle or error -> consider a (re)populate, backing off after errors.
            now = time.time()
            finished = state.get("finished_at")
            cooldown_ok = (
                state["status"] != "error"
                or not finished
                or (now - float(finished)) >= self.retry_cooldown
            )
            if cooldown_ok and self._kick():
                state["status"] = "loading"
                state["started_at"] = now
                state["finished_at"] = None
                state["error"] = None
        return state
