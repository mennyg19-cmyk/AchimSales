"""Personal and company schedules on mock data. No Graph, no Automation."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

import catalog
import store
from deps import flash, is_privileged, login_redirect, page, session_user
from routes_reports import _build_payload

router = APIRouter()


def _deliver(schedule: dict, user_email: str) -> str:
    spec = catalog.spec(schedule["report_key"])
    if spec is None:
        store.mark_schedule_run(schedule["id"], "failure", "Unknown report on the saved view.")
        return "failure"
    payload = _build_payload(schedule["report_key"], {"email": user_email, "role": "admin", "sales_group": ""}, schedule.get("params") or {})
    store.save_job(schedule["report_key"], schedule["view_name"], payload)
    recipients = schedule["recipients"]
    if store.setting("schedule_test_mode") == "1":
        recipients = ", ".join(store.test_emails())
    store.add_outbox(
        recipients,
        f"[MOCK] {schedule['view_name']}",
        "Scheduled dummy workbook. Graph is not wired on this preview.",
    )
    store.mark_schedule_run(schedule["id"], "success", f"Mock mail queued to {recipients}")
    return "success"


@router.get("/schedules")
def schedules_page(request: Request):
    user = session_user(request)
    if not user:
        return login_redirect()
    views = store.list_views(user["email"], is_privileged(user) or user.get("can_see_company_views"))
    named = [view for view in views if view["name"] and view["name"] != "Default"]
    rows = store.list_schedules()
    if not is_privileged(user):
        own = [row for row in rows if row["owner_email"] == user["email"]]
        shared = [row for row in rows if row["owner_email"] != user["email"]]
        rows = own + shared if user.get("role") == "manager" else own
    return page(
        request,
        "schedules.html",
        active_tab="schedules",
        schedules=rows,
        views=named,
        test_mode_on=store.setting("schedule_test_mode") == "1",
        test_emails=store.test_emails(),
        recent_runs=store.list_schedule_runs()[:20],
        preselect_view=request.query_params.get("view") or "",
    )


@router.post("/schedules/add")
def schedules_add(
    request: Request,
    view_id: int = Form(...),
    freq: str = Form("daily"),
    run_time: str = Form("08:00"),
    recipients: str = Form(""),
):
    user = session_user(request)
    if not user:
        return login_redirect()
    view = store.get_view(view_id)
    if view is None:
        flash(request, "Save a named view on a report first.", "warn")
        return RedirectResponse("/schedules", status_code=303)
    if freq not in {"daily", "weekly", "monthly"}:
        flash(request, "Frequency must be daily, weekly, or monthly.", "error")
        return RedirectResponse("/schedules", status_code=303)
    store.add_schedule(view_id, user["email"], freq, run_time, recipients or user["email"])
    flash(request, "Schedule saved. Run now sends mock mail to the outbox.")
    return RedirectResponse("/schedules", status_code=303)


@router.post("/schedules/{schedule_id}/toggle")
def schedules_toggle(request: Request, schedule_id: int):
    user = session_user(request)
    if not user:
        return login_redirect()
    store.toggle_schedule(schedule_id)
    return RedirectResponse("/schedules", status_code=303)


@router.post("/schedules/{schedule_id}/delete")
def schedules_delete(request: Request, schedule_id: int):
    user = session_user(request)
    if not user:
        return login_redirect()
    row = store.get_schedule(schedule_id)
    if row and row["owner_email"] != user["email"] and not is_privileged(user):
        flash(request, "You can only delete your own schedules.", "warn")
        return RedirectResponse("/schedules", status_code=303)
    store.delete_schedule(schedule_id)
    flash(request, "Schedule deleted.")
    return RedirectResponse("/schedules", status_code=303)


@router.post("/schedules/{schedule_id}/run-now")
def schedules_run_now(request: Request, schedule_id: int):
    user = session_user(request)
    if not user:
        return login_redirect()
    row = store.get_schedule(schedule_id)
    if row is None:
        flash(request, "Unknown schedule.", "error")
        return RedirectResponse("/schedules", status_code=303)
    shared = row["owner_email"] != user["email"]
    if shared and user.get("role") == "manager" and not is_privileged(user):
        pass  # Q9: view-only managers Send now on shared only
    elif shared and not is_privileged(user) and user.get("role") != "manager":
        flash(request, "You can only run your own schedules.", "warn")
        return RedirectResponse("/schedules", status_code=303)
    _deliver(row, user["email"])
    flash(request, "Mock send finished. Check Settings → Developer → Notification diagnostic.")
    return RedirectResponse("/schedules", status_code=303)


@router.get("/schedules/{schedule_id}/history")
def schedule_history(request: Request, schedule_id: int):
    user = session_user(request)
    if not user:
        return login_redirect()
    row = store.get_schedule(schedule_id)
    if row is None:
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


@router.get("/settings/company-schedules")
def company_schedules(request: Request):
    user = session_user(request)
    if not user:
        return login_redirect()
    if store.setting("show_company_schedule_setup", "0") != "1" and not is_privileged(user):
        flash(request, "Company schedule setup is hidden.", "warn")
        return RedirectResponse("/settings", status_code=302)
    rows = [row for row in store.list_schedules() if row.get("view_name")]
    return page(request, "company_schedules.html", active_tab="settings", schedules=rows)


@router.get("/master-schedules")
def master_schedules(request: Request):
    user = session_user(request)
    if not user:
        return login_redirect()
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


@router.post("/api/schedules/clear-stuck")
def clear_stuck(request: Request):
    user = session_user(request)
    if not user:
        return JSONResponse({"error": "Sign in required"}, status_code=401)
    if not is_privileged(user):
        return JSONResponse({"error": "Admin only"}, status_code=403)
    count = store.abandon_orphan_runs()
    return {"ok": True, "cleared": count}
