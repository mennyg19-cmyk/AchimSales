"""Salesman master: ``rpt.usp_salesmen_master`` first, the local table as fallback.

The SP (``POST /api/reports/salesmen_master/run``) returns every salesman with
``Salesman`` (raw SalesGroup), ``SalesmanName``, ``Email`` and
``CommissionPercentage``. That is now the source for names, split-mail
addresses and the commission fallback used by the Invoiced commissions cards.

The local ``salesmen`` table still supplies the salesman number and the short
display name, fills any blank the SP leaves, and is the whole answer while the
SP has not answered yet in this process (or is not configured). A local row
switched to inactive hides that salesman everywhere: that toggle is the admin's
opt-out for a retired rep the SP still lists.

Cached per process for ``ttl_seconds``. A failed refresh keeps the last good
list and waits ``retry_cooldown_seconds`` before trying again.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

from report_engine.facts import SalesmanFact
from report_engine.lib import first_of, num, salesman_key, text

log = logging.getLogger(__name__)

_KEY_COLUMNS = ("Salesman", "SalesGroup", "SalesGroupId", "SalesGroupCode", "sales_group",
                "salesgroup", "SalesmanCode", "SalesmanKey", "SalesmanId", "Code", "Key", "Id")
_NAME_COLUMNS = ("SalesmanName", "SalesGroupName", "salesman_name", "Name", "name",
                 "FullName", "full_name", "DisplayName", "display_name", "Description")
_EMAIL_COLUMNS = ("Email", "email", "SalesmanEmail", "EmailAddress")
_COMMISSION_COLUMNS = ("CommissionPercentage", "CommissionPct", "Commission", "commission",
                       "Commission %", "commission_pct")
_ACTIVE_COLUMNS = ("IsActive", "is_active", "Active", "active")
_INACTIVE = {"0", "false", "no", "n"}


@dataclass(frozen=True)
class MasterSalesman:
    key: str              # raw SalesGroup, the value report SPs filter on
    name: str
    email: str
    commission_pct: float  # fraction (0.06 = 6%)


def _fraction(value: Any) -> float:
    """Commission as a fraction; a whole percent (6) becomes 0.06, like the invoiced SP."""
    pct = num(value)
    if pct <= 0:
        return 0.0
    return pct / 100 if pct > 1 else pct


def master_salesman(raw: dict) -> MasterSalesman | None:
    """One salesmen_master SP row; None for blank or inactive rows."""
    key = text(first_of(raw, *_KEY_COLUMNS))
    if not key:
        return None
    active = first_of(raw, *_ACTIVE_COLUMNS)
    if active is not None and text(active).lower() in _INACTIVE:
        return None
    return MasterSalesman(
        key=key,
        name=text(first_of(raw, *_NAME_COLUMNS)),
        email=text(first_of(raw, *_EMAIL_COLUMNS)),
        commission_pct=_fraction(first_of(raw, *_COMMISSION_COLUMNS)),
    )


def _local_raw_key(row) -> str:
    """The table stores a normalized key; display_name is the raw SalesGroup when
    it normalizes back to that key (e.g. REdwards), which is what the SPs want."""
    display = (row.display_name or "").strip()
    if display and " " not in display and salesman_key(display) == row.key:
        return display
    return row.key


class SalesmanDirectory:
    def __init__(self, client, repo, *, ttl_seconds: int = 3600,
                 retry_cooldown_seconds: int = 15):
        self.client = client
        self.repo = repo
        self.ttl = ttl_seconds
        self.retry_cooldown = retry_cooldown_seconds
        self._lock = threading.Lock()
        self._master: list[MasterSalesman] | None = None
        self._fetched_at = 0.0
        self._failed_at = 0.0
        self._state: dict[str, Any] = {"raw_count": 0, "columns": [], "error": None}

    # -- fetch --------------------------------------------------------------

    @property
    def configured(self) -> bool:
        return bool(getattr(self.client, "configured", False))

    def refresh(self) -> None:
        """Fetch the SP now. Never raises; a failure keeps the last good list."""
        if not self.configured:
            return
        try:
            raw_rows = self.client.run_report("salesmen_master", {}).rows
        except Exception as exc:  # noqa: BLE001 - callers fall back to the local table
            log.warning("salesmen_master SP unreachable; using the last good list "
                        "or the local salesmen table: %s", exc)
            self._failed_at = time.time()
            self._state["error"] = str(exc)
            return
        columns = sorted(raw_rows[0].keys()) if raw_rows and isinstance(raw_rows[0], dict) else []
        rows = [r for r in map(master_salesman, raw_rows) if r]
        if raw_rows and not rows:
            log.warning("salesmen_master returned %d rows but none had a known key column;"
                        " columns=%s", len(raw_rows), columns)
        with self._lock:
            self._master = rows
            self._fetched_at = time.time()
        self._state.update(raw_count=len(raw_rows), columns=columns, error=None)

    def _refresh_if_stale(self) -> None:
        now = time.time()
        with self._lock:
            fresh = self._master is not None and (now - self._fetched_at) <= self.ttl
        if fresh or (now - self._failed_at) < self.retry_cooldown:
            return
        self.refresh()

    def status(self) -> dict[str, Any]:
        with self._lock:
            master = self._master
        return {
            "master_row_count": len(master) if master is not None else 0,
            "master_raw_count": self._state["raw_count"],
            "master_columns": list(self._state["columns"]),
            "master_error": self._state["error"],
            "master_source": "sp" if master is not None else "local",
        }

    # -- merged view --------------------------------------------------------

    def _local(self) -> tuple[dict, dict[str, float]]:
        local = {s.key: s for s in self.repo.list_all()}
        commissions = {k: f.commission_pct for k, f in self.repo.all_as_facts().items()}
        return local, commissions

    def sp_rows(self) -> list[MasterSalesman] | None:
        """SP salesmen with local blanks filled; None until the SP has answered.

        Local rows marked inactive are excluded even when the SP lists them.
        Never calls the SP, so dropdown renders do not block on it.
        """
        with self._lock:
            master = list(self._master) if self._master is not None else None
        if master is None:
            return None
        local, commissions = self._local()
        out: list[MasterSalesman] = []
        seen: set[str] = set()
        for m in master:
            norm = salesman_key(m.key)
            loc = local.get(norm)
            if norm in seen or (loc is not None and not loc.is_active):
                continue
            seen.add(norm)
            out.append(MasterSalesman(
                key=m.key,
                name=m.name or (loc.display_name or loc.full_name if loc else "") or m.key,
                email=m.email or (loc.email if loc else ""),
                commission_pct=m.commission_pct or commissions.get(norm, 0.0),
            ))
        return out

    def rows(self, *, wait: bool = True) -> list[MasterSalesman]:
        """Every salesman we know: ``sp_rows()`` plus active local rows the SP does
        not list (deactivate them in Users & access to drop them). Before the SP
        has answered this is the local table alone. ``wait`` refreshes a stale
        cache first; pass ``wait=False`` from request paths that must not block.
        """
        if wait:
            self._refresh_if_stale()
        out = list(self.sp_rows() or [])
        seen = {salesman_key(m.key) for m in out}
        local, commissions = self._local()
        for norm, loc in local.items():
            if norm in seen or not loc.is_active:
                continue
            seen.add(norm)
            out.append(MasterSalesman(
                key=_local_raw_key(loc),
                name=loc.display_name or loc.full_name or norm,
                email=loc.email,
                commission_pct=commissions.get(norm, 0.0),
            ))
        return out

    def all_as_facts(self) -> dict[str, SalesmanFact]:
        """{normalized key -> SalesmanFact} for the report builders.

        Number and short display name stay local (the SP has neither); full name
        and commission come from the SP when it has them.
        """
        local_facts = self.repo.all_as_facts()
        out: dict[str, SalesmanFact] = {}
        for m in self.rows():
            norm = salesman_key(m.key)
            loc = local_facts.get(norm)
            out[norm] = SalesmanFact(
                key=norm,
                number=loc.number if loc else "",
                full_name=m.name or (loc.full_name if loc else ""),
                display_name=(loc.display_name if loc else "") or m.name or m.key,
                commission_pct=m.commission_pct,
            )
        return out

    # -- emails (split-mail, auto-grant) ------------------------------------

    def get_email(self, key: str) -> str:
        norm = salesman_key(key)
        for m in self.rows():
            if salesman_key(m.key) == norm:
                return m.email
        return ""

    def emails_by_keys(self, keys: Iterable[str]) -> dict[str, str]:
        by_norm = {salesman_key(m.key): m.email for m in self.rows()}
        return {str(k): by_norm.get(salesman_key(str(k)), "") for k in keys}

    def keys_with_email(self) -> list[str]:
        """Raw SalesGroup keys that have an address (split-by-salesman targets)."""
        return [m.key for m in self.rows() if m.email]

    def keys_for_email(self, email: str) -> list[str]:
        """Normalized keys whose address matches this login (Users & access auto-grant)."""
        want = (email or "").strip().lower()
        if not want:
            return []
        return [salesman_key(m.key) for m in self.rows() if m.email.strip().lower() == want]
