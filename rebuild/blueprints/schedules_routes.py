"""The pages for setting up repeating, emailed report sends."""

# === What's in this file ===
# Lets a signed-in person schedule a report to email itself (and anyone they
# list) on a cadence, and lets an admin set up "master" schedules that split one
# report by salesman and mail each salesman's slice to the people mapped to it.
# Routes are thin: they read the form, hand the cadence to the scheduling module
# to clean/validate, and store it. A history page shows what actually went out.
#
# my_schedules() -- a person's own schedules + the create form
# create_schedule() -- save a new self-schedule
# admin_schedules() / create_master_schedule() -- the admin master schedules page
# toggle_schedule() / delete_schedule() -- pause/resume or remove one (owner or admin)
# run_now() -- queue a one-off run of a schedule right now (ignores the Shabbos skip)
# dismiss_notification() -- hide an in-app message
# schedule_history() -- recent scheduled sends (own, or everyone for an admin)

from __future__ import annotations

import re
import uuid

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..app import get_config, get_db
from ..auth.decorators import require_login, require_privileged
from ..auth.session import current_principal
from ..data.connection import normalize_email
from ..data.repositories.jobs import JobRepository, QueueFull
from ..data.repositories.notifications import NotificationsRepository
from ..data.repositories.run_log import RunLogRepository
from ..data.repositories.schedules import KIND_MASTER, KIND_SELF, SchedulesRepository
from ..data.repositories.user_scope import UserScopeRepository
from ..jobs.types import JOB_SCHEDULE_RUN
from ..reporting.authz import resolve_access
from ..reports.config_loader import ConfigLoader, ReportNotFound, ReportNotRunnable
from ..scheduling import cadence as C

schedules_bp = Blueprint("schedules", __name__)


def _schedules() -> SchedulesRepository:
    return SchedulesRepository(get_db())


def _reports_with_tabs() -> list[dict]:
    """Active reports the current person may schedule, plus their tab list."""
    loader = ConfigLoader(get_db())
    principal = current_principal()
    scope = UserScopeRepository(get_db())
    reports = []
    for report in loader.list_active():
        access = resolve_access(principal, report["report_key"], scope)
        if not access.allowed:
            continue
        try:
            tabs = loader.load(report["report_key"]).tabs
        except ReportNotFound:
            tabs = []
        reports.append({
            "report_key": report["report_key"],
            "title": report["title"],
            "tabs": [{"key": t["tab_key"], "label": t["label"]} for t in tabs],
        })
    return reports


def _save_schedule(report_key: str, kind: str, salesmen: list[str], redirect_endpoint: str, success_msg: str):
    """Shared tail of both create routes: validate the report + cadence, store the
    schedule, and redirect with a flash. The routes do their own kind-specific
    pre-checks (a self schedule checks the person's access; a master checks the
    salesman list) before calling this."""
    db = get_db()
    try:
        ConfigLoader(db).load_runnable(report_key)
    except (ReportNotFound, ReportNotRunnable):
        flash("That report isn't available to schedule.", "error")
        return redirect(url_for(redirect_endpoint))
    try:
        cadence = _parse_cadence(request.form)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for(redirect_endpoint))

    _schedules().create(
        owner_email=current_principal().email,
        report_key=report_key,
        title=(request.form.get("title") or report_key).strip(),
        kind=kind,
        filters={"period": (request.form.get("period") or "ytd").strip()},
        cadence=cadence,
        recipients=_parse_recipients(request.form.get("recipients", "")),
        salesmen=salesmen,
        tab_key=(request.form.get("tab_key") or "").strip() or None,
        skip_sabbath=request.form.get("skip_sabbath") == "on",
    )
    flash(success_msg, "success")
    return redirect(url_for(redirect_endpoint))


def _parse_recipients(recipient_text: str) -> list[str]:
    return [r for r in re.split(r"[,\s]+", recipient_text or "") if r]


def _parse_cadence(form) -> dict:
    cadence_values = {
        "freq": form.get("freq", ""),
        "time": form.get("time", "08:00"),
        "weekdays": [int(d) for d in form.getlist("weekdays") if d.isdigit()],
        "monthday": form.get("monthday", "1"),
    }
    return C.normalize(cadence_values)  # raises ValueError on bad input


def _can_manage(schedule) -> bool:
    principal = current_principal()
    if principal is None:
        return False
    if principal.is_privileged:
        return True
    # A master schedule mails other people, so only a current admin may touch it,
    # never the stored owner alone (they might no longer be privileged).
    if schedule.kind == KIND_MASTER:
        return False
    return schedule.owner_email == normalize_email(principal.email)


