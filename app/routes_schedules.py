"""Personal and company schedules. Graph mail when secrets exist; clock ticks every minute."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

import cadence
import catalog
import config
import store
from deliver import deliver_schedule
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

router = APIRouter()


def _owner_label(email: str, users: dict[str, dict]) -> tuple[str, str]:
    key = (email or "").lower()
    row = users.get(key)
    if row:
        return (row.get("display_name") or row["email"], row["email"])
    return (email or "Unknown", email or "")


def _decorate_schedule(row: dict, users: dict[str, dict]) -> dict:
    out = dict(row)
    spec = catalog.spec(out.get("report_key") or "")
    out["report_title"] = spec["title"] if spec else (out.get("report_key") or "")
    out["owner_name"], out["owner_email"] = _owner_label(out.get("owner_email") or "", users)
    out["cadence"] = cadence.describe(out)
    out["folder"] = out.get("sharepoint_folder") or out.get("onedrive_folder") or ""
    return out


def _group_schedule_rows(items: list[dict], privileged: bool) -> list[dict]:
    if not privileged:
        return [{"owner_name": "", "owner_email": "", "schedules": items}]
    groups: list[dict] = []
    by_owner: dict[str, list] = {}
    order: list[str] = []
    for row in items:
        oid = (row.get("owner_email") or "").lower()
        if oid not in by_owner:
            by_owner[oid] = []
            order.append(oid)
        by_owner[oid].append(row)
    for oid in order:
        rows = by_owner[oid]
        groups.append({
            "owner_name": rows[0]["owner_name"],
            "owner_email": rows[0]["owner_email"],
            "schedules": rows,
        })
    return groups


@router.get("/schedules")
def schedules_page(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    user = session_user(request)
    views = store.list_views(user["email"], is_privileged(user) or user.get("can_see_company_views"))
    named = [view for view in views if view["name"] and view["name"] != "Default"]
    named = [view for view in named if can_use_view_for_schedule(user, view)]
    users = {row["email"].lower(): row for row in store.list_users()}
    rows = [
        _decorate_schedule(row, users)
        for row in store.list_schedules()
        if can_read_schedule(user, row)
    ]
    rows.sort(key=lambda row: (
        (row.get("owner_name") or "").lower(),
        (row.get("report_title") or "").lower(),
        (row.get("view_name") or "").lower(),
    ))
    recent = store.list_schedule_runs()[:20]
    if not is_privileged(user):
        recent = [run for run in recent if can_read_schedule(user, run)]
    return page(
        request,
        "schedules.html",
        active_tab="schedules",
        schedules=rows,
        schedule_groups=_group_schedule_rows(rows, is_privileged(user)),
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
    onedrive_folder: str = Form(""),
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
        flash(request, "You can only schedule your own named views.", "warn")
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
        onedrive_folder=onedrive_folder if user.get("sharepoint_access") or is_privileged(user) else "",
    )
    flash(request, "Schedule saved. Run now sends mail (Graph when secrets are set, otherwise the outbox).")
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
    if row is None:
        flash(request, "Unknown schedule.", "error")
        return RedirectResponse("/schedules", status_code=303)
    if row["owner_email"] != user["email"] and not is_privileged(user):
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
    status = deliver_schedule(row, user)
    if status == "success":
        if config.graph_mail_configured():
            flash(request, "Send finished. Check the inbox (and Settings → Developer → Notification diagnostic).")
        else:
            flash(request, "Send finished. Graph secrets are not set, so the copy is in Settings → Developer → Notification diagnostic.")
    else:
        flash(request, "Send failed. Open the run log for the error.", "error")
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
    runs = store.list_schedule_runs_for(schedule_id)
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
        {"time": when, "step": "Build", "detail": "Workbook from the saved view."},
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
    runs = store.list_schedule_runs_for(schedule_id)
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
        onedrive_folder=row.get("onedrive_folder") or "",
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
