"""Canonical company-wide Ordered views + which schedules use them.

Boot upserts these so every environment gets the same named views. Daily
company Ordered schedules (yesterday, not a salesman split, not Open-only)
use Daily Ordered. Heshy's open-orders schedule uses Heshy Open Orders
(all-time Open orders).
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
            "group": ["Salesman"],
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
        "params": {"period": "yesterday"},
        "layout": DAILY_ORDERED_LAYOUT,
    },
    {
        "report_key": "ordered",
        "name": HESHY_OPEN_VIEW,
        "params": {
            "period": "all_time",
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
            if _stamp(masters, sched, HESHY_OPEN_VIEW, HESHY_OPEN_LAYOUT):
                _ensure_heshy_params(masters, sched)
        elif is_daily_company_ordered(sched):
            _stamp(masters, sched, DAILY_ORDERED_VIEW, DAILY_ORDERED_LAYOUT)


def _stamp(masters: MasterScheduleRepository, sched, view_name: str, layout: dict) -> bool:
    name = (getattr(sched, "view_name", None) or "").strip()
    if name and name not in (DEFAULT_VIEW_NAME, CUSTOM_VIEW_NAME, view_name):
        return False
    masters.set_view(sched.id, view_name, layout)
    return True


_HESHY_SALESMAN = ["Hkaufman"]
_HESHY_STATUS = ["Open order"]
_VIEW_FILTER_KEYS = ("period", "start_date", "end_date", "salesman", "status", "customers")


def overlay_view_params(schedule_params: dict | None, view_params: dict | None) -> dict:
    """Named company-view filters win at send (layout already does this)."""
    out = dict(schedule_params or {})
    overlay = view_params if isinstance(view_params, dict) else {}
    for key in _VIEW_FILTER_KEYS:
        val = overlay.get(key)
        if val in (None, "", [], {}):
            continue
        out[key] = val
    return out


def _ensure_heshy_params(masters: MasterScheduleRepository, sched) -> None:
    params = dict(getattr(sched, "params", None) or {})
    changed = False
    if params.get("period") != "all_time":
        params["period"] = "all_time"
        changed = True
    if {s.lower() for s in _salesman_list(params)} != {"hkaufman"}:
        params["salesman"] = list(_HESHY_SALESMAN)
        changed = True
    if {s.lower() for s in _status_list(params)} != {"open order"}:
        params["status"] = list(_HESHY_STATUS)
        changed = True
    if changed:
        masters.replace_params(sched.id, params)