@schedules_bp.get("/schedules")
@require_login
def my_schedules():
    principal = current_principal()
    schedules = _schedules().list_for_owner(principal.email)
    return render_template(
        "schedules.html",
        principal=principal,
        schedules=schedules,
        reports=_reports_with_tabs(),
        describe=C.describe,
    )


@schedules_bp.post("/schedules")
@require_login
def create_schedule():
    principal = current_principal()
    db = get_db()
    report_key = (request.form.get("report_key") or "").strip()

    access = resolve_access(principal, report_key, UserScopeRepository(db))
    if not access.allowed:
        flash("You don't have access to that report.", "error")
        return redirect(url_for("schedules.my_schedules"))
    return _save_schedule(report_key, KIND_SELF, [], "schedules.my_schedules", "Schedule saved.")


@schedules_bp.get("/admin/schedules")
@require_privileged
def admin_schedules():
    masters = [s for s in _schedules().list_all() if s.kind == KIND_MASTER]
    return render_template(
        "master_schedules.html",
        principal=current_principal(),
        schedules=masters,
        reports=_reports_with_tabs(),
        describe=C.describe,
    )


@schedules_bp.post("/admin/schedules")
@require_privileged
def create_master_schedule():
    report_key = (request.form.get("report_key") or "").strip()
    salesmen = [n for n in re.split(r"[,\s]+", request.form.get("salesmen", "")) if n]
    if not salesmen:
        flash("List at least one salesman number for a master schedule.", "error")
        return redirect(url_for("schedules.admin_schedules"))
    return _save_schedule(report_key, KIND_MASTER, salesmen, "schedules.admin_schedules", "Master schedule saved.")


@schedules_bp.post("/schedules/<schedule_id>/toggle")
@require_login
def toggle_schedule(schedule_id: str):
    repo = _schedules()
    schedule = repo.get(schedule_id)
    if schedule is None:
        abort(404)
    if not _can_manage(schedule):
        abort(403)
    repo.update(
        schedule_id,
        title=schedule.title, filters=schedule.filters, cadence=schedule.cadence,
        recipients=schedule.recipients, salesmen=schedule.salesmen, tab_key=schedule.tab_key,
        skip_sabbath=schedule.skip_sabbath, enabled=not schedule.enabled,
    )
    return redirect(_back_to(schedule))


@schedules_bp.post("/schedules/<schedule_id>/delete")
@require_login
def delete_schedule(schedule_id: str):
    repo = _schedules()
    schedule = repo.get(schedule_id)
    if schedule is None:
        abort(404)
    if not _can_manage(schedule):
        abort(403)
    repo.delete(schedule_id)
    flash("Schedule deleted.", "success")
    return redirect(_back_to(schedule))


@schedules_bp.post("/schedules/<schedule_id>/run-now")
@require_login
def run_now(schedule_id: str):
    repo = _schedules()
    schedule = repo.get(schedule_id)
    if schedule is None:
        abort(404)
    if not _can_manage(schedule):
        abort(403)

    config = get_config()
    jobs = JobRepository(get_db(), config.job_queue_max, config.job_stale_seconds)
    try:
        jobs.enqueue(
            JOB_SCHEDULE_RUN,
            report_key=schedule.report_key,
            # A unique key per press so a manual run is never deduped against the
            # scheduled slot or an earlier press -- the person asked for it now.
            cache_key=f"schedule:{schedule_id}:manual:{uuid.uuid4().hex}",
            params={"schedule_id": schedule_id, "manual": True},
            requested_by=schedule.owner_email,
        )
    except QueueFull:
        flash("The system is busy right now. Try again in a minute.", "error")
        return redirect(_back_to(schedule))

    # If this came from a "your schedule failed" message, clear that message.
    NotificationsRepository(get_db()).dismiss_for_schedule(current_principal().email, schedule_id)
    flash("Running now. The email goes out as soon as it's built.", "success")
    return redirect(_back_to(schedule))


@schedules_bp.post("/notifications/<note_id>/dismiss")
@require_login
def dismiss_notification(note_id: str):
    repo = NotificationsRepository(get_db())
    note = repo.get(note_id)
    if note is None:
        abort(404)
    if note["user_email"] != normalize_email(current_principal().email):
        abort(403)
    repo.dismiss(note_id)
    return redirect(url_for("reporting.reports_home"))


@schedules_bp.get("/schedules/history")
@require_login
def schedule_history():
    principal = current_principal()
    only_user = None if principal.is_privileged else principal.email
    entries = RunLogRepository(get_db()).recent_action("schedule.run", 200, user_email=only_user)
    return render_template("schedule_history.html", principal=principal, entries=entries)


def _back_to(schedule) -> str:
    if schedule.kind == KIND_MASTER:
        return url_for("schedules.admin_schedules")
    return url_for("schedules.my_schedules")
