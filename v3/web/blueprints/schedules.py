"""Schedules: personal recurring deliveries + shared company schedules.

Personal schedules are owner-scoped. Company (master) schedules are visible to
admins, developers, and managers; managers can edit only rows they created or
that run in their book. Sales reps never see the company list.
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, redirect, request, url_for

from report_engine import registry
from report_engine.lib import salesman_key
from web.auth.principal import ROLE_MANAGER
from web.auth.session import current_principal
from web.delivery.email import split_recipients
from web.data.repositories.report_defaults import normalize_view_name
from web.data.repositories.schedules import (
    MASTER,
    PERSONAL,
    MasterScheduleRepository,
    ScheduleRepository,
    ScheduleRunRepository,
)
from web.data.repositories.users import UserRepository
from web.scheduling import cadence as C
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


def _require_company_viewer(p):
    if not _authz().can_see_company_schedules(p):
        abort(403, description="Company schedules are for managers and admins.")


def _require_master_edit(p, sched):
    if not _authz().can_edit_master(
            p, owner_user_id=sched.owner_user_id, run_as_user_id=sched.run_as_user_id):
        abort(403, description="You can't edit this schedule. Ask an admin.")


def _require_master_visible(p, sched):
    """Shared: managers/admins. Private: owner (or admin)."""
    if sched.is_shared:
        _require_company_viewer(p)
        return
    uid = _uid(p.email)
    if sched.owner_user_id == uid or _authz().is_privileged(p):
        return
    abort(404, description="Unknown master schedule")


def _repo() -> ScheduleRepository:
    return ScheduleRepository(_db())


def _master() -> MasterScheduleRepository:
    return MasterScheduleRepository(_db())


def _settings():
    from web.data.repositories.app_settings import AppSettingsRepository
    return AppSettingsRepository(_db())


def _runs() -> ScheduleRunRepository:
    return ScheduleRunRepository(_db())


def _hold_if_due(repo, sched, schedule_type: str) -> None:
    hold_until_next_slot(repo, _runs(), sched, schedule_type)


def _lookups():
    return current_app.config["LOOKUP_SERVICE"]


def _validate_report(p, report_key: str, *, allow_in_app: bool = False):
    spec = registry.get(report_key)
    if spec is None or spec.status is not registry.ReportStatus.BUILT:
        abort(404, description="Unknown report")
    if not allow_in_app and spec.in_app:
        abort(400, description="That report can't be scheduled.")
    _authz().assert_report_runnable(p, report_key)
    return spec


def _parse_cadence(body: dict) -> dict:
    try:
        return C.normalize(body.get("cadence"))
    except ValueError as exc:
        abort(400, description=str(exc))


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


def _note_saved_recipients(recipients: str, user_id: int | None,
                           params: dict | None = None) -> None:
    from web.data.repositories.external_recipients import ExternalRecipientRepository
    addrs = split_recipients(recipients)
    extra = params or {}
    addrs.extend(split_recipients(str(extra.get("email_cc") or "")))
    addrs.extend(split_recipients(str(extra.get("email_bcc") or "")))
    ExternalRecipientRepository(_db()).note_addresses(
        addrs, requested_by_user_id=user_id)


def _drain_if_dev():
    worker = current_app.config["JOB_WORKER"]
    if not worker.running and not current_app.config["APP_CONFIG"].is_prod:
        worker.drain()


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
        for s in _master().list_shared():
            master_titles[s.id] = s.name or s.report_key
        if viewer_id:
            for s in _master().list_private_for_user(viewer_id):
                master_titles[s.id] = s.name or s.report_key

    out: list[dict] = []
    for r in _runs().list_recent(limit=80):
        if r.schedule_type == PERSONAL:
            if r.schedule_id not in personal_ids:
                continue
            title = personal_titles.get(r.schedule_id, f"Schedule #{r.schedule_id}")
            history_url = url_for("schedules.schedule_history", schedule_id=r.schedule_id)
            kind = "Personal"
        elif r.schedule_type == MASTER and include_master and r.schedule_id in master_titles:
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


def _viewer_run_log(p) -> list[dict]:
    uid = _uid(p.email)
    return _recent_run_log(
        personal_ids={s.id for s in _repo().list_for_user(uid)},
        include_master=_authz().can_see_company_schedules(p),
        viewer=p, viewer_id=uid,
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
    if "skip_sabbath" in src:
        out["skip_sabbath"] = _as_bool(src.get("skip_sabbath"))
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


def _master_page_context(p, uid: int) -> dict:
    authz = _authz()
    items = []
    for s in _master().list_shared():
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
            "is_shared": True,
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
    }



def _history_extra(runs, p) -> dict:
    from web.data.repositories.delivery_legs import DeliveryLegRepository
    from web.delivery.states import UNKNOWN
    repo = DeliveryLegRepository(_db())
    legs_by_run = {r.id: repo.list_for_run(r.id) for r in runs}
    return {
        "legs_by_run": legs_by_run,
        "can_reconcile": _authz().is_privileged(p),
        "unknown_status": UNKNOWN,
    }


from web.auth.decorators import require_login as _require_login
from flask import jsonify as _jsonify


@schedules_bp.post("/api/delivery-legs/<attempt_key>/reconcile")
@_require_login
def reconcile_delivery_leg(attempt_key: str):
    """Operator: mark an unknown send as received, or reopen it to send again."""
    from web.data.repositories.delivery_legs import DeliveryLegRepository
    from web.data.repositories.jobs import QueueAdmissionError
    from web.delivery.states import UNKNOWN
    from web.scheduling.jobs import enqueue_leg_retry

    p = _principal()
    if not _authz().is_privileged(p):
        abort(403, description="Admins and developers can reconcile unknown sends.")
    body = request.get_json(silent=True) or {}
    action = (request.form.get("action") or body.get("action") or "").strip()
    legs = DeliveryLegRepository(_db())
    leg = legs.get(attempt_key)
    if leg is None:
        abort(404, description="Unknown delivery leg")
    if action == "mark_sent":
        if leg.status not in (UNKNOWN, "accepted"):
            abort(400, description="Only unknown sends can be marked received.")
        legs.mark_sent(attempt_key, row_count=leg.row_count, remote_id=leg.remote_id)
    elif action == "retry":
        prev = leg.status
        err = leg.error
        job_repo = current_app.config["JOB_REPO"]
        if leg.job_id:
            running = job_repo.get(leg.job_id)
            if running is not None and running.status in ("queued", "running"):
                abort(409, description="That send is still running.")

        def _restore(reason: str) -> None:
            if prev == UNKNOWN:
                legs.mark_unknown(attempt_key, err or reason)
            else:
                legs.mark_failed(attempt_key, err or reason)

        if not legs.reopen_for_retry(attempt_key):
            abort(400, description="Only unknown or failed legs can be retried.")
        try:
            queued = enqueue_leg_retry(job_repo, leg)
        except QueueAdmissionError as exc:
            _restore(str(exc))
            abort(503, description=str(exc))
        if not queued:
            _restore("retry unavailable")
            abort(400, description="Cannot retry this send; the original job is gone.")
    else:
        abort(400, description="action must be mark_sent or retry")
    nxt = request.form.get("next") or request.args.get("next") or ""
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return _jsonify({"ok": True, "attempt_key": attempt_key, "action": action})


from web.blueprints import schedule_personal as _schedule_personal  # noqa: F401, E402
from web.blueprints import schedule_company as _schedule_company  # noqa: F401, E402
