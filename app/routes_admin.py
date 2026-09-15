"""Settings hub, Users & access, visibility, history, developer tools."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

import catalog
import config
import store
from db import db
from deps import (
    flash,
    is_admin,
    is_privileged,
    login_redirect,
    page,
    session_from_row,
    session_user,
)

router = APIRouter()

FLAGS = (
    ("show_company_schedule_setup", "Show the Company schedules setup page (runs still happen if this is off)."),
)


def _guard_admin(request: Request):
    user = session_user(request)
    if not user:
        return login_redirect()
    if not is_admin(user):
        flash(request, "Admin only.", "warn")
        return RedirectResponse("/settings", status_code=302)
    return None


@router.get("/settings")
def settings_page(request: Request):
    user = session_user(request)
    if not user:
        return login_redirect()
    vis = store.visibility_map()
    reports = [
        {**item, "enabled": vis.get(item["key"], True)}
        for item in catalog.REPORTS
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
    if not session_user(request):
        return JSONResponse({"error": "Sign in required"}, status_code=401)
    body = await request.json()
    value = (body or {}).get("theme")
    if value not in {"light", "dark", "monochrome", "monochrome_dark"}:
        return JSONResponse({"error": "Unknown theme"}, status_code=400)
    request.session["theme"] = value
    return {"ok": True, "theme": value}


@router.post("/api/settings/visibility")
async def set_visibility(request: Request):
    user = session_user(request)
    if not user:
        return JSONResponse({"error": "Sign in required"}, status_code=401)
    if not is_admin(user):
        return JSONResponse({"error": "Admin only"}, status_code=403)
    body = await request.json()
    key = (body or {}).get("key") or ""
    if catalog.spec(key) is None:
        return JSONResponse({"error": "Unknown report"}, status_code=400)
    store.set_visibility(key, bool((body or {}).get("enabled")))
    return {"ok": True}


@router.post("/api/settings/flag")
async def set_flag(request: Request):
    user = session_user(request)
    if not user:
        return JSONResponse({"error": "Sign in required"}, status_code=401)
    if not is_admin(user):
        return JSONResponse({"error": "Admin only"}, status_code=403)
    body = await request.json()
    key = (body or {}).get("key") or ""
    allowed = {item[0] for item in FLAGS}
    if key not in allowed:
        return JSONResponse({"error": "Unknown flag"}, status_code=400)
    store.set_setting(key, "1" if (body or {}).get("enabled") else "0")
    return {"ok": True}


@router.post("/api/settings/test-mode")
async def set_test_mode(request: Request):
    user = session_user(request)
    if not user:
        return JSONResponse({"error": "Sign in required"}, status_code=401)
    if not is_admin(user):
        return JSONResponse({"error": "Admin only"}, status_code=403)
    body = await request.json()
    store.set_setting("schedule_test_mode", "1" if (body or {}).get("enabled") else "0")
    return {"ok": True, "emails": store.test_emails()}


@router.post("/api/settings/test-emails")
async def set_test_email_list(request: Request):
    user = session_user(request)
    if not user:
        return JSONResponse({"error": "Sign in required"}, status_code=401)
    if not is_admin(user):
        return JSONResponse({"error": "Admin only"}, status_code=403)
    body = await request.json()
    emails = (body or {}).get("emails") or []
    store.set_test_emails([str(item).strip() for item in emails if str(item).strip()])
    return {"ok": True, "emails": store.test_emails()}


@router.post("/api/settings/exclusions")
async def set_exclusions(request: Request):
    user = session_user(request)
    if not user:
        return JSONResponse({"error": "Sign in required"}, status_code=401)
    body = await request.json()
    store.set_exclusions(user["email"], (body or {}).get("accounts") or [])
    return {"ok": True}


@router.get("/admin/users")
def users_page(request: Request):
    blocked = _guard_admin(request)
    if blocked:
        return blocked
    return page(
        request,
        "admin_users.html",
        active_tab="settings",
        users=store.list_users(),
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
):
    blocked = _guard_admin(request)
    if blocked:
        return blocked
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
def users_edit(
    request: Request,
    user_id: int,
    display_name: str = Form(""),
    role: str = Form("salesman"),
    sales_group: str = Form(""),
    is_active: str = Form(""),
    is_external: str = Form(""),
    can_see_company_views: str = Form(""),
    sharepoint_access: str = Form(""),
):
    blocked = _guard_admin(request)
    if blocked:
        return blocked
    if role not in config.ROLES:
        flash(request, "Unknown role.", "error")
        return RedirectResponse("/admin/users", status_code=303)
    store.update_user(
        user_id,
        {
            "display_name": display_name,
            "role": role,
            "sales_group": sales_group,
            "is_active": 1 if is_active else 0,
            "is_external": 1 if is_external else 0,
            "can_see_company_views": 1 if can_see_company_views else 0,
            "sharepoint_access": 1 if sharepoint_access else 0,
        },
    )
    extra = request.query_params.get("groups") or ""
    if extra:
        store.set_user_groups(user_id, [part for part in extra.split(",") if part])
    flash(request, "User saved.")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/view-as")
def view_as(request: Request, user_id: int):
    user = session_user(request)
    if not user:
        return login_redirect()
    if user.get("role") != "developer" and not is_privileged(user):
        flash(request, "View as is for developers.", "warn")
        return RedirectResponse("/admin/users", status_code=302)
    target = store.get_user_by_id(user_id)
    if target is None or not target["is_active"]:
        flash(request, "That login is missing or disabled.", "error")
        return RedirectResponse("/admin/users", status_code=302)
    if not request.session.get("impersonating"):
        request.session["impersonating"] = user
    request.session["user"] = session_from_row(target)
    flash(request, f"Viewing as {target['email']}.")
    return RedirectResponse("/", status_code=303)


@router.post("/impersonate/stop")
def stop_impersonate(request: Request):
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
    user = session_user(request)
    if not user:
        return login_redirect()
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
    user = session_user(request)
    if not user:
        return login_redirect()
    if user.get("role") != "developer" and not is_privileged(user):
        flash(request, "Developer only.", "warn")
        return RedirectResponse("/settings", status_code=302)
    return page(request, "db_explorer.html", active_tab="settings", rows=None, error=None, sql="")


@router.post("/dev/db-explorer")
def db_explorer_run(request: Request, sql: str = Form("")):
    user = session_user(request)
    if not user:
        return login_redirect()
    if user.get("role") != "developer" and not is_privileged(user):
        flash(request, "Developer only.", "warn")
        return RedirectResponse("/settings", status_code=302)
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
    try:
        with db() as conn:
            cur = conn.execute(stripped)
            if upper.startswith("SELECT") or upper.startswith("PRAGMA") or upper.startswith("WITH"):
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


@router.get("/dev/notif-diagnostic")
def notif_diagnostic(request: Request):
    user = session_user(request)
    if not user:
        return login_redirect()
    if user.get("role") != "developer" and not is_privileged(user):
        flash(request, "Developer only.", "warn")
        return RedirectResponse("/settings", status_code=302)
    return page(request, "notif_diagnostic.html", active_tab="settings", outbox=store.list_outbox())
