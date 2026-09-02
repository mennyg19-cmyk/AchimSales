"""Canonical company-wide Ordered views + which schedules use them.

Boot upserts these so every environment gets the same named views. Daily
company Ordered schedules (yesterday, not a salesman split, not Open-only)
use Daily Ordered. Heshy's open-orders schedule uses Heshy Open Orders.
"""

from __future__ import annotations

from web.data.repositories.company_views import CompanyViewRepository
from web.data.repositories.report_defaults import CUSTOM_VIEW_NAME, DEFAULT_VIEW_NAME
from web.data.repositories.schedules import MasterScheduleRepository

DAILY_ORDERED_VIEW = "Daily Ordered"
HESHY_OPEN_VIEW = "Heshy Open Orders"

_FULL_DATA_COLS = [
    "SalesOrderNumber", "CustomerAccount", "CustomerName", "SalesOrderName",
    "OrderDate", "purchid", "ExpectedArrivalDate", "ShipDate",
    "Item#", "ItemName", "UnitPrice", "Status", "Fulfillment %",
    "QtyOrdered", "QtyReserved", "QtyReleased", "QtyCancelled", "QtyLeftToShip",
    "Ordered $", "Cancelled $", "Released $", "Open $",
]

DAILY_ORDERED_LAYOUT = {
    "active": "by_customer",
    "order": ["summary", "by_customer", "by_item", "by_order", "by_salesman", "full_data"],
    "views": {
        "by_customer": {
            "group": ["Salesman", "CustomerName"],
            "hidden": [],
            "sorters": [
                {"column": "Salesman", "dir": "asc"},
                {"column": "CustomerName", "dir": "asc"},
            ],
        },
        "summary": {
            "group": ["Salesman", "Customer Name"],
            "sorters": [
                {"column": "Salesman", "dir": "asc"},
                {"column": "Customer Name", "dir": "asc"},
                {"column": "Item Number", "dir": "asc"},
            ],
        },
    },
}

HESHY_OPEN_LAYOUT = {
    "active": "full_data",
    "order": ["full_data"],
    "views": {
        "full_data": {
            "group": ["SalesOrderNumber"],
            "sorters": [
                {"column": "CustomerName", "dir": "asc"},
                {"column": "SalesOrderNumber", "dir": "asc"},
            ],
            "hidden": ["LineNumber"],
            "order": _FULL_DATA_COLS,
        },
    },
}

CANONICAL = (
    {
        "report_key": "ordered",
        "name": DAILY_ORDERED_VIEW,
        "params": {},
        "layout": DAILY_ORDERED_LAYOUT,
    },
    {
        "report_key": "ordered",
        "name": HESHY_OPEN_VIEW,
        "params": {
            "period": "yesterday",
            "salesman": "Hkaufman",
            "status": "Open order",
        },
        "layout": HESHY_OPEN_LAYOUT,
    },
)


def _status_list(params: dict) -> list[str]:
    raw = (params or {}).get("status") or []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


def _salesman_list(params: dict) -> list[str]:
    raw = (params or {}).get("salesman") or []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


def is_daily_company_ordered(sched) -> bool:
    """Full-company daily Ordered (yesterday), not a split file and not Open-only."""
    if getattr(sched, "report_key", "") != "ordered":
        return False
    cad = getattr(sched, "cadence", None) or {}
    if cad.get("freq") != "daily":
        return False
    params = getattr(sched, "params", None) or {}
    if params.get("split_by_salesman") or params.get("email_to_salesmen") or params.get("email_salesman_keys"):
        return False
    if _status_list(params):
        return False
    if _salesman_list(params):
        return False
    return True


def is_heshy_open_orders(sched) -> bool:
    if getattr(sched, "report_key", "") != "ordered":
        return False
    params = getattr(sched, "params", None) or {}
    statuses = [s.lower() for s in _status_list(params)]
    if not any("open" in s for s in statuses):
        return False
    keys = {s.lower().replace(" ", "") for s in _salesman_list(params)}
    return "hkaufman" in keys or "heshy" in keys


def seed_canonical_company_views(db) -> None:
    repo = CompanyViewRepository(db)
    for spec in CANONICAL:
        repo.upsert(
            spec["report_key"], spec["name"],
            params=spec["params"], layout=spec["layout"], updated_by=None,
        )
    stamp_company_views_on_schedules(db)


def stamp_company_views_on_schedules(db) -> None:
    """Point matching company schedules at the canonical views (live at send)."""
    masters = MasterScheduleRepository(db)
    for sched in masters.list_all():
        if is_heshy_open_orders(sched):
            _stamp(masters, sched, HESHY_OPEN_VIEW, HESHY_OPEN_LAYOUT)
        elif is_daily_company_ordered(sched):
            _stamp(masters, sched, DAILY_ORDERED_VIEW, DAILY_ORDERED_LAYOUT)


def _stamp(masters: MasterScheduleRepository, sched, view_name: str, layout: dict) -> None:
    name = (getattr(sched, "view_name", None) or "").strip()
    if name and name not in (DEFAULT_VIEW_NAME, CUSTOM_VIEW_NAME, view_name):
        return
    masters.set_view(sched.id, view_name, layout)


_WINDOW_KEYS = ("period", "start_date", "end_date", "from", "to")


def params_without_window(params: dict | None) -> dict:
    """Company-view filters minus the date window. Schedules own YTD / MTD / yesterday."""
    out = dict(params or {})
    for key in _WINDOW_KEYS:
        out.pop(key, None)
    return out
