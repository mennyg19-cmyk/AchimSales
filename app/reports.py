"""Mock catalog or live doorway → {data: {raw, tabs}}. Tests mock doorway.run_report."""

from __future__ import annotations

import assemble
import catalog
import doorway
import lookups
import params
import period
from deps import is_privileged, salesman_scope


def _viewer_salesman(user: dict, params_in: dict) -> str:
    scope = salesman_scope(user)
    salesman = params_in.get("salesman") or scope
    if scope and salesman and salesman != scope:
        salesman = scope
    return salesman or ""


def _stamp_period(payload: dict, params_in: dict) -> dict:
    report = payload["data"]
    if params_in.get("period"):
        report["period"] = params_in["period"]
    window = period.resolve_period(
        params_in.get("period") or "",
        params_in.get("from_date") or "",
        params_in.get("to_date") or "",
    )
    if window:
        report["from_date"] = window.start_date.isoformat()
        report["to_date"] = window.end_date.isoformat()
    elif params_in.get("from_date"):
        report["from_date"] = params_in["from_date"]
    elif params_in.get("to_date"):
        report["to_date"] = params_in["to_date"]
    return payload


def _apply_filters(payload: dict, key: str, user: dict, params_in: dict) -> dict:
    catalog.apply_viewer_filters(
        payload,
        salesman=_viewer_salesman(user, params_in),
        customers=params_in.get("customers") or None,
        n4_mode=params_in.get("n4_mode") or "both",
        hide_commissions=not is_privileged(user),
        report_key=key,
    )
    return _stamp_period(payload, params_in)


def _live_payload(key: str, params_in: dict) -> dict:
    if key == "number_4":
        mode = params.number_4_mode(params_in)
        sp_params = params.translate("number_4", params_in)
        customer_rows: list[dict] = []
        item_rows: list[dict] = []
        if mode in {"both", "by_customer"}:
            customer_rows = doorway.run_report(params.REPORT_IDS["number_4"], sp_params).rows
        if mode in {"both", "by_item"}:
            item_rows = doorway.run_report(params.NUMBER_4_ITEM_SP, sp_params).rows
        tabs = assemble.number_4_tabs(customer_rows, item_rows)
        return assemble.wrap(key, tabs, customer_rows + item_rows)
    if key == "sales_by_state":
        sp_params = params.translate("sales_by_state", params_in)
        summary = doorway.run_report(params.REPORT_IDS["sales_by_state"], sp_params)
        nyc = doorway.run_report(params.SALES_BY_STATE_NYC, sp_params)
        detail = doorway.run_report(params.SALES_BY_STATE_DETAIL, sp_params)
        tabs = assemble.sales_by_state_tabs(summary.rows, nyc.rows, detail.rows)
        return assemble.wrap(key, tabs, summary.rows + nyc.rows + detail.rows)
    if key == "item_averages":
        result = doorway.run_report(
            params.REPORT_IDS["item_averages"],
            params.translate("item_averages", params_in),
        )
        return assemble.from_result(key, result)
    report_id = params.REPORT_IDS.get(key)
    if report_id is None:
        raise KeyError(key)
    result = doorway.run_report(report_id, params.translate(key, params_in))
    return assemble.from_result(key, result)


def build_payload(key: str, user: dict, params_in: dict) -> dict:
    salesman = _viewer_salesman(user, params_in)
    scoped = dict(params_in)
    if salesman:
        scoped["salesman"] = salesman
    if not doorway.configured():
        payload = catalog.mock_report(
            key,
            salesman=salesman,
            customers=scoped.get("customers") or None,
            n4_mode=scoped.get("n4_mode") or "both",
            hide_commissions=not is_privileged(user),
        )
        payload["data"]["source"] = "mock"
        return _stamp_period(payload, scoped)
    payload = _live_payload(key, scoped)
    payload["data"]["source"] = "reporting_api"
    return _apply_filters(payload, key, user, scoped)


def last_order_page(account: str, user: dict) -> dict | None:
    if not doorway.configured():
        found = catalog.last_order_for(account)
        if found:
            found["source"] = "mock"
        return found
    info = lookups.customer(account)
    rows = doorway.run_report(
        params.REPORT_IDS["customer_last_order"],
        params.translate("customer_last_order", {"account": account}),
    ).rows
    if info is None and not rows:
        return None
    from_rows = assemble.customer_from_rows(account, rows)
    if info is None:
        customer = from_rows
    else:
        customer = dict(info)
        if not customer.get("salesman"):
            customer["salesman"] = from_rows["salesman"]
        if not customer.get("name") or customer.get("name") == account:
            customer["name"] = from_rows["name"] or customer.get("name") or account
    recent: list[dict] = []
    try:
        invoiced = doorway.run_report(
            params.REPORT_IDS["invoiced"],
            params.translate("invoiced", {"period": "last_7_days", "customers": [account]}),
        )
        recent = invoiced.rows
    except doorway.DoorwayError:
        recent = []
    view = assemble.last_order_view(account, rows, customer, recent)
    view["source"] = "reporting_api"
    return view
