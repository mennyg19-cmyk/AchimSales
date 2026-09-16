"""Settings hub, Users & access, visibility, history."""

from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

import catalog
import config
import store
from import_precious import import_precious, summarize
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

FLAGS = ()


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
    )


MAX_PRECIOUS_BYTES = 80 * 1024 * 1024


@router.post("/settings/import-precious")
async def import_precious_upload(
    request: Request,
    file: UploadFile = File(...),
    csrf: str = Form(""),
):
    blocked = _guard_admin(request)
    if blocked:
        return blocked
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    raw = await file.read()
    if len(raw) > MAX_PRECIOUS_BYTES:
        flash(request, "That file is larger than 80 MB.", "error")
        return RedirectResponse("/settings", status_code=303)
    if not raw.startswith(b"SQLite format 3"):
        flash(request, "That is not a sqlite precious.db file.", "error")
        return RedirectResponse("/settings", status_code=303)
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    try:
        tmp.write(raw)
        tmp.close()
        keep = config.db_path().parent / "last-precious.db"
        keep.write_bytes(raw)
        result = import_precious(Path(tmp.name), config.db_path())
        flash(request, summarize(result))
    except ValueError as err:
        flash(request, str(err), "error")
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    return RedirectResponse("/settings", status_code=303)


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
    user = session_user(request)
    if user and user.get("id"):
        store.set_user_theme(int(user["id"]), value)
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
