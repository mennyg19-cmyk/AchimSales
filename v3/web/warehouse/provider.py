"""Warehouse dashboard provider interface + factory."""

from __future__ import annotations

from typing import Any, Protocol

from web.warehouse.sample import SampleWarehouseProvider


class WarehouseDataProvider(Protocol):
    def get_open_shipments(self) -> list[dict]: ...
    def get_open_loads(self) -> list[dict]: ...
    def get_open_work(self) -> list[dict]: ...
    def get_open_clusters(self) -> list[dict]: ...
    def data_as_of(self) -> str: ...
    def tile_summary(self) -> dict[str, Any]: ...


def get_warehouse_provider(
    name: str = "sample",
    *,
    reporting_client=None,
) -> WarehouseDataProvider:
    """Build the configured provider. Default is sample (synthetic)."""
    key = (name or "sample").strip().lower()
    if key in {"sample", "synthetic", "fixture"}:
        return SampleWarehouseProvider()
    if key in {"reporting_api", "live", "api"}:
        if reporting_client is None:
            raise RuntimeError(
                "WH_DASHBOARD_PROVIDER=reporting_api requires a ReportingApiClient"
            )
        from web.warehouse.reporting_api import ReportingApiWarehouseProvider

        return ReportingApiWarehouseProvider(reporting_client)
    raise ValueError(
        f"Unknown WH_DASHBOARD_PROVIDER {name!r} (use 'sample' or 'reporting_api')"
    )
