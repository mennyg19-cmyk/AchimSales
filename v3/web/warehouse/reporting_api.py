"""Reporting API warehouse provider (stubbed / disabled by default).

Does not call production. When WH_DASHBOARD_PROVIDER=reporting_api and a client
is injected, it POSTs to /api/reports/{report_id}/run for the gateway-aligned
ids in schema.REPORT_IDS. Office must confirm those ids exist on the on-prem
catalog before enabling.
"""

from __future__ import annotations

from typing import Any, Protocol

from web.warehouse.filters import counts_by_status, filter_open_rows
from web.warehouse.schema import AREA_TITLES, AREAS, REPORT_IDS, STATUS_COLUMNS
from web.warehouse.timeutil import latest_refresh_utc, utc_to_eastern_display


class _ReportClient(Protocol):
    def run_report(self, report_id: str, params: dict[str, Any]) -> Any: ...


# PascalCase params mirror other ReportingApiClient call sites. MaxRows is the
# gateway's documented cap (10000). Open warehouse lists may need paging later.
_DEFAULT_PARAMS = {
    "MaxRows": 10000,
    "IncludeDeleted": 0,
}


class ReportingApiWarehouseProvider:
    """Read-only warehouse lists via ReportingApiClient. Not used until enabled."""

    def __init__(self, client: _ReportClient, *, params: dict[str, Any] | None = None):
        self._client = client
        self._params = dict(_DEFAULT_PARAMS if params is None else params)
        self._cache: dict[str, list[dict]] = {}

    def get_open_shipments(self) -> list[dict]:
        return self._open("shipments")

    def get_open_loads(self) -> list[dict]:
        return self._open("loads")

    def get_open_work(self) -> list[dict]:
        return self._open("work")

    def get_open_clusters(self) -> list[dict]:
        return self._open("clusters")

    def data_as_of(self) -> str:
        stamps = []
        for area in AREAS:
            rows = self._raw(area)
            latest = latest_refresh_utc(rows)
            if latest is not None:
                stamps.append(latest)
        if not stamps:
            return "Unknown (live provider; no UpdatedUtc/LastSeenUtc/LastImportedUTC)"
        newest = max(stamps)
        return utc_to_eastern_display(newest) or "Unknown"

    def tile_summary(self) -> dict[str, Any]:
        tiles = []
        for area in AREAS:
            rows = self._open(area)
            status_col = STATUS_COLUMNS[area]
            tiles.append({
                "key": area,
                "title": AREA_TITLES[area],
                "total": len(rows),
                "by_status": counts_by_status(rows, status_col),
                "coming_soon": False,
                "href": f"/WHdashboard/{area}",
            })
        tiles.append({
            "key": "waves", "title": "Waves", "total": None,
            "by_status": {}, "coming_soon": True, "href": None,
        })
        tiles.append({
            "key": "due_dates", "title": "Due dates", "total": None,
            "by_status": {}, "coming_soon": True, "href": None,
        })
        return {
            "data_as_of": self.data_as_of(),
            "tiles": tiles,
            "provider": "reporting_api",
        }

    def _open(self, area: str) -> list[dict]:
        return filter_open_rows(area, self._raw(area))

    def _raw(self, area: str) -> list[dict]:
        if area in self._cache:
            return self._cache[area]
        report_id = REPORT_IDS[area]
        result = self._client.run_report(report_id, dict(self._params))
        rows = list(getattr(result, "rows", None) or [])
        self._cache[area] = rows
        return rows
