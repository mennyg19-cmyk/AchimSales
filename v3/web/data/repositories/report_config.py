"""Global report on/off (precious.db `report_config`). Missing row = enabled."""

from __future__ import annotations

from report_engine import registry
from web.data.connection import Database


class ReportConfigRepository:
    def __init__(self, db: Database):
        self.db = db

    def seed_built(self) -> None:
        keys = [s.key for s in registry.built_reports()]
        with self.db.precious() as conn:
            for key in keys:
                conn.execute(
                    "INSERT INTO report_config(report_key, enabled) VALUES (?, 1)"
                    " ON CONFLICT(report_key) DO NOTHING",
                    (key,),
                )

    def all(self) -> dict[str, bool]:
        with self.db.precious() as conn:
            rows = conn.execute("SELECT report_key, enabled FROM report_config").fetchall()
        return {r["report_key"]: bool(r["enabled"]) for r in rows}

    def is_enabled(self, report_key: str) -> bool:
        with self.db.precious() as conn:
            row = conn.execute(
                "SELECT enabled FROM report_config WHERE report_key=?", (report_key,),
            ).fetchone()
        return True if row is None else bool(row["enabled"])

    def set(self, report_key: str, enabled: bool) -> None:
        with self.db.precious() as conn:
            conn.execute(
                "INSERT INTO report_config(report_key, enabled) VALUES (?, ?)"
                " ON CONFLICT(report_key) DO UPDATE SET enabled=excluded.enabled",
                (report_key, 1 if enabled else 0),
            )
