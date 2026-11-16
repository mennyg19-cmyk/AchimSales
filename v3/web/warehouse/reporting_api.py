"""Reporting API warehouse provider.

Fetches open rows per known status (MaxRows=10000 each), merges, then always
re-filters client-side by open rules and Company/dataAreaId=achm. Caches briefly.
On any API error, falls back to SampleWarehouseProvider and surfaces SAMPLE DATA.

Not used until WH_DASHBOARD_PROVIDER=reporting_api. Default stays sample.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from web.warehouse.filters import counts_by_status, filter_open_rows
from web.warehouse.sample import SampleWarehouseProvider
from web.warehouse.schema import (
    AREA_TITLES,
    AREAS,
    OPEN_STATUS_FETCH,
    REPORT_IDS,
    STATUS_COLUMNS,
)
from web.warehouse.timeutil import latest_refresh_utc, utc_to_eastern_display

log = logging.getLogger(__name__)

# Verified MaxRows shape (string) via /api/dev/reporting probe. Status filter
# names besides ShipmentStatus are assumed by analogy; client always re-filters.
_MAX_ROWS = "10000"
_MAX_ROWS_CAP = 10000
_DEFAULT_CACHE_SECONDS = 300
_ACHM = "achm"

# Stable id keys for merge dedupe (RecId first when present).
_DEDUP_KEYS = {
    "shipments": ("RecId", "ShipmentId"),
    "loads": ("RecId", "LoadId"),
    "work": ("RecId", "WorkId"),
    "clusters": ("RecId", "ClusterId"),
}


class _ReportClient(Protocol):
    def run_report(self, report_id: str, params: dict[str, Any]) -> Any: ...


@dataclass
class _AreaBundle:
    rows: list[dict] = field(default_factory=list)
    truncated: bool = False


@dataclass
class _Snapshot:
    rows_by_area: dict[str, list[dict]]
    truncated_areas: frozenset[str]
    fetched_at: float
    using_fallback: bool
    error_message: str | None
    provider_label: str


def row_is_achm(row: dict) -> bool:
    """Keep rows for company achm (Company or dataAreaId). Case-insensitive."""
    for key in ("Company", "dataAreaId"):
        val = (row.get(key) or "").strip().casefold()
        if val == _ACHM:
            return True
    return False


def _dedupe_rows(area: str, rows: list[dict]) -> list[dict]:
    keys = _DEDUP_KEYS[area]
    seen: set[str] = set()
    out: list[dict] = []
    for i, row in enumerate(rows):
        token = None
        for key in keys:
            val = row.get(key)
            if val is not None and str(val).strip() != "":
                token = f"{key}:{val}"
                break
        if token is None:
            token = f"idx:{i}"
        if token in seen:
            continue
        seen.add(token)
        out.append(row)
    return out


def _result_row_count(result: Any, rows: list[dict]) -> int:
    raw = getattr(result, "row_count", None)
    if raw is None and isinstance(result, dict):
        raw = result.get("row_count")
    try:
        if raw is not None:
            return int(raw)
    except (TypeError, ValueError):
        pass
    return len(rows)


def _result_rows(result: Any) -> list[dict]:
    rows = getattr(result, "rows", None)
    if rows is None and isinstance(result, dict):
        rows = result.get("rows")
    return list(rows or [])


class ReportingApiWarehouseProvider:
    """Read-only warehouse lists via ReportingApiClient."""

    def __init__(
        self,
        client: _ReportClient,
        *,
        cache_seconds: int = _DEFAULT_CACHE_SECONDS,
        fallback: SampleWarehouseProvider | None = None,
    ):
        self._client = client
        self._cache_seconds = max(0, int(cache_seconds))
        self._fallback = fallback or SampleWarehouseProvider()
        self._snapshot: _Snapshot | None = None

    def get_open_shipments(self) -> list[dict]:
        return list(self._rows("shipments"))

    def get_open_loads(self) -> list[dict]:
        return list(self._rows("loads"))

    def get_open_work(self) -> list[dict]:
        return list(self._rows("work"))

    def get_open_clusters(self) -> list[dict]:
        return list(self._rows("clusters"))

    def data_as_of(self) -> str:
        snap = self._ensure_snapshot()
        if snap.using_fallback:
            return self._fallback.data_as_of()
        stamps = []
        for area in AREAS:
            latest = latest_refresh_utc(snap.rows_by_area.get(area, []))
            if latest is not None:
                stamps.append(latest)
        if not stamps:
            return "Unknown (live provider; no refresh stamps)"
        return utc_to_eastern_display(max(stamps)) or "Unknown"

    def view_meta(self) -> dict[str, Any]:
        snap = self._ensure_snapshot()
        truncated = sorted(snap.truncated_areas)
        return {
            "provider": snap.provider_label,
            "using_sample_fallback": snap.using_fallback,
            "error_message": snap.error_message,
            "possibly_truncated": bool(truncated),
            "truncated_areas": truncated,
        }

    def tile_summary(self) -> dict[str, Any]:
        snap = self._ensure_snapshot()
        tiles = []
        for area in AREAS:
            rows = snap.rows_by_area.get(area, [])
            status_col = STATUS_COLUMNS[area]
            tiles.append({
                "key": area,
                "title": AREA_TITLES[area],
                "total": len(rows),
                "by_status": counts_by_status(rows, status_col),
                "coming_soon": False,
                "href": f"/whdashboard/{area}",
                "possibly_truncated": area in snap.truncated_areas,
            })
        tiles.append({
            "key": "waves", "title": "Waves", "total": None,
            "by_status": {}, "coming_soon": True, "href": None,
            "possibly_truncated": False,
        })
        tiles.append({
            "key": "due_dates", "title": "Due dates", "total": None,
            "by_status": {}, "coming_soon": True, "href": None,
            "possibly_truncated": False,
        })
        meta = self.view_meta()
        return {
            "data_as_of": self.data_as_of(),
            "tiles": tiles,
            **meta,
        }

    def _rows(self, area: str) -> list[dict]:
        return self._ensure_snapshot().rows_by_area.get(area, [])

    def _ensure_snapshot(self) -> _Snapshot:
        now = time.monotonic()
        if (
            self._snapshot is not None
            and (now - self._snapshot.fetched_at) < self._cache_seconds
        ):
            return self._snapshot
        try:
            self._snapshot = self._fetch_live(now)
        except Exception as exc:
            log.exception("WH dashboard Reporting API failed; using sample data")
            self._snapshot = self._fallback_snapshot(now, str(exc))
        return self._snapshot

    def _fallback_snapshot(self, now: float, error: str) -> _Snapshot:
        return _Snapshot(
            rows_by_area={
                "shipments": self._fallback.get_open_shipments(),
                "loads": self._fallback.get_open_loads(),
                "work": self._fallback.get_open_work(),
                "clusters": self._fallback.get_open_clusters(),
            },
            truncated_areas=frozenset(),
            fetched_at=now,
            using_fallback=True,
            error_message=error,
            provider_label="sample",
        )

    def _fetch_live(self, now: float) -> _Snapshot:
        rows_by_area: dict[str, list[dict]] = {}
        truncated: set[str] = set()
        for area in AREAS:
            bundle = self._fetch_area(area)
            rows_by_area[area] = bundle.rows
            if bundle.truncated:
                truncated.add(area)
        return _Snapshot(
            rows_by_area=rows_by_area,
            truncated_areas=frozenset(truncated),
            fetched_at=now,
            using_fallback=False,
            error_message=None,
            provider_label="reporting_api",
        )

    def _fetch_area(self, area: str) -> _AreaBundle:
        report_id = REPORT_IDS[area]
        status_col = STATUS_COLUMNS[area]
        merged: list[dict] = []
        truncated = False
        for status in OPEN_STATUS_FETCH[area]:
            params = {
                "MaxRows": _MAX_ROWS,
                status_col: status,
            }
            result = self._client.run_report(report_id, params)
            rows = _result_rows(result)
            if _result_row_count(result, rows) >= _MAX_ROWS_CAP:
                truncated = True
            merged.extend(rows)

        merged = _dedupe_rows(area, merged)
        # Always re-filter: status filters may be ignored by the API; company
        # filters were not verified on the wire.
        open_rows = filter_open_rows(area, merged)
        achm_rows = [r for r in open_rows if row_is_achm(r)]
        return _AreaBundle(rows=achm_rows, truncated=truncated)
