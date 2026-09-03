"""Schedules: personal deliveries from saved views + company (Settings) schedules.

Personal schedules are 3-step (named view → when → where). Company (master)
schedules live under Settings for admins and developers only.
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, url_for

from report_engine import registry
from report_engine.lib import salesman_key
from web.auth.decorators import require_login
from web.auth.principal import ROLE_MANAGER
from web.auth.session import current_principal
from web.delivery.email import split_recipients
from web.delivery.email_template import sanitize_html
from web.delivery.filename_template import DEFAULT_FILENAME_TEMPLATE
from web.data.repositories.report_defaults import (
    DEFAULT_VIEW_NAME,
    ReportDefaultRepository,
    normalize_view_name,
    view_and_layout_for_create,
    view_and_layout_for_update,
)
from web.data.repositories.company_views import CompanyView, CompanyViewRepository
from web.data.repositories.saved_reports import SavedReport, SavedReportRepository
from web.data.repositories.schedules import (
    MASTER,
    PERSONAL,
    MasterScheduleRepository,
    ScheduleRepository,
    ScheduleRunRepository,
)
from web.data.repositories.users import User, UserRepository
from web.scheduling.personal_views import is_custom_date_params, is_schedulable_saved_view
from web.scheduling.ui_flags import SHOW_COMPANY_SCHEDULE_SETUP
from web.scheduling import cadence as C
from web.scheduling.jobs import SCHEDULE_RUN_JOB_TYPE, enqueue_schedule_run
from web.scheduling.tick import hold_until_next_slot

schedules_bp = Blueprint("schedules", __name__)


# --- shared helpers --------------------------------------------------------

def _authz():
    return current_app.config["AUTHZ"]


def _db():
    return current_app.config["DB"]


def _principal():
    p = current_principal()
    if p is None:
        abort(401, description="Login required")
    return p


def _uid(email: str) -> int:
    user = UserRepository(_db()).get_by_email(email)
    if user is None:
        abort(403, description="Unknown user")
    return user.id


def _require_admin(p):
    if not _authz().is_privileged(p):
        abort(403, description="Admins only")


def _require_master_edit(p, sched):
    if not _authz().can_edit_master(
            p, owner_user_id=sched.owner_user_id, run_as_user_id=sched.run_as_user_id):
        abort(403, description="You can't edit this schedule. Ask an admin.")


def _repo() -> ScheduleRepository:
    return ScheduleRepository(_db())


def _master() -> MasterScheduleRepository:
    return MasterScheduleRepository(_db())


def _settings():
    from web.data.repositories.app_settings import AppSettingsRepository
    return AppSettingsRepository(_db())


def _runs() -> ScheduleRunRepository:
    return ScheduleRunRepository(_db())


def _job_repo():
    return current_app.config["JOB_REPO"]


def _schedule_job_label(job) -> str:
    params = job.params or {}
    sid = params.get("schedule_id")
    kind = params.get("schedule_type") or ""
    prefix = "Run now" if params.get("manual") else "Clock"
    name = ""
    try:
        sid_i = int(sid)
    except (TypeError, ValueError):
        sid_i = None
    if kind == MASTER and sid_i is not None:
        row = _master().get(sid_i)
        name = (getattr(row, "name", None) or "") if row else ""
    elif sid_i is not None:
        owner = job.owner_user_id
        row = _repo().get(sid_i, owner) if owner else None
        if row is not None:
            spec = registry.get(row.report_key)
            name = spec.title if spec else row.report_key
    if not name:
        name = f"{kind or 'schedule'} #{sid}" if sid else "schedule"
    return f"{prefix}: {name}"


def _active_schedule_jobs(p) -> list[dict]:
    from web.data.repositories.jobs import _step_label
    uid = _uid(p.email)
    if _authz().is_privileged(p):
        jobs = _job_repo().list_active(job_type=SCHEDULE_RUN_JOB_TYPE)
    else:
        jobs = _job_repo().list_active(job_type=SCHEDULE_RUN_JOB_TYPE, owner_user_id=uid)
    show_log = _authz().is_developer(p)
    out = []
    for job in jobs:
        row = {
            "id": job.id,
            "status": job.status,
            "label": _schedule_job_label(job),
            "manual": bool((job.params or {}).get("manual")),
        }
        if show_log:
            row["step"] = _step_label(job.log)
        out.append(row)
    return out


def _hold_if_due(repo, sched, schedule_type: str) -> None:
    hold_until_next_slot(repo, _runs(), sched, schedule_type)


def _lookups():
    return current_app.config["LOOKUP_SERVICE"]


def _validate_report(p, report_key: str, *, allow_in_app: bool = True):
    spec = registry.get(report_key)
    if spec is None or spec.status is not registry.ReportStatus.BUILT:
        abort(404, description="Unknown report")
    if not allow_in_app and spec.in_app:
        abort(400, description="That report can't be set up as a master schedule.")
    _authz().assert_report_runnable(p, report_key)
    return spec


def _parse_cadence(body: dict) -> dict:
    try:
        return C.normalize(body.get("cadence"))
    except ValueError as exc:
        abort(400, description=str(exc))


def _filename_template_for_create(body: dict) -> str:
    return (body.get("filename_template") or "").strip() or DEFAULT_FILENAME_TEMPLATE


def _check_sharepoint(p, body: dict) -> str:
    """Master schedules only: company SharePoint path (requires SP access)."""
    from web.delivery.sharepoint import strip_reports_home
    path = strip_reports_home((body.get("sharepoint_path") or "").strip())
    if path and not _authz().has_sharepoint_access(p):
        abort(403, description="You don't have SharePoint delivery access.")
    return path


def _check_personal_folder(body: dict) -> str:
    """Personal schedules store an OneDrive relative path in sharepoint_path."""
    return (body.get("onedrive_path") or body.get("sharepoint_path") or "").strip()


def _master_folder(p, body: dict, params: dict) -> str:
    """Shared → SharePoint. Private → SharePoint if given, else OneDrive."""
    od = (body.get("onedrive_path") or "").strip()
    if _parse_is_shared(body):
        path = _check_sharepoint(p, body)
        if path:
            params["folder_kind"] = "sharepoint"
        return path
    sp = (body.get("sharepoint_path") or "").strip()
    if sp:
        path = _check_sharepoint(p, body)
        params["folder_kind"] = "sharepoint"
        return path
    if od:
        params["folder_kind"] = "onedrive"
        return od
    return ""


def _clean_recipients(body: dict, *, sharepoint_path: str,
                      has_salesman_delivery: bool = False,
                      folder_label: str = "SharePoint folder") -> str:
    """Validate recipients up front (same parser as delivery), so a schedule can't
    be saved with addresses that would silently drop at send time."""
    raw = (body.get("recipients") or "").strip()
    valid = split_recipients(raw)
    if raw and not valid:
        abort(400, description="No valid email recipients (use name@domain.com).")
    if not valid and not sharepoint_path and not has_salesman_delivery:
        abort(400, description=f"A schedule needs recipients or a {folder_label}.")
    return ", ".join(valid)


def _saved_reports() -> SavedReportRepository:
    return SavedReportRepository(_db())


def _company_views() -> CompanyViewRepository:
    return CompanyViewRepository(_db())


def _users() -> UserRepository:
    return UserRepository(_db())


_DEFAULT_VIEW_TOKEN = "default:"
_COMPANY_VIEW_TOKEN = "company:"
_VIEW_SOURCE_COMPANY = "company"
_DELIVERY_PARAM_KEYS = {
    "email_on_no_data", "email_on_no_data_me_only",
    "email_cc", "email_bcc", "folder_kind", "view_source",
    "email_subject", "email_html",
}


def _is_company_view_schedule(params: dict | None) -> bool:
    return (params or {}).get("view_source") == _VIEW_SOURCE_COMPANY


def _stamp_view_source(params: dict, *, company: bool) -> None:
    if company:
        params["view_source"] = _VIEW_SOURCE_COMPANY
    else:
        params.pop("view_source", None)


def _default_view_token(report_key: str) -> str:
    return f"{_DEFAULT_VIEW_TOKEN}{report_key}"


def _company_view_token(view_id: int) -> str:
    return f"{_COMPANY_VIEW_TOKEN}{view_id}"


def _parse_company_view_id(body: dict) -> int | None:
    raw = body.get("saved_report_id")
    if raw is None or not str(raw).strip():
        return None
    token = str(raw).strip()
    if not token.lower().startswith(_COMPANY_VIEW_TOKEN):
        return None
    try:
        return int(token.split(":", 1)[1].strip())
    except (IndexError, ValueError):
        return None


def _load_company_view_schedule(body: dict, p, *, privileged: bool) -> CompanyView:
    if not privileged:
        abort(403, description="Only admins and developers can schedule company views.")
    view_id = _parse_company_view_id(body)
    if view_id is None:
        abort(400, description="Pick a company view to schedule.")
    row = _company_views().get(view_id)
    if row is None:
        abort(404, description="Unknown company view")
    _validate_report(p, row.report_key, allow_in_app=False)
    if is_custom_date_params(row.params):
        abort(400, description="Custom date ranges can't be scheduled.")
    return row


def _parse_default_report_key(body: dict) -> str | None:
    """Report key when the wizard/API is scheduling Default, else None."""
    raw = body.get("saved_report_id")
    if raw is not None and str(raw).strip():
        token = str(raw).strip()
        if token.lower() == "default":
            return (body.get("report_key") or "").strip() or None
        if token.lower().startswith(_DEFAULT_VIEW_TOKEN):
            return token.split(":", 1)[1].strip() or None
        return None
    if not isinstance(body.get("view_name"), str):
        return None
    if normalize_view_name(body.get("view_name")) != DEFAULT_VIEW_NAME:
        return None
    return (body.get("report_key") or "").strip() or None


def _load_default_schedule(body: dict, p, *, privileged: bool) -> tuple[str, dict]:
    """report_key + filter params for a Default-view personal schedule."""
    if not privileged:
        abort(403, description="Only admins and developers can schedule Default.")
    report_key = _parse_default_report_key(body)
    if not report_key:
        abort(400, description="Pick a report to schedule Default.")
    _validate_report(p, report_key, allow_in_app=False)
    incoming = body.get("params") if isinstance(body.get("params"), dict) else None
    if incoming is not None:
        params = dict(incoming)
    else:
        row = ReportDefaultRepository(_db()).get(report_key)
        params = dict(row.params) if row else {}
    if is_custom_date_params(params):
        abort(400, description="Custom date ranges can't be scheduled.")
    return report_key, params


def _load_schedulable_view(body: dict, p, *, privileged: bool,
                           existing=None) -> SavedReport:
    raw_id = body.get("saved_report_id")
    try:
        preset_id = int(raw_id)
    except (TypeError, ValueError):
        abort(400, description="Pick a saved view to schedule.")
    uid = _uid(p.email)
    preset = (
        _saved_reports().get_any(preset_id) if privileged
        else _saved_reports().get(preset_id, uid)
    )
    if preset is None:
        abort(404, description="Unknown saved view")
    if not privileged and preset.user_id != uid:
        abort(404, description="Unknown saved view")
    # Converted custom from/to views stay off the picker but must still be
    # editable (When / Where) when they are already on this schedule.
    if existing is not None and preset.user_id == existing.owner_user_id:
        current = _saved_reports().get_by_name(
            existing.owner_user_id, existing.report_key,
            normalize_view_name(getattr(existing, "view_name", None)))
        if current is not None and current.id == preset.id:
            return preset
    if existing is not None and preset.user_id != existing.owner_user_id:
        abort(400, description="Pick one of this person's saved views.")
    if not is_schedulable_saved_view(preset):
        abort(400, description="That view can't be scheduled (custom dates or Default).")
    return preset


def _personal_folder_and_kind(p, body: dict, *, privileged: bool) -> tuple[str, dict]:
    """OneDrive for everyone; SharePoint path only if privileged chose it."""
    params_extra: dict = {}
    od = (body.get("onedrive_path") or "").strip()
    if privileged:
        sp = _check_sharepoint(p, body)
        want_sp = bool(sp) or str(body.get("folder_kind") or "") == "sharepoint"
        if want_sp and sp:
            params_extra["folder_kind"] = "sharepoint"
            return sp, params_extra
    if not privileged:
        body = dict(body)
        body["sharepoint_path"] = ""
    folder = od or _check_personal_folder(body)
    if folder:
        params_extra["folder_kind"] = "onedrive"
    return folder, params_extra


def _recipients_for_view_schedule(body: dict, owner: User, *, privileged: bool,
                                  folder: str) -> str:
    want_email = body.get("email_to_owner")
    if want_email is None:
        want_email = True
    extras = split_recipients((body.get("recipients") or "").strip()) if privileged else []
    owner_email = (owner.email or "").strip()
    to: list[str] = []
    if want_email and owner_email:
        to.append(owner_email)
    if privileged:
        mine = owner_email.lower()
        to.extend(e for e in extras if e.lower() != mine)
    if not to and not folder:
        abort(400, description="A schedule needs Email to the owner or a OneDrive folder.")
    return ", ".join(to)


def _delivery_params(body: dict, view_params: dict, *, privileged: bool) -> dict:
    params = dict(view_params or {})
    params["email_on_no_data"] = bool(body.get("email_on_no_data"))
    params["email_on_no_data_me_only"] = (
        bool(body.get("email_on_no_data_me_only")) if privileged else False
    )
    if privileged:
        params["email_cc"] = (body.get("email_cc") or "").strip()
        params["email_bcc"] = (body.get("email_bcc") or "").strip()
    else:
        params.pop("email_cc", None)
        params.pop("email_bcc", None)
    return params


def _apply_mail_templates(params: dict, body: dict, existing_params: dict | None = None) -> None:
    src = existing_params or {}
    for key in ("email_subject", "email_html"):
        if key in body:
            raw = body.get(key)
            text = raw.strip() if isinstance(raw, str) else ""
            if key == "email_html" and text:
                text = sanitize_html(text).strip()
            elif key == "email_subject" and text:
                text = text.replace("\n", " ").strip()[:240]
            if text:
                params[key] = text
            else:
                params.pop(key, None)
        elif src.get(key):
            params[key] = src[key]


def _personal_or_404(schedule_id: int, p):
    uid = _uid(p.email)
    sched = _repo().get(schedule_id, uid)
    if sched is not None:
        return sched
    if _authz().is_privileged(p):
        sched = _repo().get_any(schedule_id)
        if sched is not None:
            return sched
    abort(404, description="Unknown schedule")


def _run_or_404(run_id: int, p):
    """Owner (or privileged) for personal; admins for company."""
    run = _runs().get(run_id)
    if run is None or run.schedule_id is None:
        abort(404, description="Unknown run")
    if run.schedule_type == PERSONAL:
        _personal_or_404(run.schedule_id, p)
    elif run.schedule_type == MASTER:
        _require_admin(p)
        if _master().get(run.schedule_id) is None:
            abort(404, description="Unknown run")
    else:
        abort(404, description="Unknown run")
    return run


def _run_title(run) -> str:
    if run.schedule_type == PERSONAL:
        sched = _repo().get_any(run.schedule_id)
        if sched is None:
            return f"Schedule #{run.schedule_id}"
        spec = registry.get(sched.report_key)
        return spec.title if spec else sched.report_key
    sched = _master().get(run.schedule_id)
    if sched is None:
        return f"Company #{run.schedule_id}"
    return sched.name or sched.report_key


def _report_title(report_key: str) -> str:
    spec = registry.get(report_key)
    return spec.title if spec else report_key


def _view_is_visible(p, report_key: str) -> bool:
    return _authz().can_view_report(p, report_key)


def _drain_if_dev():
    worker = current_app.config["JOB_WORKER"]
    if not worker.running and not current_app.config["APP_CONFIG"].is_prod:
        worker.drain()


# --- personal schedules ----------------------------------------------------

@schedules_bp.get("/schedules")
@require_login
def schedules_page():
    p = _principal()
    uid = _uid(p.email)
    authz = _authz()
    is_privileged = authz.is_privileged(p)
    rows = _repo().list_all() if is_privileged else _repo().list_for_user(uid)
    users = {u.id: u for u in _users().list_all()}
    items = []
    for s in rows:
        spec = registry.get(s.report_key)
        owner = users.get(s.owner_user_id)
        items.append({
            "id": s.id, "report_key": s.report_key,
            "name": spec.title if spec else s.report_key,
            "report_title": spec.title if spec else s.report_key,
            "cadence": C.describe(s.cadence), "cadence_raw": s.cadence or {},
            "params": s.params or {}, "recipients": s.recipients,
            "sharepoint_path": s.sharepoint_path, "is_active": s.is_active,
            "last_run": _runs().last_run_at(s.id, PERSONAL),
            "filename_template": getattr(s, "filename_template", "") or "",
            "kind": "personal",
            "view_name": normalize_view_name(getattr(s, "view_name", None)),
            "owner_user_id": s.owner_user_id,
            "owner_name": (owner.display_name or owner.email) if owner else "Unknown",
            "owner_email": owner.email if owner else "",
        })
    items.sort(key=lambda r: (r["owner_name"].lower(), r["report_title"].lower()))
    saved = _saved_reports()
    for row in items:
        if _is_company_view_schedule(row["params"]):
            cv = _company_views().get_by_name(row["report_key"], row["view_name"])
            row["saved_report_id"] = _company_view_token(cv.id) if cv else ""
        else:
            preset = saved.get_by_name(
                row["owner_user_id"], row["report_key"], row["view_name"])
            if preset is not None:
                row["saved_report_id"] = preset.id
            elif row["view_name"] == DEFAULT_VIEW_NAME:
                row["saved_report_id"] = _default_view_token(row["report_key"])
            else:
                cv = _company_views().get_by_name(row["report_key"], row["view_name"])
                row["saved_report_id"] = _company_view_token(cv.id) if cv else ""
        row["folder_kind"] = (row["params"] or {}).get("folder_kind") or "onedrive"
    groups = _group_personal_rows(items, is_privileged)
    context = {
        "active_tab": "schedules", "schedules": items,
        "schedule_groups": groups,
        "is_admin": is_privileged, "is_privileged": is_privileged,
        "can_see_company": False,
        "has_sharepoint": is_privileged and authz.has_sharepoint_access(p),
        "has_schedulable_views": _has_schedulable_views(p, is_privileged),
        "current_user_name": p.name or p.email,
        "views_url": url_for("schedules.list_schedulable_views"),
    }
    context["recent_runs"] = _viewer_run_log(
        p, is_privileged, is_developer=_authz().is_developer(p))
    from web.data.repositories.app_settings import AppSettingsRepository
    test_settings = AppSettingsRepository(current_app.config["DB"])
    context["test_mode_on"] = False
    context["test_emails"] = []
    if is_privileged:
        context["test_mode_on"] = test_settings.is_schedule_test_mode()
        context["test_emails"] = test_settings.test_emails() if context["test_mode_on"] else []
        context["company_schedules_url"] = url_for("schedules.company_schedules_page")
    return render_template("schedules.html", **context)


def _has_schedulable_views(p, privileged: bool) -> bool:
    if privileged:
        return True
    uid = _uid(p.email)
    presets = _saved_reports().list_for_user(uid)
    return any(
        is_schedulable_saved_view(v) and _view_is_visible(p, v.report_key)
        for v in presets
    )


def _group_personal_rows(items: list[dict], is_privileged: bool) -> list[dict]:
    if not is_privileged:
        return [{"owner_name": "", "owner_email": "", "schedules": items}]
    groups: list[dict] = []
    by_owner: dict[int, list] = {}
    order: list[int] = []
    for row in items:
        oid = row["owner_user_id"]
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


def _recent_run_log(*, personal_ids: set[int], include_master: bool,
                    limit: int = 30, viewer=None, viewer_id: int | None = None) -> list[dict]:
    """Collapsible Schedules-page log: runs the viewer is allowed to see."""
    personal_titles = {}
    for sid in personal_ids:
        sched = _repo().get_any(sid)
        if sched is None:
            continue
        spec = registry.get(sched.report_key)
        personal_titles[sid] = spec.title if spec else sched.report_key
    master_titles = {}
    if include_master:
        if viewer_id is None:
            for s in _master().list_all():
                master_titles[s.id] = s.name or s.report_key
        else:
            for s in _master().list_shared():
                master_titles[s.id] = s.name or s.report_key
            for s in _master().list_private_for_user(viewer_id):
                master_titles[s.id] = s.name or s.report_key

    out: list[dict] = []
    for r in _runs().list_recent(limit=80):
        if r.schedule_type == PERSONAL:
            if r.schedule_id not in personal_ids:
                continue
            title = personal_titles.get(r.schedule_id, f"Schedule #{r.schedule_id}")
            kind = "Personal"
        elif r.schedule_type == MASTER and include_master and r.schedule_id in master_titles:
            title = master_titles.get(r.schedule_id, f"Company #{r.schedule_id}")
            kind = "Company"
        else:
            continue
        meta = r.output_meta or {}
        out.append({
            "id": r.id,
            "schedule_id": r.schedule_id,
            "kind": kind,
            "title": title,
            "status": r.status,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "rows": r.rows,
            "message": r.debug_log or meta.get("summary") or "",
            "send_channel": meta.get("send_channel") or "",
            "log_url": url_for("schedules.run_log", run_id=r.id),
            "job_log": meta.get("job_log") or [],
        })
        if len(out) >= limit:
            break
    return out


def _viewer_run_log(p, is_privileged: bool = False, is_developer: bool = False) -> list[dict]:
    uid = _uid(p.email)
    if is_privileged:
        personal_ids = {s.id for s in _repo().list_all()}
    else:
        personal_ids = {s.id for s in _repo().list_for_user(uid)}
    return _recent_run_log(
        personal_ids=personal_ids,
        include_master=is_developer,
        viewer=p, viewer_id=None if is_developer else uid,
        limit=80 if is_developer else 30,
    )


@schedules_bp.get("/api/schedules/recent-runs")
@require_login
def recent_runs():
    p = _principal()
    if request.args.get("kind") == "company":
        _require_admin(p)
        runs = _company_run_log()
    else:
        runs = _viewer_run_log(
            p, _authz().is_privileged(p), is_developer=_authz().is_developer(p))
    if not _authz().is_developer(p):
        for row in runs:
            row.pop("log_url", None)
            row.pop("job_log", None)
    return jsonify({"runs": runs, "active_jobs": _active_schedule_jobs(p)})


@schedules_bp.post("/api/schedules")
@require_login
def create_schedule():
    p = _principal()
    body = request.get_json(silent=True) or {}
    privileged = _authz().is_privileged(p)
    if _parse_default_report_key(body) is not None:
        report_key, view_params = _load_default_schedule(
            body, p, privileged=privileged)
        owner = _users().get_by_id(_uid(p.email))
        if owner is None:
            abort(400, description="That view has no owner.")
        cadence = _parse_cadence(body)
        folder, folder_extra = _personal_folder_and_kind(p, body, privileged=privileged)
        recipients = _recipients_for_view_schedule(
            body, owner, privileged=privileged, folder=folder)
        params = _delivery_params(body, view_params, privileged=privileged)
        params.update(folder_extra)
        _stamp_view_source(params, company=False)
        _apply_mail_templates(params, body)
        sid = _repo().create(
            owner.id, report_key, params=params,
            layout={}, cadence=cadence,
            recipients=recipients, sharepoint_path=folder,
            start_date=body.get("start_date") or None, end_date=body.get("end_date") or None,
            filename_template=_filename_template_for_create(body),
            view_name=DEFAULT_VIEW_NAME,
        )
        created = _repo().get(sid, owner.id)
        if created:
            _hold_if_due(_repo(), created, PERSONAL)
        return jsonify({"id": sid, "owner_user_id": owner.id}), 201
    if _parse_company_view_id(body) is not None:
        cv = _load_company_view_schedule(body, p, privileged=privileged)
        owner = _users().get_by_id(_uid(p.email))
        if owner is None:
            abort(400, description="That view has no owner.")
        cadence = _parse_cadence(body)
        folder, folder_extra = _personal_folder_and_kind(p, body, privileged=privileged)
        recipients = _recipients_for_view_schedule(
            body, owner, privileged=privileged, folder=folder)
        params = _delivery_params(body, dict(cv.params or {}), privileged=privileged)
        params.update(folder_extra)
        _stamp_view_source(params, company=True)
        _apply_mail_templates(params, body)
        sid = _repo().create(
            owner.id, cv.report_key, params=params,
            layout=cv.layout or {}, cadence=cadence,
            recipients=recipients, sharepoint_path=folder,
            start_date=body.get("start_date") or None, end_date=body.get("end_date") or None,
            filename_template=_filename_template_for_create(body),
            view_name=cv.name,
        )
        created = _repo().get(sid, owner.id)
        if created:
            _hold_if_due(_repo(), created, PERSONAL)
        return jsonify({"id": sid, "owner_user_id": owner.id}), 201
    preset = _load_schedulable_view(body, p, privileged=privileged)
    owner = _users().get_by_id(preset.user_id)
    if owner is None:
        abort(400, description="That view has no owner.")
    cadence = _parse_cadence(body)
    folder, folder_extra = _personal_folder_and_kind(p, body, privileged=privileged)
    recipients = _recipients_for_view_schedule(
        body, owner, privileged=privileged, folder=folder)
    params = _delivery_params(body, preset.params, privileged=privileged)
    params.update(folder_extra)
    _stamp_view_source(params, company=False)
    _apply_mail_templates(params, body)
    sid = _repo().create(
        owner.id, preset.report_key, params=params,
        layout=preset.layout or {}, cadence=cadence,
        recipients=recipients, sharepoint_path=folder,
        start_date=body.get("start_date") or None, end_date=body.get("end_date") or None,
        filename_template=_filename_template_for_create(body),
        view_name=preset.name,
    )
    created = _repo().get(sid, owner.id)
    if created:
        _hold_if_due(_repo(), created, PERSONAL)
    return jsonify({"id": sid, "owner_user_id": owner.id}), 201


@schedules_bp.put("/api/schedules/<int:schedule_id>")
@require_login
def update_schedule(schedule_id: int):
    p = _principal()
    body = request.get_json(silent=True) or {}
    privileged = _authz().is_privileged(p)
    existing = _personal_or_404(schedule_id, p)
    owner = _users().get_by_id(existing.owner_user_id)
    if owner is None:
        abort(400, description="That schedule has no owner.")
    if "saved_report_id" in body:
        if _parse_default_report_key(body) is not None:
            report_key, incoming_params = _load_default_schedule(
                body, p, privileged=privileged)
            if report_key != existing.report_key:
                abort(400, description="Pick Default for this report.")
            view_name, layout = DEFAULT_VIEW_NAME, {}
            if isinstance(body.get("params"), dict):
                view_params = incoming_params
            else:
                view_params = {
                    k: v for k, v in (existing.params or {}).items()
                    if k not in _DELIVERY_PARAM_KEYS
                }
        elif _parse_company_view_id(body) is not None:
            cv = _load_company_view_schedule(body, p, privileged=privileged)
            if cv.report_key != existing.report_key:
                abort(400, description="Pick a company view for this report.")
            view_name, layout, view_params = cv.name, cv.layout or {}, dict(cv.params or {})
        else:
            preset = _load_schedulable_view(
                body, p, privileged=privileged, existing=existing)
            if preset.user_id != existing.owner_user_id:
                abort(400, description="Pick one of this person's saved views.")
            view_name, layout, view_params = preset.name, preset.layout or {}, preset.params or {}
    else:
        view_name = existing.view_name
        layout = existing.layout or {}
        view_params = existing.params or {}
        # Keep report filters from the view; drop old delivery keys then re-apply.
        view_params = {
            k: v for k, v in view_params.items()
            if k not in _DELIVERY_PARAM_KEYS
        }
        if _is_company_view_schedule(existing.params):
            cv = _company_views().get_by_name(
                existing.report_key, normalize_view_name(view_name))
            if cv is not None:
                view_params = dict(cv.params or {})
                layout = cv.layout or layout
        else:
            backed = _saved_reports().get_by_name(
                existing.owner_user_id, existing.report_key, normalize_view_name(view_name))
            if backed is not None:
                view_params = dict(backed.params or {})
                layout = backed.layout or layout
            else:
                cv = _company_views().get_by_name(
                    existing.report_key, normalize_view_name(view_name))
                if cv is not None:
                    view_params = dict(cv.params or {})
                    layout = cv.layout or layout
    cadence = _parse_cadence(body)
    folder, folder_extra = _personal_folder_and_kind(p, body, privileged=privileged)
    recipients = _recipients_for_view_schedule(
        body, owner, privileged=privileged, folder=folder)
    params = _delivery_params(body, view_params, privileged=privileged)
    params.update(folder_extra)
    if "saved_report_id" in body:
        _stamp_view_source(params, company=_parse_company_view_id(body) is not None)
    else:
        _stamp_view_source(params, company=_is_company_view_schedule(existing.params))
    _apply_mail_templates(params, body, existing.params)
    ok = _repo().update(
        schedule_id, existing.owner_user_id, params=params,
        layout=layout, cadence=cadence,
        recipients=recipients, sharepoint_path=folder,
        start_date=existing.start_date if "start_date" not in body else (body.get("start_date") or None),
        end_date=existing.end_date if "end_date" not in body else (body.get("end_date") or None),
        filename_template=(body.get("filename_template") or "").strip(),
        view_name=view_name,
    )
    if not ok:
        abort(404, description="Unknown schedule")
    updated = _repo().get(schedule_id, existing.owner_user_id)
    if updated:
        _hold_if_due(_repo(), updated, PERSONAL)
    return jsonify({"updated": True})


@schedules_bp.post("/api/schedules/<int:schedule_id>/toggle")
@require_login
def toggle_schedule(schedule_id: int):
    p = _principal()
    existing = _personal_or_404(schedule_id, p)
    body = request.get_json(silent=True) or {}
    active = bool(body.get("active"))
    if not _repo().set_active(schedule_id, existing.owner_user_id, active):
        abort(404, description="Unknown schedule")
    if active:
        sched = _repo().get(schedule_id, existing.owner_user_id)
        if sched:
            _hold_if_due(_repo(), sched, PERSONAL)
    return jsonify({"active": active})


@schedules_bp.delete("/api/schedules/<int:schedule_id>")
@require_login
def delete_schedule(schedule_id: int):
    p = _principal()
    existing = _personal_or_404(schedule_id, p)
    if not _repo().delete(schedule_id, existing.owner_user_id):
        abort(404, description="Unknown schedule")
    return jsonify({"deleted": True})


@schedules_bp.post("/api/schedules/<int:schedule_id>/run")
@require_login
def run_schedule(schedule_id: int):
    p = _principal()
    existing = _personal_or_404(schedule_id, p)
    job_id = enqueue_schedule_run(
        current_app.config["JOB_REPO"],
        schedule_id=schedule_id, schedule_type=PERSONAL,
        owner_user_id=existing.owner_user_id, ignore_sabbath=True, manual=True)
    _drain_if_dev()
    return jsonify({"job_id": job_id}), 202


@schedules_bp.post("/api/schedules/<int:schedule_id>/copy")
@require_login
def copy_schedule(schedule_id: int):
    """Duplicate a personal schedule so the owner can tweak one field."""
    p = _principal()
    src = _personal_or_404(schedule_id, p)
    sid = _repo().create(
        src.owner_user_id, src.report_key, params=dict(src.params or {}),
        layout=dict(src.layout or {}), cadence=dict(src.cadence or {}),
        recipients=src.recipients, sharepoint_path=src.sharepoint_path,
        start_date=src.start_date, end_date=src.end_date,
        filename_template=getattr(src, "filename_template", "") or "",
        view_name=normalize_view_name(getattr(src, "view_name", None)),
    )
    _repo().set_active(sid, src.owner_user_id, False)
    return jsonify({"id": sid}), 201


@schedules_bp.get("/api/schedules/views")
@require_login
def list_schedulable_views():
    p = _principal()
    privileged = _authz().is_privileged(p)
    uid = _uid(p.email)
    users = {u.id: u for u in _users().list_all() if u.is_active}
    presets = _saved_reports().list_all() if privileged else _saved_reports().list_for_user(uid)
    groups: dict[int, dict] = {}
    order: list[int] = []
    for row in presets:
        if not is_schedulable_saved_view(row):
            continue
        if not _view_is_visible(p, row.report_key):
            continue
        owner = users.get(row.user_id)
        if owner is None:
            continue
        if owner.id not in groups:
            groups[owner.id] = {
                "user_id": owner.id,
                "name": owner.display_name or owner.email,
                "email": owner.email,
                "views": [],
            }
            order.append(owner.id)
        groups[owner.id]["views"].append({
            "id": row.id,
            "name": row.name,
            "report_key": row.report_key,
            "report_title": _report_title(row.report_key),
        })
    out = [groups[i] for i in order if groups[i]["views"]]
    if privileged:
        company_rows = []
        for cv in _company_views().list_all():
            if not _view_is_visible(p, cv.report_key):
                continue
            if is_custom_date_params(cv.params):
                continue
            company_rows.append({
                "id": _company_view_token(cv.id),
                "name": cv.name,
                "report_key": cv.report_key,
                "report_title": _report_title(cv.report_key),
            })
        for spec in registry.built_reports():
            if spec.in_app or not _view_is_visible(p, spec.key):
                continue
            company_rows.append({
                "id": _default_view_token(spec.key),
                "name": DEFAULT_VIEW_NAME,
                "report_key": spec.key,
                "report_title": spec.title,
            })
        if company_rows:
            out.insert(0, {
                "user_id": 0,
                "name": "Company",
                "email": "",
                "views": company_rows,
            })
    out.sort(key=lambda g: (0 if g["name"] == "Company" else 1, g["name"].lower()))
    return jsonify({"groups": out})


@schedules_bp.get("/schedules/<int:schedule_id>/history")
@require_login
def schedule_history(schedule_id: int):
    p = _principal()
    sched = _personal_or_404(schedule_id, p)
    spec = registry.get(sched.report_key)
    runs = _runs().list_for_schedule(schedule_id, PERSONAL)
    return render_template(
        "schedule_history.html", active_tab="schedules",
        report_title=spec.title if spec else sched.report_key,
        cadence=C.describe(sched.cadence), schedule_type=PERSONAL,
        schedule_id=schedule_id, runs=runs,
    )


@schedules_bp.get("/master-schedules/<int:schedule_id>/history")
@require_login
def master_history(schedule_id: int):
    p = _principal()
    _require_admin(p)
    sched = _master().get(schedule_id)
    if sched is None:
        abort(404, description="Unknown master schedule")
    spec = registry.get(sched.report_key)
    title = sched.name or (spec.title if spec else sched.report_key)
    runs = _runs().list_for_schedule(schedule_id, MASTER)
    return render_template(
        "schedule_history.html", active_tab="schedules",
        report_title=title, cadence=C.describe(sched.cadence),
        schedule_type=MASTER, schedule_id=schedule_id, runs=runs,
    )


@schedules_bp.get("/schedules/runs/<int:run_id>")
@require_login
def run_log(run_id: int):
    p = _principal()
    if not _authz().is_developer(p):
        abort(404, description="Unknown run")
    run = _run_or_404(run_id, p)
    meta = run.output_meta or {}
    job_id = str(meta.get("job_id") or "").strip()
    job_url = ""
    if job_id and (run.status in ("running", "queued") or not meta.get("job_log")):
        job_url = url_for("reports.job_status", job_id=job_id)
    if run.schedule_type == MASTER:
        back_url = url_for("schedules.company_schedules_page")
        history_url = url_for("schedules.master_history", schedule_id=run.schedule_id)
        kind = "Company"
    else:
        back_url = url_for("schedules.schedules_page")
        history_url = url_for("schedules.schedule_history", schedule_id=run.schedule_id)
        kind = "Personal"
    return render_template(
        "schedule_run.html", active_tab="schedules",
        run=run, meta=meta, job_log=meta.get("job_log") or [],
        job_url=job_url, title=_run_title(run), kind=kind,
        back_url=back_url, history_url=history_url,
    )


# --- master schedules (admin) ----------------------------------------------

# Same filter keys the report viewer uses. Kept here (not imported from the
# reports blueprint) so schedules stay import-light and the mapping is obvious.
_MASTER_REPORT_FILTERS: dict[str, tuple[str, ...]] = {
    "ordered": ("period", "status", "customers", "salesman"),
    "invoiced": ("period", "customers", "salesman"),
    "salesman": ("year", "salesman"),
    "number_4": (),
    "customer_activity": ("salesman",),
    "sales_by_state": ("year",),
}

_PERIOD_OPTIONS: tuple[tuple[str, str], ...] = (
    ("yesterday", "Yesterday"),
    ("mtd", "Month to Date"),
    ("last_month", "Last Month"),
    ("ytd", "Year to Date"),
    ("this_week", "This Week"),
    ("last_7_days", "Last 7 Days"),
    ("all_time", "All Time"),
)

_STATUS_OPTIONS: tuple[tuple[str, str], ...] = (
    ("", "All statuses"),
    ("Open order", "Open"),
    ("Delivered", "Delivered"),
    ("Invoiced", "Invoiced"),
    ("Cancelled", "Cancelled"),
)


def _params_label(params: dict | None) -> str:
    """Plain-English one-liner for the schedules table Options column."""
    p = params or {}
    bits: list[str] = []
    if period := (p.get("period") or "").strip():
        bits.append(period.replace("_", " "))
    status = _as_str_list(p.get("status"))
    if status:
        bits.append("status " + ", ".join(status))
    salesman = _as_str_list(p.get("salesman"))
    if salesman:
        bits.append("salesman " + ", ".join(salesman))
    if p.get("email_to_salesmen"):
        bits.append("email selected salesmen")
    email_salesmen = _as_str_list(p.get("email_salesman_keys"))
    if email_salesmen:
        bits.append("email salesmen " + ", ".join(email_salesmen))
    elif p.get("split_by_salesman"):
        bits.append("split by salesman")
    customers = _as_str_list(p.get("customers"))
    if customers:
        bits.append("customers " + " ".join(customers))
    if year := p.get("year"):
        bits.append(f"year {year}")
    return ", ".join(bits) if bits else "defaults"


def _as_str_list(raw) -> list[str]:
    """Accept a list, CSV string, or space-separated ids -> cleaned string list.

    Comma-separated wins when commas are present so values with spaces
    (e.g. status \"Open order\") stay intact.
    """
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(x).strip() for x in raw if str(x).strip()]
    s = str(raw).strip()
    if not s:
        return []
    if "," in s:
        return [p.strip() for p in s.split(",") if p.strip()]
    return [p for p in s.split() if p]


def _as_bool(raw) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _normalize_master_params(raw: dict | None, *, allow_salesman_delivery: bool = False) -> dict:
    """Keep only known filter keys; multi filters store as lists."""
    src = raw if isinstance(raw, dict) else {}
    out: dict = {}
    for key in ("period", "year", "start_date", "end_date"):
        val = src.get(key)
        if val is None:
            continue
        s = str(val).strip()
        if s:
            out[key] = s
    for key in ("status", "salesman", "customers"):
        cleaned = _as_str_list(src.get(key))
        if cleaned:
            out[key] = cleaned
    if allow_salesman_delivery:
        selected_salesmen = _as_str_list(out.get("salesman"))
        email_keys = _as_str_list(src.get("email_salesman_keys"))
        email_to_selected = bool(selected_salesmen) and _as_bool(src.get("email_to_salesmen"))
        split_unfiltered = not selected_salesmen and (_as_bool(src.get("split_by_salesman")) or bool(email_keys))
        out["email_to_salesmen"] = email_to_selected
        out["split_by_salesman"] = split_unfiltered
        out["email_salesman_keys"] = email_keys if split_unfiltered else []
    for key in ("email_cc", "email_bcc"):
        s = str(src.get(key) or "").strip()
        if s:
            out[key] = s
    out["email_on_no_data"] = _as_bool(src.get("email_on_no_data"))
    out["email_on_no_data_me_only"] = _as_bool(src.get("email_on_no_data_me_only"))
    kind = str(src.get("folder_kind") or "").strip()
    if kind in ("onedrive", "sharepoint"):
        out["folder_kind"] = kind
    return out


def _has_salesman_delivery(params: dict) -> bool:
    if params.get("email_to_salesmen") and _as_str_list(params.get("salesman")):
        return True
    if _as_str_list(params.get("email_salesman_keys")):
        return True
    return _as_bool(params.get("split_by_salesman"))


def _manager_options() -> list[dict]:
    return [
        {"id": u.id, "email": u.email, "name": u.display_name or u.email}
        for u in UserRepository(_db()).list_all()
        if u.is_active and u.role == ROLE_MANAGER
    ]


def _parse_run_as(p, body: dict) -> int | None:
    """Admins may pick a manager whose book the schedule runs in."""
    raw = body.get("run_as_user_id")
    if raw in (None, "", 0, "0"):
        return None
    if not _authz().is_privileged(p):
        abort(403, description="Only admins can run a schedule as a manager.")
    try:
        uid = int(raw)
    except (TypeError, ValueError):
        abort(400, description="Pick a manager from the list.")
    user = UserRepository(_db()).get_by_id(uid)
    if user is None or not user.is_active or user.role != ROLE_MANAGER:
        abort(400, description="That manager is not available.")
    return uid


def _parse_is_shared(body: dict) -> bool:
    if "is_shared" in body:
        return bool(body.get("is_shared"))
    if "share" in body:
        return bool(body.get("share"))
    return True


def _scoped_salesmen(p, rows: list[dict]) -> list[dict]:
    keys = _authz().visible_salesman_keys(p)
    if keys is None:
        return rows
    return [r for r in rows if salesman_key(r.get("key")) in keys]


def _master_page_context(p) -> dict:
    authz = _authz()
    items = []
    for s in _master().list_all():
        spec = registry.get(s.report_key)
        can_edit = authz.can_edit_master(
            p, owner_user_id=s.owner_user_id, run_as_user_id=s.run_as_user_id)
        items.append({
            "id": s.id, "name": s.name, "report_key": s.report_key,
            "report_title": spec.title if spec else s.report_key,
            "cadence": C.describe(s.cadence), "cadence_raw": s.cadence or {},
            "params": s.params or {}, "params_label": _params_label(s.params),
            "recipients": s.recipients,
            "sharepoint_path": s.sharepoint_path, "is_active": s.is_active,
            "last_run": _runs().last_run_at(s.id, MASTER),
            "can_edit": can_edit,
            "filename_template": getattr(s, "filename_template", "") or "",
            "is_shared": bool(s.is_shared),
            "owner_user_id": s.owner_user_id,
            "run_as_user_id": s.run_as_user_id,
            "view_name": normalize_view_name(getattr(s, "view_name", None)),
        })
    items.sort(key=lambda row: (row["name"] or "").casefold())
    built = [
        {"key": s.key, "title": s.title}
        for s in registry.built_reports()
        if not s.in_app
    ]
    from report_engine.dates import today_eastern
    year_now = today_eastern().year
    return {
        "master_schedules": items,
        "built_reports": built,
        "report_filters": _MASTER_REPORT_FILTERS,
        "period_options": _PERIOD_OPTIONS,
        "status_options": _STATUS_OPTIONS,
        "year_options": list(range(year_now, year_now - 5, -1)),
        "managers": _manager_options(),
        "company_schedule_setup": SHOW_COMPANY_SCHEDULE_SETUP,
    }


def _company_run_log() -> list[dict]:
    return _recent_run_log(
        personal_ids=set(), include_master=True, viewer_id=None)


@schedules_bp.get("/settings/company-schedules")
@require_login
def company_schedules_page():
    p = _principal()
    _require_admin(p)
    authz = _authz()
    ctx = _master_page_context(p)
    from web.data.repositories.app_settings import AppSettingsRepository
    test_settings = AppSettingsRepository(current_app.config["DB"])
    ctx.update({
        "active_tab": "settings",
        "is_admin": True,
        "is_privileged": True,
        "can_see_company": True,
        "company_page": True,
        "has_sharepoint": authz.has_sharepoint_access(p),
        "test_mode_on": test_settings.is_schedule_test_mode(),
        "test_emails": test_settings.test_emails() if test_settings.is_schedule_test_mode() else [],
        "recent_runs": _company_run_log(),
    })
    return render_template("company_schedules.html", **ctx)


@schedules_bp.get("/master-schedules")
@require_login
def master_page():
    p = _principal()
    _require_admin(p)
    return redirect(url_for("schedules.company_schedules_page"))


@schedules_bp.get("/api/master-schedules/lookups/status")
@require_login
def master_lookup_status():
    """Warm-up progress for the salesman / customer dropdowns."""
    _require_admin(_principal())
    return jsonify(_lookups().status())


@schedules_bp.get("/api/master-schedules/lookups/salesmen")
@require_login
def master_lookup_salesmen():
    """Salesmen from the salesmen_master SP (same source as report filter dropdowns)."""
    p = _principal()
    _require_admin(p)
    return jsonify({"salesmen": _scoped_salesmen(p, _lookups().salesmen())})


@schedules_bp.get("/api/master-schedules/lookups/salesmen-emails")
@require_login
def master_lookup_salesmen_emails():
    """Raw SalesGroup values that also have an email (salesmen_master SP, local fallback)."""
    p = _principal()
    _require_admin(p)
    salesmen = _scoped_salesmen(p, _lookups().salesmen())
    directory = current_app.config["SALESMAN_DIRECTORY"]
    emails = directory.emails_by_keys([r["key"] for r in salesmen])
    return jsonify({"salesmen": [
        {"key": r["key"], "name": r["name"], "email": emails.get(r["key"], "")}
        for r in salesmen
        if emails.get(r["key"], "")
    ]})


@schedules_bp.get("/api/master-schedules/lookups/customers")
@require_login
def master_lookup_customers():
    """Customers from customer_master (optional ?salesman= filter)."""
    p = _principal()
    _require_admin(p)
    salesman = (request.args.get("salesman") or "").strip() or None
    rows = _lookups().customers(salesman)
    keys = _authz().visible_salesman_keys(p)
    if keys is not None:
        rows = [c for c in rows if salesman_key(c.get("salesman")) in keys]
    return jsonify({"customers": rows})


@schedules_bp.post("/api/master-schedules")
@require_login
def create_master():
    p = _principal()
    _require_admin(p)
    body = request.get_json(silent=True) or {}
    report_key = (body.get("report_key") or "").strip()
    _validate_report(p, report_key, allow_in_app=False)
    name = (body.get("name") or "").strip()
    if not name:
        abort(400, description="A master schedule needs a name.")
    cadence = _parse_cadence(body)
    params = _normalize_master_params(
        body.get("params") or {},
        allow_salesman_delivery="salesman" in _MASTER_REPORT_FILTERS.get(report_key, ()),
    )
    sp = _master_folder(p, body, params)
    recipients = _clean_recipients(
        body, sharepoint_path=sp, has_salesman_delivery=_has_salesman_delivery(params),
        folder_label="folder",
    )
    view_name, layout = view_and_layout_for_create(body)
    mid = _master().create(
        report_key, name, params=params, layout=layout,
        cadence=cadence, recipients=recipients, sharepoint_path=sp,
        filename_template=_filename_template_for_create(body),
        owner_user_id=_uid(p.email),
        is_shared=_parse_is_shared(body),
        run_as_user_id=_parse_run_as(p, body),
        view_name=view_name,
    )
    _settings().unskip_seed_name(name)
    created = _master().get(mid)
    if created:
        _hold_if_due(_master(), created, MASTER)
    return jsonify({"id": mid}), 201


@schedules_bp.post("/api/master-schedules/<int:schedule_id>/copy")
@require_login
def copy_master(schedule_id: int):
    """Duplicate a company schedule so the user can tweak one field."""
    p = _principal()
    _require_admin(p)
    src = _master().get(schedule_id)
    if src is None:
        abort(404, description="Unknown master schedule")
    _require_master_edit(p, src)
    mid = _master().copy(src, owner_user_id=_uid(p.email))
    return jsonify({"id": mid}), 201


@schedules_bp.put("/api/master-schedules/<int:schedule_id>")
@require_login
def update_master(schedule_id: int):
    p = _principal()
    _require_admin(p)
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        abort(400, description="A master schedule needs a name.")
    report_key = (body.get("report_key") or "").strip()
    if report_key:
        _validate_report(p, report_key, allow_in_app=False)
    existing = _master().get(schedule_id)
    if existing is None:
        abort(404, description="Unknown master schedule")
    _require_master_edit(p, existing)
    cadence = _parse_cadence(body)
    effective_report_key = report_key or existing.report_key
    params = _normalize_master_params(
        body.get("params") or {},
        allow_salesman_delivery="salesman" in _MASTER_REPORT_FILTERS.get(effective_report_key, ()),
    )
    sp = _master_folder(p, body, params)
    recipients = _clean_recipients(
        body, sharepoint_path=sp, has_salesman_delivery=_has_salesman_delivery(params),
        folder_label="folder",
    )
    view_name, layout = view_and_layout_for_update(
        body, getattr(existing, "view_name", None), existing.layout)
    kwargs = dict(
        name=name, params=params, layout=layout,
        cadence=cadence, recipients=recipients, sharepoint_path=sp,
        filename_template=(body.get("filename_template") or "").strip(),
        is_shared=_parse_is_shared(body),
        run_as_user_id=_parse_run_as(p, body) if _authz().is_privileged(p) else existing.run_as_user_id,
        view_name=view_name,
    )
    if report_key:
        kwargs["report_key"] = report_key
    if not _master().update(schedule_id, **kwargs):
        abort(404, description="Unknown master schedule")
    if existing.name != name:
        _settings().skip_seed_name(existing.name)
        _settings().unskip_seed_name(name)
    updated = _master().get(schedule_id)
    if updated:
        _hold_if_due(_master(), updated, MASTER)
    return jsonify({"updated": True})


@schedules_bp.post("/api/master-schedules/<int:schedule_id>/toggle")
@require_login
def toggle_master(schedule_id: int):
    p = _principal()
    _require_admin(p)
    sched = _master().get(schedule_id)
    if sched is None:
        abort(404, description="Unknown master schedule")
    _require_master_edit(p, sched)
    body = request.get_json(silent=True) or {}
    active = bool(body.get("active"))
    if not _master().set_active(schedule_id, active):
        abort(404, description="Unknown master schedule")
    if active:
        row = _master().get(schedule_id)
        if row:
            _hold_if_due(_master(), row, MASTER)
    return jsonify({"active": active})


@schedules_bp.delete("/api/master-schedules/<int:schedule_id>")
@require_login
def delete_master(schedule_id: int):
    p = _principal()
    _require_admin(p)
    sched = _master().get(schedule_id)
    if sched is None:
        abort(404, description="Unknown master schedule")
    _require_master_edit(p, sched)
    name = sched.name
    if not _master().delete(schedule_id):
        abort(404, description="Unknown master schedule")
    _settings().skip_seed_name(name)
    return jsonify({"deleted": True})


@schedules_bp.post("/api/master-schedules/<int:schedule_id>/run")
@require_login
def run_master(schedule_id: int):
    p = _principal()
    _require_admin(p)
    sched = _master().get(schedule_id)
    if sched is None:
        abort(404, description="Unknown master schedule")
    _require_master_edit(p, sched)
    job_id = enqueue_schedule_run(current_app.config["JOB_REPO"],
                                  schedule_id=schedule_id, schedule_type=MASTER,
                                  owner_user_id=_uid(p.email),
                                  ignore_sabbath=True, manual=True)
    _drain_if_dev()
    return jsonify({"job_id": job_id}), 202
