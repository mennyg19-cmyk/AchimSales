"""Personal and company schedules on mock data. No Graph, no Automation."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

import catalog
import store
from deps import (
    can_read_schedule,
    can_use_view_for_schedule,
    flash,
    is_privileged,
    need_login,
    page,
    require_csrf,
    session_user,
)
from routes_reports import _build_payload

router = APIRouter()


def _deliver(schedule: dict, user: dict) -> str:
    spec = catalog.spec(schedule["report_key"])
    if spec is None:
        store.mark_schedule_run(schedule["id"], "failure", "Unknown report on the saved view.")
        return "failure"
    payload = _build_payload(schedule["report_key"], user, schedule.get("params") or {})
    store.save_job(schedule["report_key"], schedule["view_name"], payload, owner_email=user["email"])
    recipients = store.mail_recipients(schedule["recipients"])
    extra = []
    if schedule.get("cc"):
        extra.append(f"CC {schedule['cc']}")
    if schedule.get("bcc"):
        extra.append(f"BCC {schedule['bcc']}")
    if schedule.get("filename"):
        extra.append(f"file {schedule['filename']}")
    if schedule.get("sharepoint_folder"):
        extra.append(f"SharePoint {schedule['sharepoint_folder']}")
    detail = "Scheduled dummy workbook. Graph is not wired on this preview."
    if extra:
        detail += " " + "; ".join(extra)
    store.add_outbox(
        recipients,
        schedule.get("subject") or f"[MOCK] {schedule['view_name']}",
        detail,
    )
    store.mark_schedule_run(schedule["id"], "success", f"Mock mail queued to {recipients}")
    return "success"


@router.get("/schedules")
def schedules_page(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    views = store.list_views(user["email"], is_privileged(user) or user.get("can_see_company_views"))
    named = [view for view in views if view["name"] and view["name"] != "Default"]
    named = [view for view in named if can_use_view_for_schedule(user, view)]
    rows = store.list_schedules()
    if not is_privileged(user):
        own = [row for row in rows if row["owner_email"] == user["email"]]
        if user.get("role") == "manager":
            shared = [
                row
                for row in rows
                if row["owner_email"] != user["email"] and row.get("view_kind") == "company"
            ]
            rows = own + shared
        else:
            rows = own
    recent = store.list_schedule_runs()[:20]
    if not is_privileged(user):
        recent = [run for run in recent if can_read_schedule(user, run)]
    return page(
        request,
        "schedules.html",
        active_tab="schedules",
        schedules=rows,
        views=named,
        test_mode_on=store.setting("schedule_test_mode") == "1",
        test_emails=store.test_emails(),
        recent_runs=recent,
        preselect_view=request.query_params.get("view") or "",
    )


@router.post("/schedules/add")
def schedules_add(
    request: Request,
    view_id: int = Form(...),
    freq: str = Form("daily"),
    run_time: str = Form("08:00"),
    recipients: str = Form(""),
    weekdays: list[str] = Form(default=[]),
    monthday: str = Form(""),
    cc: str = Form(""),
    bcc: str = Form(""),
    subject: str = Form(""),
    filename: str = Form(""),
    sharepoint_folder: str = Form(""),
    csrf: str = Form(""),
):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    user = session_user(request)
    view = store.get_view(view_id)
    if view is None:
        flash(request, "Save a named view on a report first.", "warn")
        return RedirectResponse("/schedules", status_code=303)
    if not can_use_view_for_schedule(user, view):
        flash(request, "You can only schedule your own views or a company view.", "warn")
        return RedirectResponse("/schedules", status_code=303)
    if freq not in {"daily", "weekly", "monthly"}:
        flash(request, "Frequency must be daily, weekly, or monthly.", "error")
        return RedirectResponse("/schedules", status_code=303)
    day = int(monthday) if monthday.strip().isdigit() else None
    store.add_schedule(
        view_id,
        user["email"],
        freq,
        run_time,
        recipients or user["email"],
        weekdays=",".join(weekdays),
        monthday=day,
        cc=cc if is_privileged(user) else "",
        bcc=bcc if is_privileged(user) else "",
        subject=subject,
        filename=filename,
        sharepoint_folder=sharepoint_folder if user.get("sharepoint_access") or is_privileged(user) else "",
    )
    flash(request, "Schedule saved. Run now sends mock mail to the outbox.")
    return RedirectResponse("/schedules", status_code=303)


@router.post("/schedules/{schedule_id}/toggle")
def schedules_toggle(request: Request, schedule_id: int, csrf: str = Form("")):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    user = session_user(request)
    row = store.get_schedule(schedule_id)
    if row is None:
        flash(request, "Unknown schedule.", "error")
        return RedirectResponse("/schedules", status_code=303)
    if row["owner_email"] != user["email"] and not is_privileged(user):
        flash(request, "You can only pause your own schedules.", "warn")
        return RedirectResponse("/schedules", status_code=303)
    store.toggle_schedule(schedule_id)
    return RedirectResponse("/schedules", status_code=303)


@router.post("/schedules/{schedule_id}/delete")
def schedules_delete(request: Request, schedule_id: int, csrf: str = Form("")):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    user = session_user(request)
    row = store.get_schedule(schedule_id)
    if row and row["owner_email"] != user["email"] and not is_privileged(user):
        flash(request, "You can only delete your own schedules.", "warn")
        return RedirectResponse("/schedules", status_code=303)
    store.delete_schedule(schedule_id)
    flash(request, "Schedule deleted.")
    return RedirectResponse("/schedules", status_code=303)


@router.post("/schedules/{schedule_id}/run-now")
def schedules_run_now(request: Request, schedule_id: int, csrf: str = Form("")):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    user = session_user(request)
    row = store.get_schedule(schedule_id)
    if row is None or not can_read_schedule(user, row):
        flash(request, "You can only run a schedule you can see.", "warn")
        return RedirectResponse("/schedules", status_code=303)
    _deliver(row, user)
    flash(request, "Mock send finished. Check Settings → Developer → Notification diagnostic.")
    return RedirectResponse("/schedules", status_code=303)


@router.get("/schedules/{schedule_id}/history")
def schedule_history(request: Request, schedule_id: int):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    row = store.get_schedule(schedule_id)
    if row is None or not can_read_schedule(user, row):
        flash(request, "Unknown schedule.", "error")
        return RedirectResponse("/schedules", status_code=302)
    runs = [item for item in store.list_schedule_runs() if item["schedule_id"] == schedule_id]
    return page(
        request,
        "schedule_history.html",
        active_tab="schedules",
        schedule=row,
        runs=runs,
    )


@router.get("/schedules/runs/{run_id}")
def schedule_run_log(request: Request, run_id: int):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    run = store.get_schedule_run(run_id)
    if run is None or not can_read_schedule(user, run):
        flash(request, "Unknown schedule run.", "error")
        return RedirectResponse("/schedules", status_code=302)
    when = run["started_at"]
    steps = [
        {"time": when, "step": "Start", "detail": f"{run['view_name']} ({run['report_key']})"},
        {"time": when, "step": "Build", "detail": "Mock workbook from the saved view. No office API."},
        {"time": when, "step": "Deliver", "detail": run["message"] or run["status"]},
    ]
    return page(
        request,
        "schedule_run.html",
        active_tab="schedules",
        run=run,
        steps=steps,
    )


@router.get("/settings/company-schedules")
def company_schedules(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    if store.setting("show_company_schedule_setup", "0") != "1" and not is_privileged(user):
        flash(request, "Company schedule setup is hidden.", "warn")
        return RedirectResponse("/settings", status_code=302)
    rows = [row for row in store.list_schedules() if row.get("view_name")]
    return page(request, "company_schedules.html", active_tab="settings", schedules=rows)


@router.get("/master-schedules")
def master_schedules(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    if not is_privileged(user):
        flash(request, "Master schedules are admin-only on this preview.", "warn")
        return RedirectResponse("/schedules", status_code=302)
    return page(
        request,
        "company_schedules.html",
        active_tab="settings",
        schedules=store.list_schedules(),
        master=True,
    )


@router.get("/master-schedules/{schedule_id}/history")
def master_schedule_history(request: Request, schedule_id: int):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    if not is_privileged(user):
        flash(request, "Master schedules are admin-only on this preview.", "warn")
        return RedirectResponse("/schedules", status_code=302)
    row = store.get_schedule(schedule_id)
    if row is None:
        flash(request, "Unknown schedule.", "error")
        return RedirectResponse("/master-schedules", status_code=302)
    runs = [item for item in store.list_schedule_runs() if item["schedule_id"] == schedule_id]
    return page(
        request,
        "schedule_history.html",
        active_tab="settings",
        schedule=row,
        runs=runs,
        master=True,
    )


@router.post("/schedules/{schedule_id}/copy")
def schedules_copy(request: Request, schedule_id: int, csrf: str = Form("")):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    user = session_user(request)
    row = store.get_schedule(schedule_id)
    if row is None or not can_read_schedule(user, row):
        flash(request, "You can only copy a schedule you can see.", "warn")
        return RedirectResponse("/schedules", status_code=303)
    store.add_schedule(
        row["view_id"],
        user["email"],
        row["freq"],
        row["run_time"],
        user["email"],
        weekdays=row.get("weekdays") or "",
        monthday=row.get("monthday"),
        cc=row.get("cc") or "",
        bcc=row.get("bcc") or "",
        subject=row.get("subject") or "",
        filename=row.get("filename") or "",
        sharepoint_folder=row.get("sharepoint_folder") or "",
    )
    flash(request, "Copied. Recipients set to you — edit if needed.")
    return RedirectResponse("/schedules", status_code=303)


@router.post("/api/schedules/clear-stuck")
def clear_stuck(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    user = session_user(request)
    if not is_privileged(user):
        return JSONResponse({"error": "Admin only"}, status_code=403)
    count = store.abandon_orphan_runs()
    return {"ok": True, "cleared": count}
