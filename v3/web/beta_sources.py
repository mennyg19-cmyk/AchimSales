"""Beta report data-source map (shared with Live Settings).

Stored in the live app SQLite DB so phase-two Azure schedules can read the same
map later. Values are 'sql' or 'odata' per report key.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

log = logging.getLogger(__name__)

Source = Literal["sql", "odata"]

# Signed-off SQL reports. customer_aging stays odata until that report is built.
_DEFAULT_SQL = frozenset({
    "ordered",
    "invoiced",
    "salesman",
    "number_4",
    "customer_activity",
    "customer_last_order",
    "item_averages",
})

_ALL_KEYS = (
    "ordered",
    "invoiced",
    "salesman",
    "number_4",
    "customer_activity",
    "customer_last_order",
    "item_averages",
    "customer_aging",
)


def default_sources() -> dict[str, Source]:
    return {
        key: ("sql" if key in _DEFAULT_SQL else "odata")
        for key in _ALL_KEYS
    }


def _table_ready(conn) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='beta_report_sources'"
    ).fetchone()
    return row is not None


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS beta_report_sources (
               report_key TEXT PRIMARY KEY,
               source TEXT NOT NULL CHECK(source IN ('sql', 'odata')),
               updated_at TEXT NOT NULL DEFAULT (datetime('now'))
           )"""
    )
    for key, source in default_sources().items():
        conn.execute(
            "INSERT OR IGNORE INTO beta_report_sources (report_key, source) VALUES (?, ?)",
            (key, source),
        )
    conn.execute(
        """UPDATE beta_report_sources
           SET source = 'sql', updated_at = datetime('now')
           WHERE report_key IN ({})""".format(
            ", ".join("?" for _ in _DEFAULT_SQL)
        ),
        tuple(_DEFAULT_SQL),
    )
    conn.commit()


def get_sources() -> dict[str, Source]:
    """Read the map from the live DB. Falls back to defaults if unavailable."""
    out = default_sources()
    try:
        from webapp.db import get_db

        conn = get_db()
        try:
            ensure_schema(conn)
            rows = conn.execute("SELECT report_key, source FROM beta_report_sources").fetchall()
            for row in rows:
                src = (row["source"] or "").strip().lower()
                if src in ("sql", "odata"):
                    out[str(row["report_key"])] = src  # type: ignore[assignment]
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - beta must still boot if live DB is locked
        log.exception("beta sources: could not read live DB; using defaults")
    return out


def get_source(report_key: str) -> Source:
    """SQL/OData toggle for hybrid reports. Unknown keys are SQL-only."""
    if report_key not in _ALL_KEYS:
        return "sql"
    return get_sources().get(report_key, "odata")


def set_source(report_key: str, source: Source) -> None:
    if source not in ("sql", "odata"):
        raise ValueError(f"source must be sql or odata, got {source!r}")
    if report_key not in _ALL_KEYS:
        raise ValueError(f"unknown report_key {report_key!r}")
    from webapp.db import get_db

    conn = get_db()
    try:
        ensure_schema(conn)
        conn.execute(
            """INSERT INTO beta_report_sources (report_key, source, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(report_key) DO UPDATE SET
                 source=excluded.source, updated_at=excluded.updated_at""",
            (report_key, source),
        )
        conn.commit()
    finally:
        conn.close()


def set_sources(mapping: dict[str, str]) -> dict[str, Source]:
    """Bulk update; returns the full map after write."""
    for key, source in mapping.items():
        set_source(key, source if source in ("sql", "odata") else "odata")  # type: ignore[arg-type]
    return get_sources()


def sources_json() -> str:
    return json.dumps(get_sources(), sort_keys=True)
