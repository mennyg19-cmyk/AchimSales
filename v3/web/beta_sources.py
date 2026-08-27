"""Per-report SQL vs OData map for the home site.

Stored in v3 precious.db (`beta_report_sources`). Values are 'sql' or 'odata'.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

log = logging.getLogger(__name__)

Source = Literal["sql", "odata"]

_DEFAULT_SQL = frozenset({
    "ordered",
    "invoiced",
    "customer_activity",
    "salesman",
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


def _db():
    from flask import current_app, has_app_context

    if not has_app_context():
        return None
    return current_app.config.get("DB")


def get_sources() -> dict[str, Source]:
    out = default_sources()
    db = _db()
    if db is None:
        return out
    try:
        with db.precious() as conn:
            rows = conn.execute("SELECT report_key, source FROM beta_report_sources").fetchall()
            for row in rows:
                src = (row["source"] or "").strip().lower()
                if src in ("sql", "odata"):
                    out[str(row["report_key"])] = src  # type: ignore[assignment]
    except Exception:  # noqa: BLE001 - home site still boots if the table is missing
        log.exception("report sources: could not read precious DB; using defaults")
    return out


def get_source(report_key: str) -> Source:
    if report_key not in _ALL_KEYS:
        return "sql"
    return get_sources().get(report_key, "odata")


def set_source(report_key: str, source: Source) -> None:
    if source not in ("sql", "odata"):
        raise ValueError(f"source must be sql or odata, got {source!r}")
    if report_key not in _ALL_KEYS:
        raise ValueError(f"unknown report_key {report_key!r}")
    db = _db()
    if db is None:
        raise RuntimeError("report sources need an app context")
    with db.precious() as conn:
        conn.execute(
            """INSERT INTO beta_report_sources (report_key, source, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(report_key) DO UPDATE SET
                 source=excluded.source, updated_at=excluded.updated_at""",
            (report_key, source),
        )


def set_sources(mapping: dict[str, str]) -> dict[str, Source]:
    for key, source in mapping.items():
        set_source(key, source if source in ("sql", "odata") else "odata")  # type: ignore[arg-type]
    return get_sources()


def sources_json() -> str:
    return json.dumps(get_sources(), sort_keys=True)
