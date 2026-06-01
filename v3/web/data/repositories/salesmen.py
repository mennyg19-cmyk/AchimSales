"""Salesman repository (precious.db `salesmen` table).

Holds salesman master data (number, names, commission rate) that builders use
to resolve a raw SalesGroup into a display label / number / commission. Seeded
once from the live config (see web/data/seed_salesmen.py) and editable in v3
thereafter.
"""

from __future__ import annotations

from dataclasses import dataclass

from report_engine.facts import SalesmanFact
from report_engine.lib import salesman_key
from web.data.connection import Database


@dataclass(frozen=True)
class SalesmanSeed:
    """One inbound salesman record to upsert (key derived from `raw_key`)."""
    raw_key: str
    number: str
    full_name: str
    display_name: str
    email: str = ""
    commission_pct: float = 0.0


@dataclass(frozen=True)
class SalesmanRow:
    """A full salesman row for the admin grid (active and inactive)."""
    key: str
    number: str
    full_name: str
    display_name: str
    is_active: bool


class SalesmanRepository:
    def __init__(self, db: Database):
        self.db = db

    def all_as_facts(self) -> dict[str, SalesmanFact]:
        """{normalized key -> SalesmanFact} for the builders' salesman map."""
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT key, number, full_name, display_name, commission_pct"
                " FROM salesmen WHERE is_active = 1"
            ).fetchall()
        return {
            r["key"]: SalesmanFact(
                source="reporting_api", key=r["key"], number=r["number"],
                full_name=r["full_name"], display_name=r["display_name"],
                commission_pct=float(r["commission_pct"] or 0.0),
            )
            for r in rows
        }

    def count(self) -> int:
        with self.db.precious() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM salesmen").fetchone()["n"]

    def list_all(self) -> list[SalesmanRow]:
        """Every salesman (active + inactive) for the admin grid, by number."""
        with self.db.precious() as conn:
            rows = conn.execute(
                "SELECT key, number, full_name, display_name, is_active FROM salesmen"
                " ORDER BY number, display_name"
            ).fetchall()
        return [
            SalesmanRow(key=r["key"], number=r["number"], full_name=r["full_name"],
                        display_name=r["display_name"], is_active=bool(r["is_active"]))
            for r in rows
        ]

    _EDITABLE = ("number", "full_name", "display_name", "is_active")

    def update(self, key: str, **fields) -> bool:
        """Update editable fields of a salesman. Returns False if the key is unknown."""
        sets: list[str] = []
        vals: list[object] = []
        for name, value in fields.items():
            if name not in self._EDITABLE or value is None:
                continue
            sets.append(f"{name} = ?")
            vals.append((1 if value else 0) if name == "is_active" else value)
        if not sets:
            return False
        vals.append(key)
        with self.db.precious() as conn:
            cur = conn.execute(f"UPDATE salesmen SET {', '.join(sets)} WHERE key = ?", vals)
            return cur.rowcount > 0

    def upsert_many(self, seeds: list[SalesmanSeed]) -> int:
        """Insert/update salesmen keyed by normalized SalesGroup. Returns count."""
        n = 0
        with self.db.precious() as conn:
            for s in seeds:
                key = salesman_key(s.raw_key)
                if not key:
                    continue
                conn.execute(
                    "INSERT INTO salesmen(key, number, full_name, display_name,"
                    " email, commission_pct) VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET"
                    "   number=excluded.number, full_name=excluded.full_name,"
                    "   display_name=excluded.display_name, email=excluded.email,"
                    "   commission_pct=excluded.commission_pct",
                    (key, s.number, s.full_name, s.display_name, s.email, s.commission_pct),
                )
                n += 1
        return n
