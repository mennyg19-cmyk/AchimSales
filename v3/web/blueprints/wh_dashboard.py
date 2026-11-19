"""Warehouse operations dashboard (/whdashboard).

Allowlist-only: WH_DASHBOARD_ALLOWED_EMAILS (default bgrossman@achimonline.com).
Not role-based. Data from WH_DASHBOARD_PROVIDER (default: sample).
Does not change the customer /dashboard page.
"""

from __future__ import annotations

import json

from flask import (
    Blueprint,
    abort,
    current_app,
    render_template,
    url_for,
)

from web.auth.decorators import require_login
from web.auth.session import current_principal
from web.warehouse.access import email_may_access_wh_dashboard
from web.warehouse.filters import counts_by_status
from web.warehouse.schema import (
    AREA_TITLES,
    AREAS,
    COLUMNS,
    DEFAULT_VISIBLE,
    PLACEHOLDER_AREAS,
    STATUS_COLUMNS,
)

wh_dashboard_bp = Blueprint("wh_dashboard", __name__)


def _require_wh_access():
    """Gate every WH route: signed-in email must be on the allowlist."""
    p = current_principal()
    allowed = current_app.config["APP_CONFIG"].wh_dashboard_allowed_emails
    if not email_may_access_wh_dashboard(p.email if p else None, allowed):
        abort(403, description="Warehouse dashboard access is restricted")
    return p


def _provider():
    return current_app.config["WH_DASHBOARD_PROVIDER"]


def _view_meta(prov) -> dict:
    getter = getattr(prov, "view_meta", None)
    if callable(getter):
        meta = getter()
        meta.setdefault("unrecognized_statuses", {})
        meta.setdefault("area_errors", {})
        return meta
    return {
        "provider": "sample",
        "using_sample_fallback": False,
        "error_message": None,
        "possibly_truncated": False,
        "truncated_areas": [],
        "unrecognized_statuses": {},
        "area_errors": {},
    }


def _rows_for(area: str) -> list[dict]:
    prov = _provider()
    if area == "shipments":
        return prov.get_open_shipments()
    if area == "loads":
        return prov.get_open_loads()
    if area == "work":
        return prov.get_open_work()
    if area == "clusters":
        return prov.get_open_clusters()
    if area == "waves":
        return prov.get_open_waves()
    abort(404)


# Canonical path is /whdashboard; /WHdashboard kept for bookmarks (same view).
@wh_dashboard_bp.get("/whdashboard")
@wh_dashboard_bp.get("/WHdashboard")
@require_login
def wh_dashboard():
    _require_wh_access()
    summary = _provider().tile_summary()
    for tile in summary["tiles"]:
        if tile.get("coming_soon"):
            tile["href"] = None
        elif tile.get("key") in AREAS:
            tile["href"] = url_for("wh_dashboard.wh_list", area=tile["key"])
    return render_template(
        "wh_dashboard.html",
        active_tab="wh_dashboard",
        data_as_of=summary["data_as_of"],
        tiles=summary["tiles"],
        provider_name=summary.get("provider", "sample"),
        using_sample_fallback=bool(summary.get("using_sample_fallback")),
        error_message=summary.get("error_message"),
        possibly_truncated=bool(summary.get("possibly_truncated")),
        truncated_areas=summary.get("truncated_areas") or [],
        unrecognized_statuses=summary.get("unrecognized_statuses") or {},
    )


@wh_dashboard_bp.get("/whdashboard/<area>")
@wh_dashboard_bp.get("/WHdashboard/<area>")
@require_login
def wh_list(area: str):
    _require_wh_access()
    area = (area or "").strip().lower()
    if area in PLACEHOLDER_AREAS:
        abort(404, description=f"{AREA_TITLES.get(area, area)} is coming soon")
    if area not in AREAS:
        abort(404)

    prov = _provider()
    meta = _view_meta(prov)
    area_errors = meta.get("area_errors") or {}
    area_error = area_errors.get(area)
    rows = [] if area_error else _rows_for(area)
    status_col = STATUS_COLUMNS[area]
    columns = COLUMNS[area]
    visible = DEFAULT_VISIBLE[area]
    status_counts = counts_by_status(rows, status_col)
    payload = [{col: row.get(col) for col in columns} for row in rows]
    truncated_areas = meta.get("truncated_areas") or []

    return render_template(
        "wh_dashboard_list.html",
        active_tab="wh_dashboard",
        area=area,
        title=AREA_TITLES[area],
        status_column=status_col,
        columns=columns,
        default_visible=visible,
        status_counts=status_counts,
        row_count=len(rows),
        data_as_of=prov.data_as_of(),
        table_data_json=json.dumps(payload, default=str),
        columns_json=json.dumps(columns),
        default_visible_json=json.dumps(visible),
        status_column_json=json.dumps(status_col),
        provider_name=meta.get("provider", "sample"),
        using_sample_fallback=bool(meta.get("using_sample_fallback")),
        error_message=meta.get("error_message"),
        area_error=area_error,
        possibly_truncated=area in truncated_areas,
        truncated_areas=truncated_areas,
        unrecognized_statuses=(meta.get("unrecognized_statuses") or {}).get(area) or [],
    )
