"""Salesman master: ``rpt.usp_salesmen_master`` is the only source.

The SP (``POST /api/reports/salesmen_master/run``) returns every salesman with
``Salesman`` (raw SalesGroup), ``SalesmanName``, ``Email`` and
``CommissionPercentage``. It feeds every salesman dropdown, split-mail
addresses, the Users & access email auto-grant, and the commission fallback on
the Invoiced commissions cards. There is no local salesman table any more; to
add, rename, retire or re-address a salesman, change D365.

Cached in memory for ``ttl_seconds`` and, when a database is given, written to
``cache.db`` (``salesmen_master_cache``) on every successful fetch so a worker
that boots while the SP is down still has the last good list. A failed refresh
keeps what we have and waits ``retry_cooldown_seconds`` before trying again.
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


class SalesmanDirectory:
    def __init__(self, client, db=None, *, ttl_seconds: int = 3600,
                 retry_cooldown_seconds: int = 15):
        self.client = client
        self.db = db
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
        except Exception as exc:  # noqa: BLE001 - callers keep the cached list
            log.warning("salesmen_master SP unreachable; using the last good list: %s", exc)
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
        self._write_cache(rows)

    def _refresh_if_stale(self) -> None:
        now = time.time()
        with self._lock:
            fresh = self._master is not None and (now - self._fetched_at) <= self.ttl
        if fresh or (now - self._failed_at) < self.retry_cooldown:
            return
        self.refresh()

    # -- disk cache (last good list across restarts) -------------------------

    def _write_cache(self, rows: list[MasterSalesman]) -> None:
        if self.db is None:
            return
        try:
            with self.db.cache() as conn:
                conn.execute("DELETE FROM salesmen_master_cache")
                conn.executemany(
                    "INSERT INTO salesmen_master_cache(salesman, name, email, commission_pct)"
                    " VALUES (?, ?, ?, ?)",
                    [(r.key, r.name, r.email, r.commission_pct) for r in rows],
                )
        except Exception as exc:  # noqa: BLE001 - the cache is best-effort
            log.warning("could not write salesmen_master_cache: %s", exc)

    def _read_cache(self) -> list[MasterSalesman]:
        if self.db is None:
            return []
        try:
            with self.db.cache() as conn:
                rows = conn.execute(
                    "SELECT salesman, name, email, commission_pct FROM salesmen_master_cache"
                    " ORDER BY name, salesman"
                ).fetchall()
        except Exception as exc:  # noqa: BLE001 - cache.db can vanish between boots
            log.warning("could not read salesmen_master_cache: %s", exc)
            return []
        return [MasterSalesman(key=r["salesman"], name=r["name"], email=r["email"],
                               commission_pct=float(r["commission_pct"] or 0.0))
                for r in rows]

    def status(self) -> dict[str, Any]:
        with self._lock:
            master = self._master
        if master is not None:
            source = "sp"
        elif self._read_cache():
            source = "cache"
        else:
            source = "none"
        return {
            "master_row_count": len(master) if master is not None else 0,
            "master_raw_count": self._state["raw_count"],
            "master_columns": list(self._state["columns"]),
            "master_error": self._state["error"],
            "master_source": source,
        }

    # -- reads --------------------------------------------------------------

    def rows(self, *, wait: bool = True) -> list[MasterSalesman]:
        """Every salesman: this process's SP fetch, else the last good list on
        disk. ``wait`` refreshes a stale cache first; pass ``wait=False`` from
        request paths that must not block (the lookup warm-up refreshes in the
        background)."""
        if wait:
            self._refresh_if_stale()
        with self._lock:
            master = list(self._master) if self._master is not None else None
        if master is None:
            master = self._read_cache()
        out: list[MasterSalesman] = []
        seen: set[str] = set()
        for m in master:
            norm = salesman_key(m.key)
            if norm in seen:
                continue
            seen.add(norm)
            out.append(m)
        return sorted(out, key=lambda m: ((m.name or m.key).lower(), m.key))

    def all_as_facts(self) -> dict[str, SalesmanFact]:
        """{normalized key -> SalesmanFact} for the report builders."""
        return {
            salesman_key(m.key): SalesmanFact(
                source="reporting_api", key=salesman_key(m.key),
                full_name=m.name or m.key, display_name=m.name or m.key,
                commission_pct=m.commission_pct,
            )
            for m in self.rows()
        }

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
