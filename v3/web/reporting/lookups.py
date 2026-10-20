"""Filter-form lookup data: the salesman + customer dropdown sources.

Behaviour parity with the v2 test app (WHAT, not HOW): the dropdowns must never
block a page render. We source the customer universe from the on-prem
``customer_master`` SP (through the existing ``ReportService`` - which already
falls back to a local mirror when the API is down), cache it in-process with a
TTL, and populate it on a background thread. While that's loading, callers get
whatever's cached now (possibly nothing) and the form polls ``status()`` to swap
in the live list when it's ready.

Salesman values are the raw ``SalesGroup`` strings the run endpoint pushes down
to the SP (so the dropdown selection round-trips correctly). The list itself is
the ``SalesmanDirectory`` (``rpt.usp_salesmen_master``, last good copy kept in
cache.db), so every salesman appears even before they own a customer. Any
customer SalesGroup the directory does not list is appended so no filter value
disappears.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from report_engine.lib import salesman_key, sales_group_value
from web.reporting.report_service import ReportService
from web.reporting.salesman_directory import SalesmanDirectory

log = logging.getLogger(__name__)


class LookupService:
    def __init__(self, service: ReportService, directory: SalesmanDirectory,
                 *, mirror_customers=None, remember_customers=None,
                 ttl_seconds: int = 3600, retry_cooldown_seconds: int = 15):
        self.service = service
        self.directory = directory
        # Called with the live CustomerFact list after a successful populate.
        # Used to copy that list into the shared mirror so other workers can
        # serve it before their own populate finishes.
        self.remember_customers = remember_customers
        # Persisted customer universe (the dashboard mirror). Each gunicorn worker
        # warms its OWN in-process live cache, so a dropdown request can land on a
        # worker that hasn't populated yet; the mirror is the shared, durable
        # source every worker can read immediately. This is how the test app feeds
        # its dropdown (WHAT, not HOW). Callable -> iterable of objects exposing
        # .customer_account / .customer_name / .sales_group; None disables it.
        self.mirror_customers = mirror_customers
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
            self.directory.refresh()  # never raises; salesman list keeps its last good copy
            rows = self.service._customer_universe()  # facts; mirror fallback inside
            with self._lock:
                self._rows = rows
                self._fetched_at = time.time()
            self._state.update(
                status="ready", finished_at=time.time(),
                elapsed_ms=int((time.monotonic() - started) * 1000),
                row_count=len(rows), error=None,
            )
            if rows and self.remember_customers:
                try:
                    self.remember_customers(rows)
                except Exception:  # noqa: BLE001 - the dropdown still has this worker's cache
                    log.warning("could not remember customer universe", exc_info=True)
        except Exception as exc:  # noqa: BLE001 - report it, never crash the thread
            self._state.update(status="error", finished_at=time.time(),
                               elapsed_ms=int((time.monotonic() - started) * 1000),
                               error=str(exc))
        finally:
            with self._lock:
                self._thread = None

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

        Prefer this worker's freshly-cached live universe; otherwise serve the
        shared persisted mirror so the dropdowns populate immediately (before
        this worker's own background populate finishes, or if the live API is
        down). A background live populate is still kicked so the cache warms.
        """
        rows = self._cached_rows()
        if rows is None:
            self._kick()
            return self._mirror_rows()
        if not rows:
            return self._mirror_rows() or rows
        return rows

    # -- public -----------------------------------------------------------

    def salesmen(self) -> list[dict]:
        """Salesmen for every dropdown on the site. Never blocks.

        Values are the raw ``SalesGroup`` strings the run endpoint pushes to the
        SP: the ``salesmen_master`` rows (this process's fetch, else the last good
        copy in cache.db; the background warm-up refreshes, never this call), plus
        any customer SalesGroup the SP does not list.
        """
        out = [{"key": m.key, "name": m.name or m.key} for m in self.directory.rows(wait=False)]
        seen = {salesman_key(r["key"]) for r in out}
        for f in self._universe():
            acct = (getattr(f, "customer_account", "") or "").strip()
            sg = sales_group_value(getattr(f, "sales_group", ""), acct)
            norm = salesman_key(sg)
            if not sg or norm in seen:
                continue
            seen.add(norm)
            out.append({"key": sg, "name": sg})
        return sorted(out, key=lambda r: r["name"].lower())

    def _salesman_filter_key(self, salesman: str | None) -> str | None:
        """Normalized salesman key for a dropdown filter, or None for all.

        The dropdown value is the raw SalesGroup. A saved view or a deep link
        can send that same salesman in a different case, or as the display
        name. An exact compare then matches nobody.
        """
        raw = (salesman or "").strip()
        if not raw:
            return None
        want = salesman_key(raw)
        want_name = raw.casefold()
        for row in self.salesmen():
            key = row.get("key") or ""
            name = (row.get("name") or "").strip().casefold()
            if salesman_key(key) == want or name == want_name:
                return salesman_key(key)
            if name.startswith(want_name + " ") or name.startswith(want_name + ","):
                return salesman_key(key)
        return want

    def customers(self, salesman: str | None = None) -> list[dict]:
        """Distinct customers (optionally narrowed to one salesman). Never blocks."""
        rows = self._universe()
        sm = self._salesman_filter_key(salesman)
        seen: dict[str, dict] = {}
        for f in rows:
            acct = (getattr(f, "customer_account", "") or "").strip()
            if not acct:
                continue
            sg = sales_group_value(getattr(f, "sales_group", ""), acct)
            if sm and salesman_key(sg) != sm:
                continue
            if acct in seen:
                continue
            name = (getattr(f, "customer_name", "") or "").strip()
            seen[acct] = {"key": acct, "name": name or acct, "salesman": sg}
        return sorted(seen.values(), key=lambda c: c["name"].lower())

    def customers_visible(self, visible_keys: set[str] | None,
                          salesman: str | None = None) -> list[dict]:
        """Report-dropdown customer list, narrowed to the caller's salesman keys.

        ``visible_keys is None`` means unrestricted (admin / developer).
        """
        rows = self.customers(salesman)
        if visible_keys is not None:
            rows = [c for c in rows if salesman_key(c.get("salesman", "")) in visible_keys]
        return rows

    def customer_dropdown(self, visible_keys: set[str] | None,
                          salesman: str | None = None) -> dict:
        """Customer picker payload.

        ``warming`` is true when this worker has neither a live cache nor the
        shared mirror, so an empty list is "still loading", not "no customers".
        The page keeps polling until a worker that has the list answers.
        """
        cached = self._cached_rows()
        mirror_count = len(self._mirror_rows())
        rows = self.customers_visible(visible_keys, salesman)
        warming = cached is None and mirror_count == 0 and not rows
        return {"customers": rows, "warming": warming}

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
                        "salesman": sales_group_value(getattr(f, "sales_group", ""), acct)}
        return None

    def customer_sales_groups(self) -> dict[str, str]:
        """{customer account -> SalesGroup} from the same universe as the dropdowns."""
        out: dict[str, str] = {}
        for f in self._universe():
            acct = (getattr(f, "customer_account", "") or "").strip()
            sg = sales_group_value(getattr(f, "sales_group", ""), acct)
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

        Self-warming but bounded: a populate is (re)kicked only when we're idle
        or after a failed attempt's cooldown elapses. A successful populate that
        returned 0 rows is treated as "ready" (a real empty universe), NOT as a
        reason to retry forever.
        """
        state = dict(self._state)
        state.update(self.directory.status())
        state["configured"] = self._configured
        cached = self._cached_rows()
        state["cached_row_count"] = len(cached) if cached is not None else 0
        state["mirror_row_count"] = len(self._mirror_rows())

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


def seed_customer_mirror(repo, facts) -> int:
    """Copy a live customer list into the shared mirror when that mirror is empty.

    Gunicorn workers do not share the in-process cache. The first worker that
    loads customer_master writes it here so the others can fill the dropdown
    before their own load finishes. A mirror the dashboard refresh already
    filled is left alone.
    """
    if not facts or repo.count():
        return 0
    from web.data.repositories.dashboard import DashboardCustomer

    records = []
    seen: set[str] = set()
    for fact in facts:
        acct = (getattr(fact, "customer_account", "") or "").strip()
        if not acct or acct in seen:
            continue
        seen.add(acct)
        records.append(DashboardCustomer(
            customer_account=acct,
            customer_name=(getattr(fact, "customer_name", "") or "").strip() or acct,
            sales_group=sales_group_value(getattr(fact, "sales_group", ""), acct),
            last_order_date=None,
            order_count=0,
            avg_gap_days=None,
            gap_stdev=None,
            overdue_threshold=None,
            days_since_last=None,
            status="new",
        ))
    if not records:
        return 0
    return repo.replace_all(records)
