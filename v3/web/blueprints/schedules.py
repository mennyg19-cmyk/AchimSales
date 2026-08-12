"""Schedules: personal recurring deliveries + admin master schedules.

Personal schedules are owner-scoped; master schedules are admin-only and shared.
Both store filter params + grid layout + cadence + delivery targets, run through
the same ScheduleRunner, and record into the shared run-history ledger. "Run now"
and the cron tick both enqueue a durable ``schedule.run`` job.
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, url_for

from report_engine import registry
from web.auth.decorators import require_login
from web.auth.session import current_principal
from web.delivery.email import split_recipients
from web.data.repositories.schedules import (
    MASTER,
    PERSONAL,
    MasterScheduleRepository,
    ScheduleRepository,
    ScheduleRunRepository,
)
from web.data.repositories.salesmen import SalesmanRepository
from web.data.repositories.users import UserRepository
from web.scheduling import cadence as C
from web.scheduling.jobs import enqueue_schedule_run

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


def _repo() -> ScheduleRepository:
    return ScheduleRepository(_db())


def _master() -> MasterScheduleRepository:
    return MasterScheduleRepository(_db())


def _runs() -> ScheduleRunRepository:
    return ScheduleRunRepository(_db())


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


def _check_sharepoint(p, body: dict) -> str:
    """Master schedules only: company SharePoint path (requires SP access)."""
    path = (body.get("sharepoint_path") or "").strip()
    if path and not _authz().has_sharepoint_access(p):
        abort(403, description="You don't have SharePoint delivery access.")
    return path


def _check_personal_folder(body: dict) -> str:
    """Personal schedules store an OneDrive relative path in sharepoint_path."""
    return (body.get("onedrive_path") or body.get("sharepoint_path") or "").strip()


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
    is_admin = _authz().is_privileged(p)
    items = []
    for s in _repo().list_for_user(uid):
        spec = registry.get(s.report_key)
        items.append({
            "id": s.id, "report_key": s.report_key,
            "report_title": spec.title if spec else s.report_key,
            "cadence": C.describe(s.cadence), "recipients": s.recipients,
            "sharepoint_path": s.sharepoint_path, "is_active": s.is_active,
            "last_run": _runs().last_run_at(s.id, PERSONAL),
        })
    authz = _authz()
    personal_reports = [
        {"key": s.key, "title": s.title}
        for s in registry.built_reports()
        if (not s.in_app) and authz.can_view_report(p, s.key)
    ]
    from datetime import datetime
    from zoneinfo import ZoneInfo
    year_now = datetime.now(ZoneInfo("America/New_York")).year
    context = {
        "active_tab": "schedules", "schedules": items, "is_admin": is_admin,
        "personal_reports": personal_reports,
        "personal_report_filters": {k: list(v) for k, v in _MASTER_REPORT_FILTERS.items()},
        "period_options": _PERIOD_OPTIONS,
        "year_options": list(range(year_now, year_now - 5, -1)),
    }
    if is_admin:
        context.update(_master_page_context())
    context["recent_runs"] = _recent_run_log(
        personal_ids={s["id"] for s in items},
        include_master=is_admin,
    )
    return render_template("schedules.html", **context)


def _recent_run_log(*, personal_ids: set[int], include_master: bool,
                    limit: int = 30) -> list[dict]:
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
        for s in _master().list_all():
            master_titles[s.id] = s.name or s.report_key

    out: list[dict] = []
    for r in _runs().list_recent(limit=80):
        if r.schedule_type == PERSONAL:
            if r.schedule_id not in personal_ids:
                continue
            title = personal_titles.get(r.schedule_id, f"Schedule #{r.schedule_id}")
            history_url = url_for("schedules.schedule_history", schedule_id=r.schedule_id)
            kind = "Personal"
        elif r.schedule_type == MASTER and include_master:
            title = master_titles.get(r.schedule_id, f"Company #{r.schedule_id}")
            history_url = url_for("schedules.master_history", schedule_id=r.schedule_id)
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
            "history_url": history_url,
        })
        if len(out) >= limit:
            break
    return out


@schedules_bp.post("/api/schedules")
@require_login
def create_schedule():
    p = _principal()
    body = request.get_json(silent=True) or {}
    report_key = (body.get("report_key") or "").strip()
    _validate_report(p, report_key)
    cadence = _parse_cadence(body)
    folder = _check_personal_folder(body)
    recipients = _clean_recipients(body, sharepoint_path=folder, folder_label="OneDrive folder")
    sid = _repo().create(
        _uid(p.email), report_key, params=body.get("params") or {},
        layout=body.get("layout") or {}, cadence=cadence,
        recipients=recipients, sharepoint_path=folder,
        start_date=body.get("start_date") or None, end_date=body.get("end_date") or None,
        filename_template=(body.get("filename_template") or "").strip(),
    )
    return jsonify({"id": sid}), 201


@schedules_bp.put("/api/schedules/<int:schedule_id>")
@require_login
def update_schedule(schedule_id: int):
    p = _principal()
    body = request.get_json(silent=True) or {}
    cadence = _parse_cadence(body)
    folder = _check_personal_folder(body)
    recipients = _clean_recipients(body, sharepoint_path=folder, folder_label="OneDrive folder")
    ok = _repo().update(
        schedule_id, _uid(p.email), params=body.get("params") or {},
        layout=body.get("layout") or {}, cadence=cadence,
        recipients=recipients, sharepoint_path=folder,
        start_date=body.get("start_date") or None, end_date=body.get("end_date") or None,
        filename_template=(body.get("filename_template") or "").strip(),
    )
    if not ok:
        abort(404, description="Unknown schedule")
    return jsonify({"updated": True})


@schedules_bp.post("/api/schedules/<int:schedule_id>/toggle")
@require_login
def toggle_schedule(schedule_id: int):
    p = _principal()
    body = request.get_json(silent=True) or {}
    if not _repo().set_active(schedule_id, _uid(p.email), bool(body.get("active"))):
        abort(404, description="Unknown schedule")
    return jsonify({"active": bool(body.get("active"))})


@schedules_bp.delete("/api/schedules/<int:schedule_id>")
@require_login
def delete_schedule(schedule_id: int):
    p = _principal()
    if not _repo().delete(schedule_id, _uid(p.email)):
        abort(404, description="Unknown schedule")
    return jsonify({"deleted": True})


@schedules_bp.post("/api/schedules/<int:schedule_id>/run")
@require_login
def run_schedule(schedule_id: int):
    p = _principal()
    uid = _uid(p.email)
    if _repo().get(schedule_id, uid) is None:
        abort(404, description="Unknown schedule")
    job_id = enqueue_schedule_run(current_app.config["JOB_REPO"],
                                  schedule_id=schedule_id, schedule_type=PERSONAL,
                                  owner_user_id=uid)
    _drain_if_dev()
    return jsonify({"job_id": job_id}), 202


@schedules_bp.post("/api/schedules/<int:schedule_id>/copy")
@require_login
def copy_schedule(schedule_id: int):
    """Duplicate a personal schedule so the user can tweak one field."""
    p = _principal()
    uid = _uid(p.email)
    src = _repo().get(schedule_id, uid)
    if src is None:
        abort(404, description="Unknown schedule")
    sid = _repo().create(
        uid, src.report_key, params=dict(src.params or {}),
        layout=dict(src.layout or {}), cadence=dict(src.cadence or {}),
        recipients=src.recipients, sharepoint_path=src.sharepoint_path,
        start_date=src.start_date, end_date=src.end_date,
        filename_template=getattr(src, "filename_template", "") or "",
    )
    # Leave the copy inactive so it doesn't double-fire until edited.
    _repo().set_active(sid, uid, False)
    return jsonify({"id": sid}), 201


@schedules_bp.get("/schedules/<int:schedule_id>/history")
@require_login
def schedule_history(schedule_id: int):
    p = _principal()
    uid = _uid(p.email)
    sched = _repo().get(schedule_id, uid)
    if sched is None:
        abort(404, description="Unknown schedule")
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


# --- master schedules (admin) ----------------------------------------------

# Same filter keys the report viewer uses. Kept here (not imported from the
# reports blueprint) so schedules stay import-light and the mapping is obvious.
_MASTER_REPORT_FILTERS: dict[str, tuple[str, ...]] = {
    "ordered": ("period", "status", "customers", "salesman"),
    "invoiced": ("period", "customers", "salesman"),
    "salesman": ("year",),
    "number_4": (),
    "customer_activity": ("salesman",),
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
    return out


def _has_salesman_delivery(params: dict) -> bool:
    if params.get("email_to_salesmen") and _as_str_list(params.get("salesman")):
        return True
    return bool(_as_str_list(params.get("email_salesman_keys")))


def _master_page_context() -> dict:
    items = []
    for s in _master().list_all():
        spec = registry.get(s.report_key)
        items.append({
            "id": s.id, "name": s.name, "report_key": s.report_key,
            "report_title": spec.title if spec else s.report_key,
            "cadence": C.describe(s.cadence), "cadence_raw": s.cadence or {},
            "params": s.params or {}, "params_label": _params_label(s.params),
            "recipients": s.recipients,
            "sharepoint_path": s.sharepoint_path, "is_active": s.is_active,
            "last_run": _runs().last_run_at(s.id, MASTER),
        })
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
    }


@schedules_bp.get("/master-schedules")
@require_login
def master_page():
    p = _principal()
    _require_admin(p)
    return redirect(url_for("schedules.schedules_page") + "#company")


@schedules_bp.get("/api/master-schedules/lookups/status")
@require_login
def master_lookup_status():
    """Warm-up progress for the customer_master-backed dropdowns."""
    _require_admin(_principal())
    return jsonify(_lookups().status())


@schedules_bp.get("/api/master-schedules/lookups/salesmen")
@require_login
def master_lookup_salesmen():
    """Salesmen from customer_master (same source as report filter dropdowns)."""
    _require_admin(_principal())
    return jsonify({"salesmen": _lookups().salesmen()})


@schedules_bp.get("/api/master-schedules/lookups/salesmen-emails")
@require_login
def master_lookup_salesmen_emails():
    """Raw SalesGroup values that also have an email in the salesmen table."""
    _require_admin(_principal())
    salesmen = _lookups().salesmen()
    emails = SalesmanRepository(_db()).emails_by_keys([r["key"] for r in salesmen])
    return jsonify({"salesmen": [
        {"key": r["key"], "name": r["name"], "email": emails.get(r["key"], "")}
        for r in salesmen
        if emails.get(r["key"], "")
    ]})


@schedules_bp.get("/api/master-schedules/lookups/customers")
@require_login
def master_lookup_customers():
    """Customers from customer_master (optional ?salesman= filter)."""
    _require_admin(_principal())
    salesman = (request.args.get("salesman") or "").strip() or None
    return jsonify({"customers": _lookups().customers(salesman)})


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
    sp = _check_sharepoint(p, body)
    params = _normalize_master_params(
        body.get("params") or {},
        allow_salesman_delivery="salesman" in _MASTER_REPORT_FILTERS.get(report_key, ()),
    )
    recipients = _clean_recipients(
        body, sharepoint_path=sp, has_salesman_delivery=_has_salesman_delivery(params),
    )
    mid = _master().create(
        report_key, name, params=params, layout=body.get("layout") or {},
        cadence=cadence, recipients=recipients, sharepoint_path=sp,
        filename_template=(body.get("filename_template") or "").strip(),
    )
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
    # report_key may be changed on edit (wizard allows picking a different report).
    report_key = (body.get("report_key") or "").strip()
    if report_key:
        _validate_report(p, report_key, allow_in_app=False)
    existing = _master().get(schedule_id)
    if existing is None:
        abort(404, description="Unknown master schedule")
    cadence = _parse_cadence(body)
    sp = _check_sharepoint(p, body)
    effective_report_key = report_key or existing.report_key
    params = _normalize_master_params(
        body.get("params") or {},
        allow_salesman_delivery="salesman" in _MASTER_REPORT_FILTERS.get(effective_report_key, ()),
    )
    recipients = _clean_recipients(
        body, sharepoint_path=sp, has_salesman_delivery=_has_salesman_delivery(params),
    )
    kwargs = dict(
        name=name, params=params, layout=body.get("layout") or {},
        cadence=cadence, recipients=recipients, sharepoint_path=sp,
        filename_template=(body.get("filename_template") or "").strip(),
    )
    if report_key:
        kwargs["report_key"] = report_key
    if not _master().update(schedule_id, **kwargs):
        abort(404, description="Unknown master schedule")
    return jsonify({"updated": True})


@schedules_bp.post("/api/master-schedules/<int:schedule_id>/toggle")
@require_login
def toggle_master(schedule_id: int):
    p = _principal()
    _require_admin(p)
    body = request.get_json(silent=True) or {}
    if not _master().set_active(schedule_id, bool(body.get("active"))):
        abort(404, description="Unknown master schedule")
    return jsonify({"active": bool(body.get("active"))})


@schedules_bp.delete("/api/master-schedules/<int:schedule_id>")
@require_login
def delete_master(schedule_id: int):
    p = _principal()
    _require_admin(p)
    if not _master().delete(schedule_id):
        abort(404, description="Unknown master schedule")
    return jsonify({"deleted": True})


@schedules_bp.post("/api/master-schedules/<int:schedule_id>/run")
@require_login
def run_master(schedule_id: int):
    p = _principal()
    _require_admin(p)
    if _master().get(schedule_id) is None:
        abort(404, description="Unknown master schedule")
    job_id = enqueue_schedule_run(current_app.config["JOB_REPO"],
                                  schedule_id=schedule_id, schedule_type=MASTER)
    _drain_if_dev()
    return jsonify({"job_id": job_id}), 202
