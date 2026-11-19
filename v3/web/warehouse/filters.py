"""Open-status rules for warehouse dashboard lists (confirmed by Baruch)."""

from __future__ import annotations

from collections import Counter
from typing import Iterable


def is_open_shipment(status: str | None) -> bool:
    """Shipments open = status not Shipped."""
    return (status or "").strip().casefold() != "shipped"


def is_open_load(status: str | None) -> bool:
    """Loads open = status not Shipped."""
    return (status or "").strip().casefold() != "shipped"


def is_open_work(status: str | None) -> bool:
    """Work open = not Closed; Cancelled is excluded too."""
    s = (status or "").strip().casefold()
    return s not in {"closed", "cancelled", "canceled"}


def is_open_cluster(status: str | None) -> bool:
    """Clusters open = not Closed (Open, Passed, InProcess)."""
    return (status or "").strip().casefold() != "closed"


def is_open_wave(status: str | None) -> bool:
    """Waves open = WaveStatus not Shipped (Baruch, Nov 19 2026)."""
    return (status or "").strip().casefold() != "shipped"


def row_is_not_deleted(row: dict) -> bool:
    """Keep rows that are not tombstoned (IsDeleted=0 / false / blank)."""
    val = row.get("IsDeleted")
    if val is None:
        return True
    s = str(val).strip().casefold()
    return s in {"", "0", "false", "no"}


_OPEN_PREDICATES = {
    "shipments": ("ShipmentStatus", is_open_shipment),
    "loads": ("LoadStatus", is_open_load),
    "work": ("WorkStatus", is_open_work),
    "clusters": ("WorkClusterStatus", is_open_cluster),
    "waves": ("WaveStatus", is_open_wave),
}


def open_predicate(area: str):
    try:
        return _OPEN_PREDICATES[area]
    except KeyError as exc:
        raise KeyError(f"Unknown warehouse area {area!r}") from exc


def filter_open_rows(area: str, rows: Iterable[dict]) -> list[dict]:
    status_col, pred = open_predicate(area)
    return [r for r in rows if pred(r.get(status_col))]


def counts_by_status(rows: Iterable[dict], status_col: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        label = (row.get(status_col) or "").strip() or "(blank)"
        counts[label] += 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
