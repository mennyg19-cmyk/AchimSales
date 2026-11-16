"""Warehouse dashboard data layer (provider interface + sample/live stubs)."""

from web.warehouse.provider import WarehouseDataProvider, get_warehouse_provider

__all__ = ["WarehouseDataProvider", "get_warehouse_provider"]
