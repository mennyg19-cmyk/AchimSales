"""Settings hub, Users & access, visibility, history, developer tools."""

from __future__ import annotations

import json
import re
import sqlite3

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

import catalog
import config
import store
from db import db
from deps import (
    THEME_BODY_CLASS,
    flash,
    is_privileged,
    need_login,
    page,
    require_csrf,
    session_from_row,
    session_user,
)

router = APIRouter()

FLAGS = (
    ("show_company_schedule_setup", "Show the Company schedules setup page (runs still happen if this is off)."),
)


def _deny(request: Request, message: str, dest: str = "/settings"):
    flash(request, message, "warn")
    code = 303 if request.method == "POST" else 302
    return RedirectResponse(dest, status_code=code)


def _guard_admin(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    if not is_privileged(session_user(request)):
        return _deny(request, "Admin only.", "/settings")
    return None


def _guard_developer(request: Request, dest: str = "/settings"):
    denied = need_login(request)
    if denied:
        return denied
    if not is_privileged(session_user(request)):
        return _deny(request, "Developer only.", dest)
    return None


@router.get("/settings")
def settings_page(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    vis = store.visibility_map()
    reports = [
        {**report, "enabled": vis.get(report["key"], True)}
        for report in catalog.REPORTS
    ]
    flags = [
        {"key": key, "description": desc, "enabled": store.setting(key, "0") == "1"}
        for key, desc in FLAGS
    ]
    return page(
        request,
        "settings.html",
        active_tab="settings",
        reports=reports,
        flags=flags,
        test_mode_on=store.setting("schedule_test_mode") == "1",
        test_emails=store.test_emails(),
        excluded=store.exclusions_for(user["email"]),
        customers=catalog.CUSTOMERS,
        company_schedule_setup=store.setting("show_company_schedule_setup", "0") == "1",
    )


@router.post("/api/settings/theme")
async def set_theme(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    body = await request.json()
    value = (body or {}).get("theme")
    if value not in THEME_BODY_CLASS:
        return JSONResponse({"error": "Unknown theme"}, status_code=400)
    request.session["theme"] = value
    return {"ok": True, "theme": value}


@router.post("/api/settings/visibility")
async def set_visibility(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    if not is_privileged(session_user(request)):
        return JSONResponse({"error": "Admin only"}, status_code=403)
    body = await request.json()
    key = (body or {}).get("key") or ""
    if catalog.spec(key) is None:
        return JSONResponse({"error": "Unknown report"}, status_code=400)
    store.set_visibility(key, bool((body or {}).get("enabled")))
    return {"ok": True}


@router.post("/api/settings/flag")
async def set_flag(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    if not is_privileged(session_user(request)):
        return JSONResponse({"error": "Admin only"}, status_code=403)
    body = await request.json()
    key = (body or {}).get("key") or ""
    allowed = {flag[0] for flag in FLAGS}
    if key not in allowed:
        return JSONResponse({"error": "Unknown flag"}, status_code=400)
    store.set_setting(key, "1" if (body or {}).get("enabled") else "0")
    return {"ok": True}


@router.post("/api/settings/test-mode")
async def set_test_mode(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    if not is_privileged(session_user(request)):
        return JSONResponse({"error": "Admin only"}, status_code=403)
    body = await request.json()
    store.set_setting("schedule_test_mode", "1" if (body or {}).get("enabled") else "0")
    return {"ok": True, "emails": store.test_emails()}


@router.post("/api/settings/test-emails")
async def set_test_email_list(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    if not is_privileged(session_user(request)):
        return JSONResponse({"error": "Admin only"}, status_code=403)
    body = await request.json()
    emails = (body or {}).get("emails") or []
    store.set_test_emails([str(addr).strip() for addr in emails if str(addr).strip()])
    return {"ok": True, "emails": store.test_emails()}


@router.post("/api/settings/exclusions")
async def set_exclusions(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    user = session_user(request)
    body = await request.json()
    store.set_exclusions(user["email"], (body or {}).get("accounts") or [])
    return {"ok": True}


@router.get("/admin/users")
def users_page(request: Request):
    blocked = _guard_admin(request)
    if blocked:
        return blocked
    people = []
    for row in store.list_users():
        person = dict(row)
        person["extra_groups"] = store.list_user_groups(person["id"])
        person["report_access"] = store.report_access_map(person["id"])
        people.append(person)
    return page(
        request,
        "admin_users.html",
        active_tab="settings",
        users=people,
        roles=config.ROLES,
        salesmen=catalog.SALESMEN,
        reports=catalog.REPORTS,
    )


@router.post("/admin/users/add")
def users_add(
    request: Request,
    email: str = Form(""),
    display_name: str = Form(""),
    role: str = Form("salesman"),
    sales_group: str = Form(""),
    is_external: str = Form(""),
    csrf: str = Form(""),
):
    blocked = _guard_admin(request)
    if blocked:
        return blocked
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    email = email.strip().lower()
    if not email or role not in config.ROLES:
        flash(request, "Email and a valid role are required.", "error")
        return RedirectResponse("/admin/users", status_code=303)
    if store.get_user(email):
        flash(request, "That email is already on the list. There is no self-register.", "warn")
        return RedirectResponse("/admin/users", status_code=303)
    store.add_user(email, display_name or email, role, 1 if is_external else 0, sales_group)
    flash(request, f"Added {email}.")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/edit")
async def users_edit(request: Request, user_id: int):
    blocked = _guard_admin(request)
    if blocked:
        return blocked
    form = await request.form()
    denied = require_csrf(request, str(form.get("csrf") or ""))
    if denied:
        return denied
    if store.get_user_by_id(user_id) is None:
        flash(request, "Unknown user.", "error")
        return RedirectResponse("/admin/users", status_code=303)
    role = str(form.get("role") or "salesman")
    if role not in config.ROLES:
        flash(request, "Unknown role.", "error")
        return RedirectResponse("/admin/users", status_code=303)
    store.update_user(
        user_id,
        {
            "display_name": str(form.get("display_name") or ""),
            "role": role,
            "sales_group": str(form.get("sales_group") or ""),
            "is_active": 1 if form.get("is_active") else 0,
            "is_external": 1 if form.get("is_external") else 0,
            "can_see_company_views": 1 if form.get("can_see_company_views") else 0,
            "sharepoint_access": 1 if form.get("sharepoint_access") else 0,
            "dashboard_enabled": 1 if form.get("dashboard_enabled") else 0,
            "test_access": 1 if form.get("test_access") else 0,
        },
    )
    extra = [str(part) for part in form.getlist("extra_groups") if str(part)]
    store.set_user_groups(user_id, extra)
    for report in catalog.REPORTS:
        mode = str(form.get(f"report_access_{report['key']}") or "inherit")
        if mode not in {"inherit", "allow", "deny"}:
            mode = "inherit"
        store.set_report_access(user_id, report["key"], mode)
    flash(request, "User saved.")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/delete")
def users_delete(request: Request, user_id: int, csrf: str = Form("")):
    blocked = _guard_admin(request)
    if blocked:
        return blocked
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    actor = session_user(request)
    target = store.get_user_by_id(user_id)
    if target is None:
        flash(request, "Unknown user.", "error")
        return RedirectResponse("/admin/users", status_code=303)
    if actor and target["email"] == actor["email"]:
        flash(request, "You cannot delete your own login.", "warn")
        return RedirectResponse("/admin/users", status_code=303)
    store.delete_user(user_id)
    flash(request, f"Deleted {target['email']}.")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/view-as")
def view_as(request: Request, user_id: int, csrf: str = Form("")):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    blocked = _guard_developer(request, "/admin/users")
    if blocked:
        return blocked
    target = store.get_user_by_id(user_id)
    if target is None or not target["is_active"]:
        flash(request, "That login is missing or disabled.", "error")
        return RedirectResponse("/admin/users", status_code=303)
    if not request.session.get("impersonating"):
        request.session["impersonating"] = session_user(request)
    request.session["user"] = session_from_row(target)
    flash(request, f"Viewing as {target['email']}.")
    return RedirectResponse("/", status_code=303)


@router.post("/impersonate/stop")
def stop_impersonate(request: Request, csrf: str = Form("")):
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    original = request.session.get("impersonating")
    if original:
        request.session["user"] = original
        request.session.pop("impersonating", None)
        flash(request, "Back to your own login.")
    return RedirectResponse("/", status_code=303)


@router.get("/dev/role-picker")
def role_picker(request: Request):
    if config.PRODUCTION:
        return JSONResponse({"error": "Not in production"}, status_code=404)
    blocked = _guard_developer(request)
    if blocked:
        return blocked
    return page(request, "role_picker.html", active_tab="settings", users=store.list_users())


@router.get("/admin/run-log")
def run_log(request: Request):
    blocked = _guard_admin(request)
    if blocked:
        return blocked
    return page(request, "run_log.html", active_tab="settings", jobs=store.list_jobs())


@router.get("/admin/schedule-runs")
def schedule_runs(request: Request):
    blocked = _guard_admin(request)
    if blocked:
        return blocked
    return page(request, "schedule_runs.html", active_tab="settings", runs=store.list_schedule_runs())


@router.get("/dev/db-explorer")
def db_explorer(request: Request):
    blocked = _guard_developer(request)
    if blocked:
        return blocked
    return page(request, "db_explorer.html", active_tab="settings", rows=None, error=None, sql="")


@router.post("/dev/db-explorer")
def db_explorer_run(
    request: Request,
    sql: str = Form(""),
    csrf: str = Form(""),
    confirm_write: str = Form(""),
):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    blocked = _guard_developer(request)
    if blocked:
        return blocked
    stripped = sql.strip().rstrip(";")
    upper = stripped.upper()
    blocked_words = ("DROP ", "ALTER ", "ATTACH ", "CREATE ", "DETACH ")
    if any(word in upper for word in blocked_words):
        return page(
            request,
            "db_explorer.html",
            active_tab="settings",
            rows=None,
            error="DROP/ALTER/ATTACH/CREATE are blocked.",
            sql=sql,
        )
    is_read = upper.startswith("SELECT") or upper.startswith("PRAGMA")
    if upper.startswith("WITH") and not re.search(r"\b(INSERT|UPDATE|DELETE|REPLACE)\b", upper):
        is_read = True
    if not is_read and confirm_write != "1":
        return page(
            request,
            "db_explorer.html",
            active_tab="settings",
            rows=None,
            error="Writes need the Confirm write box checked. Expected a read, or confirm=1.",
            sql=sql,
        )
    try:
        with db() as conn:
            cur = conn.execute(stripped)
            if is_read:
                fetched = [dict(row) for row in cur.fetchall()]
                return page(
                    request,
                    "db_explorer.html",
                    active_tab="settings",
                    rows=fetched[:200],
                    error=None,
                    sql=sql,
                )
            return page(
                request,
                "db_explorer.html",
                active_tab="settings",
                rows=[{"changes": cur.rowcount}],
                error=None,
                sql=sql,
            )
    except sqlite3.Error as err:
        return page(
            request,
            "db_explorer.html",
            active_tab="settings",
            rows=None,
            error=str(err),
            sql=sql,
        )


@router.post("/dev/db-explorer/json")
def db_explorer_json(
    request: Request,
    view_id: int = Form(...),
    params_json: str = Form(""),
    csrf: str = Form(""),
    confirm_write: str = Form(""),
):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    blocked = _guard_developer(request)
    if blocked:
        return blocked
    if confirm_write != "1":
        return page(
            request,
            "db_explorer.html",
            active_tab="settings",
            rows=None,
            error="JSON edits need Confirm write checked.",
            sql="SELECT id, name, params_json FROM views",
        )
    try:
        parsed = json.loads(params_json)
    except json.JSONDecodeError as err:
        return page(
            request,
            "db_explorer.html",
            active_tab="settings",
            rows=None,
            error=f"params_json is not valid JSON: {err}",
            sql="SELECT id, name, params_json FROM views",
        )
    if not isinstance(parsed, dict):
        return page(
            request,
            "db_explorer.html",
            active_tab="settings",
            rows=None,
            error="views params_json must be a JSON object.",
            sql="SELECT id, name, params_json FROM views",
        )
    bad = store.update_view_params(view_id, parsed)
    if bad:
        return page(
            request,
            "db_explorer.html",
            active_tab="settings",
            rows=None,
            error=bad,
            sql="SELECT id, name, params_json FROM views",
        )
    flash(request, f"Updated view {view_id} params_json.")
    return RedirectResponse("/dev/db-explorer", status_code=303)


@router.get("/dev/notif-diagnostic")
def notif_diagnostic(request: Request):
    blocked = _guard_developer(request)
    if blocked:
        return blocked
    return page(request, "notif_diagnostic.html", active_tab="settings", outbox=store.list_outbox())


@router.get("/dev/diagnostics")
def diagnostics(request: Request):
    blocked = _guard_developer(request)
    if blocked:
        return blocked
    salesman = catalog.mock_report("salesman")
    number4 = catalog.mock_report("number_4")
    return page(
        request,
        "diagnostics.html",
        active_tab="settings",
        salesman_tabs=list((salesman["data"]["tabs"] or {}).keys()),
        number4_tabs=list((number4["data"]["tabs"] or {}).keys()),
        blocked="P4.I8 salesman vs SalesGroup is BLOCKED. Testers stay admin until Menny maps live rows.",
    )


@router.post("/api/dev/reporting/{report_id}/run")
async def reporting_api_run(request: Request, report_id: str):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    user = session_user(request)
    if not is_privileged(user):
        return JSONResponse({"error": "Developer only"}, status_code=403)
    if not config.reporting_api_key():
        return JSONResponse(
            {
                "error": "REPORTING_API_KEY is not set. This preview uses catalog mock JSON instead of the office doorway.",
                "mock": True,
                "report_id": report_id,
            },
            status_code=501,
        )
    return JSONResponse(
        {"error": "Live Reporting API calls are not enabled on this dummy site."},
        status_code=501,
    )
