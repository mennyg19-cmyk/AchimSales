"""Report cards, grid viewer, Last Order, views, export, mock mail."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

import catalog
import store
from deps import (
    can_see_report,
    can_read_job,
    flash,
    is_privileged,
    need_login,
    page,
    require_csrf,
    salesman_scope,
    session_user,
    visible_reports,
)
from export_xlsx import workbook_bytes

router = APIRouter()


def _params_from_request(body: dict, spec: dict) -> dict:
    filters = set(spec["filters"])
    params = {}
    if "period" in filters:
        params["period"] = body.get("period") or "last_7_days"
        params["from_date"] = body.get("from_date") or ""
        params["to_date"] = body.get("to_date") or ""
    if "status" in filters:
        params["status"] = body.get("status") or ""
    if "year" in filters:
        params["year"] = body.get("year") or catalog.YEAR_OPTIONS[0]
    if "n4_mode" in filters:
        params["n4_mode"] = body.get("n4_mode") or "both"
    if "salesman" in filters:
        params["salesman"] = body.get("salesman") or ""
    if "customers" in filters:
        raw = body.get("customers") or []
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.split(",") if part.strip()]
        params["customers"] = raw
    return params


def _build_payload(key: str, user: dict, params: dict) -> dict:
    scope = salesman_scope(user)
    salesman = params.get("salesman") or scope
    if scope and salesman and salesman != scope:
        salesman = scope
    payload = catalog.mock_report(
        key,
        salesman=salesman,
        customers=params.get("customers") or None,
        n4_mode=params.get("n4_mode") or "both",
        hide_commissions=not is_privileged(user),
    )
    report = payload["data"]
    if params.get("period"):
        report["period"] = params["period"]
    if params.get("from_date"):
        report["from_date"] = params["from_date"]
    if params.get("to_date"):
        report["to_date"] = params["to_date"]
    report["source"] = "mock"
    return payload


@router.get("/")
def reports_home(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    cards = visible_reports(user)
    views = store.list_views(user["email"], is_privileged(user) or user.get("can_see_company_views"))
    titles = {item["key"]: item["title"] for item in catalog.REPORTS}
    company = []
    presets = []
    for view in views:
        if not can_see_report(user, view["report_key"]):
            continue
        href = f"/reports/{view['report_key']}?view={view['id']}"
        card = {
            "name": view["name"],
            "report_title": titles.get(view["report_key"], view["report_key"]),
            "url": href,
        }
        if view["kind"] == "company":
            company.append(card)
        elif view.get("owner_email") == user["email"]:
            presets.append(card)
    return page(
        request,
        "reports_list.html",
        active_tab="reports",
        report_cards=cards,
        backlog=catalog.BACKLOG,
        company_views=company if (is_privileged(user) or user.get("can_see_company_views")) else [],
        presets=presets,
    )


@router.get("/reports/{report_key}")
def report_page(request: Request, report_key: str):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    spec = catalog.spec(report_key)
    if spec is None or spec["in_app"]:
        return RedirectResponse("/", status_code=302)
    if not can_see_report(user, report_key):
        flash(request, "That report is hidden or not available for your role.", "warn")
        return RedirectResponse("/", status_code=302)
    view_id = request.query_params.get("view")
    loaded = store.get_view(int(view_id)) if view_id and view_id.isdigit() else None
    return page(
        request,
        "report_view.html",
        active_tab="reports",
        report_key=report_key,
        report_title=spec["title"],
        filters=spec["filters"],
        period_options=catalog.PERIOD_OPTIONS,
        status_options=catalog.STATUS_OPTIONS,
        n4_mode_options=catalog.N4_MODE_OPTIONS,
        year_options=catalog.YEAR_OPTIONS,
        salesmen=catalog.SALESMEN,
        customers=catalog.CUSTOMERS,
        loaded_view=loaded,
        privileged=is_privileged(user),
        can_company=is_privileged(user),
    )


@router.get("/api/reports/{report_key}/mock")
def report_mock(request: Request, report_key: str):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    if catalog.spec(report_key) is None or not can_see_report(user, report_key):
        return JSONResponse({"error": "Unknown or hidden report"}, status_code=404)
    payload = _build_payload(report_key, user, {})
    store.save_job(report_key, catalog.spec(report_key)["title"], payload, owner_email=user["email"])
    return payload


@router.post("/api/reports/{report_key}/run")
async def report_run(request: Request, report_key: str):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    user = session_user(request)
    spec = catalog.spec(report_key)
    if spec is None or spec["in_app"] or not can_see_report(user, report_key):
        return JSONResponse({"error": "Unknown or hidden report"}, status_code=404)
    body = await request.json()
    params = _params_from_request(body or {}, spec)
    payload = _build_payload(report_key, user, params)
    job_id = store.save_job(report_key, spec["title"], payload, owner_email=user["email"])
    payload["data"]["job_id"] = job_id
    return payload


@router.get("/api/reports/{report_key}/xlsx")
async def report_xlsx(request: Request, report_key: str):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    spec = catalog.spec(report_key)
    if spec is None or not can_see_report(user, report_key):
        return JSONResponse({"error": "Unknown or hidden report"}, status_code=404)
    params = _params_from_request(dict(request.query_params), spec)
    raw_customers = request.query_params.get("customers") or ""
    if raw_customers:
        params["customers"] = [part for part in raw_customers.split(",") if part]
    payload = _build_payload(report_key, user, params)
    store.save_job(report_key, spec["title"] + " export", payload, owner_email=user["email"])
    return Response(
        workbook_bytes(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{report_key}.xlsx"'},
    )


@router.post("/api/reports/{report_key}/email")
async def report_email(request: Request, report_key: str):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    user = session_user(request)
    spec = catalog.spec(report_key)
    if spec is None or not can_see_report(user, report_key):
        return JSONResponse({"error": "Unknown or hidden report"}, status_code=404)
    body = await request.json()
    params = _params_from_request(body or {}, spec)
    payload = _build_payload(report_key, user, params)
    store.save_job(report_key, spec["title"], payload, owner_email=user["email"])
    recipients = store.mail_recipients((body or {}).get("recipients") or user["email"])
    subject = (body or {}).get("subject") or f"[MOCK] {spec['title']}"
    store.add_outbox(recipients, subject, "Dummy Excel attached. Graph mail is not wired yet.")
    return {"ok": True, "recipients": recipients, "mock": True}


@router.get("/report/customer-last-order")
def last_order_pick(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    if not can_see_report(user, "customer_last_order"):
        flash(request, "Customer's Last Order is hidden.", "warn")
        return RedirectResponse("/", status_code=302)
    scope = salesman_scope(user)
    excluded = set(store.exclusions_for(user["email"]))
    customers = [
        row
        for row in catalog.CUSTOMERS
        if (not scope or row["salesman"] == scope) and row["account"] not in excluded
    ]
    return page(
        request,
        "last_order_pick.html",
        active_tab="reports",
        customers=customers,
        salesmen=catalog.SALESMEN,
        show_salesman_picker=not scope,
    )


@router.get("/report/customer-last-order/{account}")
def last_order_view(request: Request, account: str):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    if not can_see_report(user, "customer_last_order"):
        flash(request, "Customer's Last Order is hidden.", "warn")
        return RedirectResponse("/", status_code=302)
    found = catalog.last_order_for(account)
    if found is None:
        flash(request, "No mock customer with that account.", "warn")
        return RedirectResponse("/report/customer-last-order", status_code=302)
    if account in store.exclusions_for(user["email"]):
        flash(request, "That customer is on your exclusion list.", "warn")
        return RedirectResponse("/report/customer-last-order", status_code=302)
    scope = salesman_scope(user)
    if scope and found["customer"]["salesman"] != scope:
        flash(request, "That customer is outside your SalesGroup.", "warn")
        return RedirectResponse("/report/customer-last-order", status_code=302)
    return page(request, "last_order_view.html", active_tab="reports", view=found)


@router.get("/api/jobs")
def jobs_list(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    kept = request.query_params.get("kept") == "1"
    if is_privileged(user):
        return {"jobs": store.list_jobs(kept_only=kept)}
    return {"jobs": store.list_jobs(kept_only=kept, owner_email=user["email"])}


@router.get("/api/jobs/{job_id}")
def job_get(request: Request, job_id: int):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    job = store.get_job(job_id)
    if job is None or not can_read_job(user, job):
        return JSONResponse({"error": "Unknown run"}, status_code=404)
    return job


@router.post("/api/jobs/{job_id}/keep")
async def job_keep(request: Request, job_id: int):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    user = session_user(request)
    job = store.get_job(job_id)
    if job is None or not can_read_job(user, job):
        return JSONResponse({"error": "Unknown run"}, status_code=404)
    body = await request.json()
    name = (body or {}).get("name") or "Kept run"
    store.keep_job(job_id, name)
    return {"ok": True}


@router.get("/api/views")
def views_list(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    report_key = request.query_params.get("report") or ""
    privileged = is_privileged(user) or user.get("can_see_company_views")
    if report_key:
        return {"views": store.list_views_for_report(user["email"], report_key, privileged)}
    return {"views": store.list_views(user["email"], privileged)}


@router.post("/api/views")
async def views_save(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    user = session_user(request)
    body = await request.json()
    name = ((body or {}).get("name") or "").strip()
    report_key = (body or {}).get("report_key") or ""
    if not name or catalog.spec(report_key) is None:
        return JSONResponse({"error": "Name and report_key are required"}, status_code=400)
    kind = (body or {}).get("kind") or "personal"
    if kind == "company" and not is_privileged(user):
        return JSONResponse({"error": "Company views are admin-only"}, status_code=403)
    if kind == "company_default":
        if not is_privileged(user):
            return JSONResponse({"error": "Company Default is admin-only"}, status_code=403)
        kind = "company"
        name = name or "Company Default"
    owner = None if kind == "company" else user["email"]
    params = (body or {}).get("params") or {}
    include_period = 1 if (body or {}).get("include_period") else 0
    view_id = store.add_view(owner, report_key, name, kind, params, include_period)
    return {"ok": True, "id": view_id}


@router.post("/api/views/{view_id}/delete")
def views_delete(request: Request, view_id: int):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    user = session_user(request)
    view = store.get_view(view_id)
    if view is None:
        return JSONResponse({"error": "Unknown view"}, status_code=404)
    if view["kind"] == "company" and not is_privileged(user):
        return JSONResponse({"error": "Company views are admin-only"}, status_code=403)
    if view["kind"] != "company" and view.get("owner_email") != user["email"] and not is_privileged(user):
        return JSONResponse({"error": "Not your view"}, status_code=403)
    store.delete_view(view_id)
    return {"ok": True}
