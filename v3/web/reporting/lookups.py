"""Filter-form lookup data: the salesman + customer dropdown sources.

Behaviour parity with the v2 test app (WHAT, not HOW): the dropdowns must never
block a page render. We source the customer universe from the on-prem
``customer_master`` SP (through the existing ``ReportService`` - which already
falls back to a local mirror when the API is down), cache it in-process with a
TTL, and populate it on a background thread. While that's loading, callers get
whatever's cached now (possibly nothing) and the form polls ``status()`` to swap
in the live list when it's ready.

Salesman values are the raw ``SalesGroup`` strings the run endpoint pushes down
to the SP (so the dropdown selection round-trips correctly). The list itself
comes from the ``salesmen_master`` SP (``rpt.usp_salesmen_master``), which has
every salesman even before they own a customer. If that SP is unreachable we
fall back to the distinct SalesGroups on the customer universe, and any customer
SalesGroup the master does not list is appended so no filter value disappears.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from report_engine.lib import first_of, salesman_key, text
from web.data.repositories.salesmen import SalesmanRepository
from web.reporting.report_service import ReportService

log = logging.getLogger(__name__)

_INACTIVE = {"0", "false", "no", "n"}


_KEY_COLUMNS = ("SalesGroup", "SalesGroupId", "SalesGroupCode", "sales_group", "salesgroup",
                "SalesmanCode", "SalesmanKey", "SalesmanId", "Salesman", "Code", "Key", "Id")
_NAME_COLUMNS = ("SalesmanName", "SalesGroupName", "salesman_name", "Name", "name",
                 "FullName", "full_name", "DisplayName", "display_name", "Description")
_ACTIVE_COLUMNS = ("IsActive", "is_active", "Active", "active")


def master_salesman(raw: dict) -> dict | None:
    """One salesmen_master SP row -> {key, name}; None for blank or inactive rows."""
    key = text(first_of(raw, *_KEY_COLUMNS))
    if not key:
        return None
    active = first_of(raw, *_ACTIVE_COLUMNS)
    if active is not None and text(active).lower() in _INACTIVE:
        return None
    return {"key": key, "name": text(first_of(raw, *_NAME_COLUMNS))}


class LookupService:
    def __init__(self, service: ReportService, salesmen_repo: SalesmanRepository,
                 *, mirror_customers=None, ttl_seconds: int = 3600,
                 retry_cooldown_seconds: int = 15):
        self.service = service
        self.salesmen_repo = salesmen_repo
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
        self._master: list[dict] | None = None  # cached salesmen_master {key, name}
        self._thread: threading.Thread | None = None
        self._state: dict[str, Any] = {
            "status": "idle", "started_at": None, "finished_at": None,
            "elapsed_ms": None, "row_count": 0, "error": None,
            # salesmen_master diagnostics: raw = rows the SP returned, row_count =
            # rows we kept, columns = the SP's field names (so a zero count can be
            # traced to a failed call vs. column names the adapter does not know).
            "master_row_count": 0, "master_raw_count": 0, "master_columns": [],
            "master_error": None,
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
            self._populate_master()
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

    def _populate_master(self) -> None:
        """Refresh the salesmen_master list; keep the last good one on failure."""
        try:
            raw_rows = self.service.salesmen_master()
        except Exception as exc:  # noqa: BLE001 - customers still populate without it
            log.warning("salesmen_master SP unreachable; salesman dropdown falls back "
                        "to customer SalesGroups: %s", exc)
            self._state["master_error"] = str(exc)
            return
        columns = sorted(raw_rows[0].keys()) if raw_rows and isinstance(raw_rows[0], dict) else []
        rows = [r for r in map(master_salesman, raw_rows) if r]
        if raw_rows and not rows:
            log.warning("salesmen_master returned %d rows but none had a known key column;"
                        " columns=%s", len(raw_rows), columns)
        with self._lock:
            self._master = rows
        self._state.update(master_row_count=len(rows), master_raw_count=len(raw_rows),
                           master_columns=columns, master_error=None)

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

    def _name_map(self) -> dict[str, str]:
        """normalized salesman key -> display/full name (from the v3 master)."""
        out: dict[str, str] = {}
        for key, fact in self.salesmen_repo.all_as_facts().items():
            out[key] = fact.display_name or fact.full_name or key
        return out

    # -- public -----------------------------------------------------------

    def salesmen(self) -> list[dict]:
        """Salesmen for every dropdown on the site. Never blocks.

        Values are the raw ``SalesGroup`` strings the run endpoint pushes to the
        SP. The list is the ``salesmen_master`` SP when this worker has fetched
        it (so a new salesman with no customers still appears), plus any customer
        SalesGroup the master does not list. Before the master is fetched, or if
        that SP is down, it is the distinct SalesGroups on the customer universe.
        Names: the SP's name, else the v3 salesmen table's display name, else the
        raw key. We never fall back to the v3 table's keys: those are normalized
        (lowercased) and would be the WRONG value to send the SP.
        """
        names = self._name_map()
        with self._lock:
            master = list(self._master or [])
        out: list[dict] = []
        seen: set[str] = set()
        for row in master:
            norm = salesman_key(row["key"])
            if norm in seen:
                continue
            seen.add(norm)
            out.append({"key": row["key"], "name": row["name"] or names.get(norm) or row["key"]})
        for f in self._universe():
            sg = (getattr(f, "sales_group", "") or "").strip()
            norm = salesman_key(sg)
            if not sg or norm in seen:
                continue
            seen.add(norm)
            out.append({"key": sg, "name": names.get(norm) or sg})
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

    def customers_visible(self, visible_keys: set[str] | None,
                          salesman: str | None = None) -> list[dict]:
        """Report-dropdown customer list, narrowed to the caller's salesman keys.

        ``visible_keys is None`` means unrestricted (admin / developer).
        """
        rows = self.customers(salesman)
        if visible_keys is not None:
            rows = [c for c in rows if salesman_key(c.get("salesman", "")) in visible_keys]
        return rows

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

        Self-warming but bounded: a populate is (re)kicked only when we're idle
        or after a failed attempt's cooldown elapses. A successful populate that
        returned 0 rows is treated as "ready" (a real empty universe), NOT as a
        reason to retry forever.
        """
        state = dict(self._state)
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
