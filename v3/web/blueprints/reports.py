"""Reports: list, view, and the run/poll/result/export JSON API.

Thin by design. Routes authenticate, authorize (the single Authorization
layer), enqueue a durable job, and read back the one cache. The on-screen
interactive table is driven entirely by report.js against this JSON API; the
math + column shape live in report_engine, the orchestration in
web.reporting.report_service.

Scope note: the principal's visible-salesman scope is folded into the cache key
(scope-safe cache) AND the dedup key, so two users with different scope never
share a cached payload. Builders filter facts to the user's scope at build time.
The result endpoint also verifies scope compatibility so a demoted user cannot
read stale wider-scoped cached data.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import io
import os
import socket
import time
from urllib.parse import urlencode, urlparse

from report_engine import registry
from report_engine.registry import ReportStatus
from report_engine.lib import salesman_key
from report_engine.reports import customer_last_order as clo
from web.auth.decorators import require_login
from web.auth.session import current_principal
from web.data.repositories.company_views import CompanyView, CompanyViewRepository
from web.scheduling.company_layouts import params_without_window
from web.data.repositories.report_defaults import (
    DEFAULT_VIEW_NAME,
    ReportDefault,
    ReportDefaultRepository,
)
from web.data.repositories.saved_reports import SavedReport, SavedReportRepository
from web.data.repositories.users import User, UserRepository
from web.delivery.email import split_recipients
from web.delivery.graph_errors import graph_error_message
from web.delivery.jobs import enqueue_delivery
from web.reporting import params as P
from web.reporting.export_jobs import EXPORT_JOB_TYPE, enqueue_export
from web.reporting.jobs import enqueue_report_run
from web.reporting.report_service import drop_commissions_tab

reports_bp = Blueprint("reports", __name__)

# Which filter inputs each report exposes (rendered by report_view.html and read
# by report.js). Reports with a fixed server-side window expose none.
REPORT_FILTERS: dict[str, tuple[str, ...]] = {
    "ordered": ("period", "status", "customers", "salesman"),
    "invoiced": ("period", "customers", "salesman"),
    "salesman": ("year", "salesman"),
    "number_4": ("n4_mode",),
    "item_averages": (),
    "customer_activity": ("salesman",),
    "sales_by_state": ("year",),
}

PERIOD_OPTIONS: tuple[tuple[str, str], ...] = (
    ("all_time", "All Time"),
    ("mtd", "Month to Date"),
    ("last_month", "Last Month"),
    ("ytd", "Year to Date"),
    ("this_week", "This Week"),
    ("last_7_days", "Last 7 Days"),
    ("daily", "Yesterday"),
    ("custom", "Custom Range"),
)

# Number 4's one question: which rolling-12 view(s) to build. "Both" fetches
# each view from its own stored procedure; each view shows 12-month + YTD tabs.
N4_MODE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("both", "Both"),
    ("by_customer", "By Customer"),
    ("by_item", "By Item"),
)

# Sales order status filter (Ordered report). Empty value = all statuses.
STATUS_OPTIONS: tuple[tuple[str, str], ...] = (
    ("", "All Statuses"),
    ("Open order", "Open"),
    ("Delivered", "Delivered"),
    ("Invoiced", "Invoiced"),
    ("Cancelled", "Cancelled"),
)


# --- helpers --------------------------------------------------------------- #

def _authz():
    return current_app.config["AUTHZ"]


def _job_repo():
    return current_app.config["JOB_REPO"]


def _cache():
    return current_app.config["REPORT_CACHE"]


def _exports():
    return current_app.config["EXPORT_REPO"]


def _lookups():
    return current_app.config["LOOKUP_SERVICE"]


def _saved_repo() -> SavedReportRepository:
    return SavedReportRepository(current_app.config["DB"])


def _defaults_repo() -> ReportDefaultRepository:
    return ReportDefaultRepository(current_app.config["DB"])


def _company_views_repo() -> CompanyViewRepository:
    return CompanyViewRepository(current_app.config["DB"])


def _sharepoint():
    return current_app.config["SHAREPOINT_SERVICE"]


def _company_view_dict(v: CompanyView, p) -> dict:
    return {
        "id": v.id, "report_key": v.report_key, "name": v.name,
        "params": v.params, "layout": v.layout, "kind": "company",
        "can_edit": _authz().can_see_company_schedules(p),
        "updated_at": v.updated_at,
    }


def _preset_dict(s: SavedReport, owner: User | None = None) -> dict:
    out = {"id": s.id, "report_key": s.report_key, "name": s.name,
           "params": s.params, "layout": s.layout, "created_at": s.created_at,
           "owner_user_id": s.user_id}
    if owner is not None:
        out["owner_name"] = owner.display_name or owner.email
    return out


def _default_dict(report_key: str, p, row: ReportDefault | None) -> dict:
    return {
        "id": "default",
        "name": DEFAULT_VIEW_NAME,
        "report_key": report_key,
        "params": dict(row.params) if row else {},
        "layout": dict(row.layout) if row else {},
        "can_edit": _authz().can_see_company_schedules(p),
        "updated_at": row.updated_at if row else None,
    }


def _principal_or_401():
    p = current_principal()
    if p is None:
        abort(401, description="Sign in required")
    return p


def _require_developer_principal():
    p = _principal_or_401()
    if not _authz().is_developer(p):
        abort(403, description="Developer role required")
    return p


def _user_id(email: str) -> int | None:
    row = UserRepository(current_app.config["DB"]).get_by_email(email)
    return row.id if row else None


def _users_repo() -> UserRepository:
    return UserRepository(current_app.config["DB"])


def _preset_for_caller(preset_id: int, p) -> SavedReport:
    """Owner's preset, or any preset when the caller is an admin/developer."""
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    row = _saved_repo().get(preset_id, uid)
    if row is None and _authz().is_privileged(p):
        row = _saved_repo().get_any(preset_id)
    if row is None or not _authz().can_view_report(p, row.report_key):
        abort(404, description="Unknown preset")
    return row


def _owner_id_for_new_preset(body: dict, p, *, default_uid: int) -> int:
    raw = body.get("owner_user_id")
    if raw in (None, "", 0, "0"):
        return default_uid
    if not _authz().is_privileged(p):
        return default_uid
    try:
        want = int(raw)
    except (TypeError, ValueError):
        abort(400, description="owner_user_id must be a user id")
    owner = _users_repo().get_by_id(want)
    if owner is None or not owner.is_active:
        abort(400, description="Unknown user")
    return owner.id


def _save_for_users(p) -> list[dict]:
    if not _authz().is_privileged(p):
        return []
    me = (p.email or "").strip().lower()
    out = []
    for u in _users_repo().all_users():
        if (u.email or "").strip().lower() == me:
            continue
        out.append({"user_id": u.id, "name": u.display_name or u.email, "email": u.email})
    out.sort(key=lambda r: r["name"].lower())
    return out


def _built_spec_or_404(report_key: str):
    spec = registry.get(report_key)
    if spec is None or spec.status is not ReportStatus.BUILT:
        abort(404, description="Unknown report")
    return spec


def _owned_job_or_404(job_id: str, uid: int | None):
    # Fail closed: require a real current-user id AND an exact owner match. This
    # keeps NULL-owner (system/orphaned) jobs unreadable through the user APIs.
    job = _job_repo().get(job_id)
    if job is None or uid is None or job.owner_user_id != uid:
        abort(404, description="Unknown job")
    return job


def _job_scope_ok(p, job) -> bool:
    """True if p may still see a result built under job.params['visible_keys']."""
    current_keys = _authz().visible_salesman_keys(p)
    if current_keys is None:
        return True
    job_keys = job.params.get("visible_keys")
    if job_keys is None:
        return False
    normalized_current = {salesman_key(k) for k in current_keys}
    normalized_job = {salesman_key(k) for k in job_keys}
    return normalized_job.issubset(normalized_current)


def _deny_result_scope():
    abort(403, description="Result scope exceeds your current access; please re-run")


def _assert_scope_compatible(p, job):
    """Deny if the user's current scope is narrower than the job's build scope.

    Prevents a demoted user from reading a cached result that contains data
    they can no longer access (e.g. admin -> salesman demotion).
    """
    if not _job_scope_ok(p, job):
        _deny_result_scope()


def _export_source_job(export_job):
    sid = (export_job.params or {}).get("source_job_id")
    return _job_repo().get(sid) if sid else None


def _export_in_scope(p, export_job) -> bool:
    source = _export_source_job(export_job)
    return source is not None and _job_scope_ok(p, source)


def _selected_customer_accounts(params: dict) -> list[str]:
    """Extract customer account list from filter params (same format as the UI sends)."""
    c = (params or {}).get("customers")
    if isinstance(c, (list, tuple)):
        return [str(x).strip() for x in c if str(x).strip()]
    if c:
        return [s.strip() for s in str(c).split(",") if s.strip()]
    return []


# --- pages ----------------------------------------------------------------- #

@reports_bp.get("/")
@require_login
def reports_list():
    p = _principal_or_401()
    authz = _authz()
    built = [s for s in registry.built_reports() if authz.can_view_report(p, s.key)]
    backlog = list(registry.backlog_reports())
    return render_template(
        "reports_list.html", active_tab="reports",
        built_reports=built, backlog_reports=backlog, presets=_my_presets(p),
        company_views=_company_view_cards(p),
    )


def _my_presets(p) -> list[dict]:
    """The current user's presets as home-page cards (deep-link 'Open' URLs)."""
    uid = _user_id(p.email)
    if uid is None:
        return []
    authz = _authz()
    titles = {s.key: s.title for s in registry.built_reports()}
    out: list[dict] = []
    for s in _saved_repo().list_for_user(uid):
        if not authz.can_view_report(p, s.report_key):
            continue
        q: dict = {}
        for k, v in (s.params or {}).items():
            q[k] = ",".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)
        q["preset"] = s.id
        out.append({
            "id": s.id, "name": s.name, "report_key": s.report_key,
            "report_title": titles.get(s.report_key, s.report_key),
            "url": url_for("reports.report_view", report_key=s.report_key) + "?" + urlencode(q),
        })
    return out


def _company_view_cards(p) -> list[dict]:
    """Company-wide views as home-page cards (deep-link Open URLs)."""
    authz = _authz()
    if not authz.can_see_company_views(p):
        return []
    titles = {s.key: s.title for s in registry.built_reports()}
    out: list[dict] = []
    for v in _company_views_repo().list_all():
        if not authz.can_view_report(p, v.report_key):
            continue
        q: dict = {}
        for k, val in (v.params or {}).items():
            q[k] = ",".join(map(str, val)) if isinstance(val, (list, tuple)) else str(val)
        q["cview"] = v.id
        out.append({
            "id": v.id, "name": v.name, "report_key": v.report_key,
            "report_title": titles.get(v.report_key, v.report_key),
            "url": url_for("reports.report_view", report_key=v.report_key) + "?" + urlencode(q),
        })
    return out


@reports_bp.get("/reports/<report_key>")
@require_login
def report_view(report_key: str):
    p = _principal_or_401()
    spec = _built_spec_or_404(report_key)
    # In-app reports (customer picker driven) have their own pages.
    if spec.in_app and report_key == "customer_last_order":
        return redirect(url_for("reports.customer_last_order_pick"))
    authz = _authz()
    authz.assert_report_runnable(p, report_key)
    return render_template(
        "report_view.html", active_tab="reports", report=spec,
        filters=REPORT_FILTERS.get(report_key, ()), period_options=PERIOD_OPTIONS,
        status_options=STATUS_OPTIONS, year_options=_year_options(),
        n4_mode_options=N4_MODE_OPTIONS,
        is_developer=authz.is_developer(p),
        is_privileged=authz.is_privileged(p),
        user_email=p.email,
        user_name=p.name or p.email,
        save_for_users=_save_for_users(p),
        has_sharepoint=authz.is_privileged(p) and authz.has_sharepoint_access(p),
        hide_commissions=not authz.may_see_commissions(p),
        can_edit_default=authz.can_see_company_schedules(p),
    )


def _year_options() -> list[int]:
    """Descending years for the year picker (current back to D365 go-live year)."""
    from report_engine.dates import D365_GO_LIVE, today_eastern

    return list(range(today_eastern().year, D365_GO_LIVE.year - 1, -1))


# --- JSON API -------------------------------------------------------------- #

@reports_bp.post("/api/reports/<report_key>/run")
@require_login
def run_report(report_key: str):
    p = _principal_or_401()
    spec = _built_spec_or_404(report_key)
    authz = _authz()
    authz.assert_report_runnable(p, report_key)

    params = request.get_json(silent=True)
    if not isinstance(params, dict):
        params = request.form.to_dict()

    # Validate selected customers: resync if unknown, error if still missing.
    selected = _selected_customer_accounts(params)
    if selected:
        still_unknown = _lookups().ensure_customers(selected)
        if still_unknown:
            abort(400, description=f"Unknown customer(s): {', '.join(still_unknown)}")

    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    visible = authz.visible_salesman_keys(p)
    params = _params_for_viewer(p, report_key, params)
    job_id = enqueue_report_run(
        _job_repo(), report_key=report_key, identity=p.email,
        visible_salesman_keys=visible, builder_version=spec.builder_version,
        params=params, owner_user_id=uid,
    )

    # In prod the background worker drains the queue; only in non-prod (no poller)
    # do we run it inline so a local dev poll resolves without a worker thread.
    worker = current_app.config["JOB_WORKER"]
    if not worker.running and not current_app.config["APP_CONFIG"].is_prod:
        worker.drain()

    return jsonify({"job_id": job_id}), 202


@reports_bp.get("/api/jobs/<job_id>")
@require_login
def job_status(job_id: str):
    p = _principal_or_401()
    job = _owned_job_or_404(job_id, _user_id(p.email))
    return jsonify({
        "job_id": job.id, "status": job.status, "progress": job.progress,
        "error": job.error, "result_ref": job.result_ref,
    })


@reports_bp.post("/api/jobs/<job_id>/cancel")
@require_login
def cancel_job(job_id: str):
    """Cancel a still-running (or queued) report run the user is watching.

    Owner-checked like the status route. Returns whether the job was active to
    cancel; if it already finished, we report its current status so the screen
    can show the result instead of an error.
    """
    p = _principal_or_401()
    job = _owned_job_or_404(job_id, _user_id(p.email))
    cancelled = _job_repo().cancel(job_id)
    return jsonify({"cancelled": cancelled,
                    "status": "cancelled" if cancelled else job.status})


@reports_bp.get("/api/reports/result/<job_id>")
@require_login
def report_result(job_id: str):
    p = _principal_or_401()
    job = _owned_job_or_404(job_id, _user_id(p.email))
    _authz().assert_report_runnable(p, job.params.get("report_key"))
    _assert_scope_compatible(p, job)
    if job.status != "success":
        return jsonify({"status": job.status, "error": job.error}), 409
    cached = _cache().get(job.result_ref)
    if cached is None:
        abort(404, description="Result expired; please re-run")
    payload = cached.payload
    if not _authz().may_see_commissions(p):
        payload = drop_commissions_tab(payload)
    return jsonify(payload)


# How long a finished run stays resumable without Keep.
_RECENT_DONE_SECONDS = 48 * 3600
_KEEP_SECONDS = 30 * 86400
_KEEP_CAP = 5


def _age_seconds(ts: str | None, now: datetime | None = None) -> int | None:
    """Seconds since a stored timestamp. Handles both the naive 'YYYY-MM-DD
    HH:MM:SS' that SQLite writes for created_at and the tz-aware ISO that the
    job repo writes for finished_at."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return int((now - dt).total_seconds())


def _kept_still_valid(kept_until: str | None, now: datetime) -> bool:
    if not kept_until:
        return False
    try:
        dt = datetime.fromisoformat(kept_until)
    except ValueError:
        return False
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt > now


@reports_bp.get("/api/reports/active")
@require_login
def active_report_runs():
    """The current user's report runs that are still going (queued/running) or
    finished recently / Kept. Drives the always-on status bar and the
    resume-on-return behaviour. Owner-scoped: only the caller's own jobs."""
    p = _principal_or_401()
    uid = _user_id(p.email)
    if uid is None:
        return jsonify({"jobs": []})
    titles = {s.key: s.title for s in registry.built_reports()}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    jobs = []
    for r in _job_repo().report_runs_for_user(uid, limit=30):
        status = r["status"]
        kept_until = r.get("kept_until")
        if status not in ("queued", "running"):
            if _kept_still_valid(kept_until, now):
                pass
            else:
                age = _age_seconds(r["finished_at"] or r["created_at"], now)
                if age is None or age > _RECENT_DONE_SECONDS:
                    continue
        rkey = json.loads(r["params_json"] or "{}").get("report_key")
        jobs.append({
            "job_id": r["id"], "report_key": rkey,
            "title": titles.get(rkey, rkey or "Report"),
            "status": status, "progress": r["progress"] or 0,
            "age_seconds": _age_seconds(r["created_at"], now),
            "created_at": r["created_at"],
            "finished_at": r["finished_at"],
            "kept_until": kept_until or None,
            "kept": _kept_still_valid(kept_until, now),
            "keep_name": (r["keep_name"] or "").strip() if "keep_name" in r.keys() else "",
        })
    return jsonify({"jobs": jobs})


@reports_bp.post("/api/reports/runs/<job_id>/keep")
@require_login
def keep_report_run(job_id: str):
    """Extend a finished run's resume window to 30 days (cap 5 Kept per user)."""
    p = _principal_or_401()
    uid = _user_id(p.email)
    job = _owned_job_or_404(job_id, uid)
    if job.status != "success":
        abort(409, description="Only a finished report can be kept")
    kept_until = (datetime.now(timezone.utc) + timedelta(seconds=_KEEP_SECONDS)).isoformat()
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "").strip()[:80]
    ok = _job_repo().keep_run(job_id, uid, kept_until=kept_until, name=name, cap=_KEEP_CAP)
    if not ok:
        abort(404, description="Unknown job")
    return jsonify({"job_id": job_id, "kept_until": kept_until, "kept": True, "keep_name": name})


@reports_bp.post("/api/reports/<report_key>/export/<job_id>")
@require_login
def export_report(report_key: str, job_id: str):
    """Kick off a BACKGROUND export of an already-run report and return the export
    job id. Big workbooks took minutes and timed out the request; now the worker
    builds the .xlsx off-thread (streaming) and the user downloads it after,
    without losing it if they navigate away. Body is the viewer's serialized
    layout so the file mirrors the screen."""
    p = _principal_or_401()
    spec = _built_spec_or_404(report_key)
    uid = _user_id(p.email)
    job = _owned_job_or_404(job_id, uid)
    if job.params.get("report_key") != report_key:
        abort(404, description="Unknown job")
    _authz().assert_report_runnable(p, report_key)
    _assert_scope_compatible(p, job)
    if job.status != "success":
        abort(409, description="Report is not ready to export")
    if not _cache().exists(job.result_ref):  # cheap presence check (no payload deserialize)
        abort(404, description="Result expired; please re-run")
    layout = request.get_json(silent=True)
    if not isinstance(layout, dict):  # ignore missing/malformed bodies (e.g. a JSON array)
        layout = {}
    export_id = enqueue_export(
        _job_repo(), owner_user_id=uid, source_job_id=job_id, report_key=report_key,
        report_name=spec.title, layout=layout,
    )
    # Non-prod has no background poller; drain inline so a local export resolves.
    worker = current_app.config["JOB_WORKER"]
    if not worker.running and not current_app.config["APP_CONFIG"].is_prod:
        worker.drain()
    return jsonify({"export_id": export_id}), 202


@reports_bp.get("/api/reports/exports/<export_id>/download")
@require_login
def download_export(export_id: str):
    """Stream a finished background export. Owner-checked via the job row; the
    blob lives in cache.db keyed by the export id."""
    p = _principal_or_401()
    job = _owned_job_or_404(export_id, _user_id(p.email))
    if job.type != EXPORT_JOB_TYPE:
        abort(404, description="Unknown export")
    _authz().assert_report_runnable(p, job.params.get("report_key"))
    if not _export_in_scope(p, job):
        _deny_result_scope()
    if job.status != "success":
        abort(409, description="Export is not ready yet")
    found = _exports().content(export_id)
    if found is None:
        abort(404, description="Export expired; please export again")
    filename, data = found
    return send_file(
        io.BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name=filename,
    )


@reports_bp.get("/api/reports/exports")
@require_login
def list_exports():
    """The current user's recent background exports (for the 'Recent exports'
    panel): newest first, with status + size so finished files are re-downloadable
    in seconds."""
    p = _principal_or_401()
    uid = _user_id(p.email)
    if uid is None:
        return jsonify({"exports": []})
    authz = _authz()
    # Re-check live report access so a revoked user can't even see old export
    # metadata/titles (download is already owner+authz gated separately).
    jobs = [j for j in _job_repo().list_for_user(uid, limit=100)
            if j.type == EXPORT_JOB_TYPE
            and authz.can_view_report(p, j.params.get("report_key", ""))][:15]
    jobs = [j for j in jobs if _export_in_scope(p, j)]
    metas = _exports().metas_for([j.id for j in jobs if j.status == "success"])
    titles = {s.key: s.title for s in registry.built_reports()}
    out = []
    for j in jobs:
        rk = j.params.get("report_key", "")
        m = metas.get(j.id)
        out.append({
            "export_id": j.id, "status": j.status, "progress": j.progress,
            "report_key": rk, "report_title": titles.get(rk, rk),
            "error": j.error or "",
            "filename": m.filename if m else "",
            "size_bytes": m.size_bytes if m else 0,
            "built_at": m.built_at if m else "",
            "ready": bool(m),
        })
    return jsonify({"exports": out})


# --- Customer's Last Order (in-app, customer-picker driven) ---------------- #

_CLO_KEY = "customer_last_order"


def _report_service():
    return current_app.config["REPORT_SERVICE"]


def _assert_clo_access(p):
    """Page access: per-report grant (or privileged). Customer-level scope is
    enforced separately, per fetched customer, in the view itself."""
    _built_spec_or_404(_CLO_KEY)
    _authz().assert_can_view_report(p, _CLO_KEY)


def _visible_customers(p, salesman: str | None) -> list[dict]:
    """Customer picker list, narrowed to the principal's visible salesman scope."""
    customers = _lookups().customers(salesman)
    keys = _authz().visible_salesman_keys(p)
    if keys is None:
        return customers
    return [c for c in customers if salesman_key(c.get("salesman")) in keys]


@reports_bp.get("/report/customer-last-order")
@require_login
def customer_last_order_pick():
    p = _principal_or_401()
    _assert_clo_access(p)
    authz = _authz()
    # Admin/dev (unrestricted) get a salesman picker; scoped users don't need one.
    show_picker = authz.visible_salesman_keys(p) is None
    return render_template(
        "customer_last_order_pick.html", active_tab="reports",
        report=registry.get(_CLO_KEY), show_salesman_picker=show_picker,
    )


@reports_bp.get("/api/report/customer-last-order/customers")
@require_login
def customer_last_order_customers():
    p = _principal_or_401()
    _assert_clo_access(p)
    salesman = (request.args.get("salesman") or "").strip() or None
    return jsonify({"customers": _visible_customers(p, salesman)})


@reports_bp.get("/api/report/customer-last-order/salesmen")
@require_login
def customer_last_order_salesmen():
    p = _principal_or_401()
    _assert_clo_access(p)
    salesmen = _lookups().salesmen()
    keys = _authz().visible_salesman_keys(p)
    if keys is not None:  # scoped users only see their own salesmen (endpoint is callable directly)
        salesmen = [s for s in salesmen if salesman_key(s.get("key")) in keys]
    return jsonify({"salesmen": salesmen})


def _clo_rows_or_403(p, account: str):
    """Resolve the customer authoritatively, enforce scope, then fetch last orders.

    Returns (rows, customer_dict). Scope is checked against the CUSTOMER MASTER's
    sales group (LookupService), never the order lines — blank Salesman on a line
    must not deny a valid customer or skip authorization on empty history. When the
    master knows the customer we authorize on its group even with zero orders; when
    it can't resolve the account we fall back to Salesman on the SP rows and only
    authorize when there ARE rows (an empty unknown account leaks nothing).
    """
    from report_engine.lib import first_of, text as _text

    info = _lookups().customer(account)
    rows = _report_service().last_order_rows(account)
    if info is not None:
        sales_group, name = info["salesman"], info["name"]
        _authz().assert_can_view_customer(p, sales_group)
    else:
        sales_group = ""
        name = ""
        for r in rows:
            if not sales_group:
                sales_group = _text(first_of(r, "Salesman", "SalesGroup"))
            if not name:
                name = _text(first_of(r, "Customer Name", "CustomerName", "customername"))
            if sales_group and name:
                break
        if rows:
            _authz().assert_can_view_customer(p, sales_group)
    return rows, {"account": account, "name": name or account, "sales_group": sales_group}


@reports_bp.get("/api/report/customer-last-order/<account>/recent-invoiced")
@require_login
def customer_last_order_recent_invoiced(account: str):
    p = _principal_or_401()
    _assert_clo_access(p)
    rows, _ = _clo_rows_or_403(p, account)
    orders = [
        {"order_number": o.order_number, "order_date": o.order_date,
         "status": o.status, "customer_req": o.customer_req, "order_name": o.order_name}
        for o in clo.logical_orders(rows)
    ]
    return jsonify({"orders": orders})


@reports_bp.get("/report/customer-last-order/<account>")
@require_login
def customer_last_order_view(account: str):
    p = _principal_or_401()
    _assert_clo_access(p)

    requested = [o.strip() for o in (request.args.get("orders") or "").split(",") if o.strip()]
    try:
        rows, customer = _clo_rows_or_403(p, account)
        view = clo.build(rows, requested_orders=requested)
    except Exception as exc:  # noqa: BLE001 - render a clean error card, never 500
        if getattr(exc, "status_code", None) == 403:
            raise
        current_app.logger.exception("customer last order failed for %s", account)
        return render_template(
            "customer_last_order_view.html", active_tab="reports",
            customer={"account": account, "name": account, "sales_group": ""},
            view=None, error=str(exc),
        )
    return render_template(
        "customer_last_order_view.html", active_tab="reports",
        customer=customer, view=view, error=None,
    )


@reports_bp.get("/report/customer-last-order/<account>/export")
@require_login
def customer_last_order_export(account: str):
    """Excel or PDF of the current Last Order view (format=xlsx|pdf)."""
    from openpyxl import Workbook
    from web.reporting.last_order_export import last_order_pdf

    p = _principal_or_401()
    _assert_clo_access(p)
    fmt = (request.args.get("format") or "xlsx").strip().lower()
    if fmt not in ("xlsx", "pdf"):
        abort(400, description="format must be xlsx or pdf")
    requested = [o.strip() for o in (request.args.get("orders") or "").split(",") if o.strip()]
    rows, customer = _clo_rows_or_403(p, account)
    view = clo.build(rows, requested_orders=requested)
    if not view or not view.primary:
        abort(404, description="No order data to export")

    primary = view.primary
    name = customer.get("name") or account
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)[:40]
    primary_dict = {
        "order_number": primary.order_number,
        "order_date": primary.order_date,
        "salesman": primary.salesman,
    }
    line_dicts = [
        {
            "item": ln.item, "description": ln.description,
            "qty_ordered": ln.qty_ordered, "qty_shipped": ln.qty_shipped,
            "qty_cancelled": ln.qty_cancelled, "sales_price": ln.sales_price,
            "total": ln.total,
        }
        for ln in (view.lines or [])
    ]
    if fmt == "pdf":
        data = last_order_pdf(
            customer_name=name, account=account, primary=primary_dict,
            display_po=view.display_po or "", lines=line_dicts,
            totals=view.totals or {},
        )
        return send_file(
            io.BytesIO(data), mimetype="application/pdf", as_attachment=True,
            download_name=f"Last_Order_{safe}.pdf",
        )

    wb = Workbook()
    ws = wb.active
    ws.title = "Last Order"
    ws.append(["Customer", name, "Account", account])
    ws.append(["Order", primary.order_number, "Date", primary.order_date,
               "PO", view.display_po or ""])
    ws.append([])
    ws.append(["Item #", "Description", "Qty Ordered", "Qty Shipped",
               "Qty Cancelled", "Sales Price", "Total"])
    for line in line_dicts:
        ws.append([
            line["item"], line["description"],
            line["qty_ordered"], line["qty_shipped"], line["qty_cancelled"],
            line["sales_price"], line["total"],
        ])
    totals = view.totals or {}
    ws.append([
        "TOTALS", "", totals.get("qty_ordered"), totals.get("qty_shipped"),
        totals.get("qty_cancelled"), "", totals.get("total"),
    ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"Last_Order_{safe}.xlsx",
    )


# --- filter lookups (dropdown data + live API preview) --------------------- #

@reports_bp.get("/api/reports/lookups/status")
@require_login
def lookup_status():
    """Populate progress for the customer/salesman dropdowns (form polls this)."""
    _principal_or_401()
    return jsonify(_lookups().status())


@reports_bp.get("/api/reports/<report_key>/salesmen")
@require_login
def report_salesmen(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    visible = _authz().visible_salesman_keys(p)
    all_sm = _lookups().salesmen()
    if visible is not None:
        all_sm = [s for s in all_sm if salesman_key(s["key"]) in visible]
    return jsonify({"salesmen": all_sm})


@reports_bp.get("/api/reports/<report_key>/customers")
@require_login
def report_customers(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    salesman = (request.args.get("salesman") or "").strip() or None
    visible = _authz().visible_salesman_keys(p)
    return jsonify({"customers": _lookups().customers_visible(visible, salesman)})


@reports_bp.get("/api/reports/<report_key>/years")
@require_login
def report_years(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    return jsonify({"years": _year_options()})


@reports_bp.post("/api/reports/<report_key>/preview-body")
@require_login
def preview_body(report_key: str):
    """Show the exact request that would be sent to the on-prem Reporting API.

    Read-only: builds the SP params from the current filters without calling the
    API, so the form can surface a live "this is what we'll ask for" panel.
    Developer-only -- the panel is a dev tool, not a user-facing feature.
    """
    p = _require_developer_principal()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)

    filters = request.get_json(silent=True)
    if not isinstance(filters, dict):
        filters = request.form.to_dict()

    cfg = current_app.config["APP_CONFIG"]
    base = (cfg.reporting_api_base_url or "").rstrip("/")
    try:
        report_id = P.report_id_for(report_key)
        # Number 4's SP depends on the View filter; "both" previews the first
        # of its two calls (the By Customer SP).
        if report_key == "number_4" and P.number_4_mode(filters) == "by_item":
            report_id = P.NUMBER_4_BY_ITEM_SP
        body = P.translate(report_key, filters)
        url = f"{base}/api/reports/{report_id}/run" if base else None
        return jsonify({
            "report_id": report_id, "method": "POST", "url": url,
            "body": body, "configured": bool(base and cfg.reporting_api_key),
        })
    except KeyError as exc:
        return jsonify({
            "report_id": None, "method": "POST", "url": None, "body": {},
            "configured": bool(base and cfg.reporting_api_key),
            "warning": str(exc),
        })


def _probe_reporting_api(cfg, *, run_live: bool = False) -> dict:
    """Hit the on-prem Reporting API straight from this request (no worker, no
    cache, no dedup) so we can prove whether our calls leave the app and reach
    the endpoint at all. Checks, all with short timeouts so the request can't hang:

      tcp  - open a raw socket to host:port. Proves the Azure Hybrid Connection
             tunnel reaches the on-prem listener (no HTTP, no stored procedure).
      http - a GET to the API root. ANY status code means the API process
             answered and the DBA should see this request land. A connect/read
             timeout here (with tcp ok) points at the API, not the tunnel.
      live_query (only when run_live) - POST a real but tiny reference-data SP
             (customer_master, no date window) with a short read timeout and no
             retries. This is the ONLY check that proves the stored-proc layer
             actually executes and returns - reachability can't. It's also a call
             the DBA can watch land on the SQL box.

    Never returns the API key. host:port is operational info, not a secret.
    """
    base = (cfg.reporting_api_base_url or "").rstrip("/")
    out: dict = {"configured": bool(base and cfg.reporting_api_key),
                 "host": None, "port": None, "tcp": None, "http": None}
    if not base:
        return out
    parsed = urlparse(base)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    out["host"], out["port"] = host, port

    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=5):
            out["tcp"] = {"ok": True, "ms": int((time.monotonic() - t0) * 1000)}
    except Exception as exc:  # noqa: BLE001 - report the failure, don't raise
        out["tcp"] = {"ok": False, "ms": int((time.monotonic() - t0) * 1000),
                      "error": f"{type(exc).__name__}: {exc}"}

    import requests
    t1 = time.monotonic()
    try:
        r = requests.get(f"{base}/", timeout=(5, 10),
                         headers={"X-API-Key": cfg.reporting_api_key})
        out["http"] = {"ok": True, "status": r.status_code,
                       "ms": int((time.monotonic() - t1) * 1000)}
    except Exception as exc:  # noqa: BLE001 - report the failure, don't raise
        out["http"] = {"ok": False, "ms": int((time.monotonic() - t1) * 1000),
                       "error": f"{type(exc).__name__}: {exc}"}

    if run_live:
        t2 = time.monotonic()
        try:
            r = requests.post(
                f"{base}/api/reports/customer_master/run", json={},
                headers={"X-API-Key": cfg.reporting_api_key,
                         "Content-Type": "application/json"},
                timeout=(5, 25))
            body = r.json() if r.ok else None
            out["live_query"] = {
                "ok": r.ok, "status": r.status_code,
                "ms": int((time.monotonic() - t2) * 1000),
                "report_id": "customer_master",
                "row_count": (body or {}).get("row_count"),
            }
        except Exception as exc:  # noqa: BLE001 - report the failure, don't raise
            out["live_query"] = {"ok": False, "ms": int((time.monotonic() - t2) * 1000),
                                 "report_id": "customer_master",
                                 "error": f"{type(exc).__name__}: {exc}"}
    return out


@reports_bp.get("/api/reports/diagnostics/reporting-api")
@require_login
def reporting_api_diagnostics():
    """Admin/developer check: is the Reporting API reachable from the app right
    now, and is the job worker backed up? Answers 'why aren't our calls hitting
    the endpoint' without guessing. Developer-only (exposes the API host)."""
    p = _require_developer_principal()
    cfg = current_app.config["APP_CONFIG"]
    from web import is_background_leader_process
    worker = current_app.config["JOB_WORKER"]
    run_live = request.args.get("live") in ("1", "true", "yes")
    return jsonify({
        "reporting_api": _probe_reporting_api(cfg, run_live=run_live),
        "jobs": _job_repo().status_summary(),
        "claim_probe": _claim_probe(current_app.config["DB"]),
        "me": {"email": p.email, "user_id": _user_id(p.email), "role": p.role},
        "recent_jobs": _recent_jobs(current_app.config["DB"]),
        "wiring": _worker_wiring(worker, current_app.config["DB"]),
        "worker": {
            "pid": os.getpid(),
            "is_leader_process": is_background_leader_process(),
            **worker.health(),
        },
    })


@reports_bp.get("/api/reports/diagnostics/reconcile-salesman-invoiced")
def reconcile_salesman_invoiced_diagnostic():
    """One-shot: monthly_salesman_yoy vs invoiced_report Total Invoice.

    Gated by env DIAG_RECONCILE_KEY (?k=...). When the key is unset, returns 404.
    Optional ?scope=ty|ly|all (default all). Split ty/ly avoids App Service 230s
    gateway timeout when both invoiced windows are large.
    """
    import hmac

    expected = (os.environ.get("DIAG_RECONCILE_KEY") or "").strip()
    provided = (request.args.get("k") or "").strip()
    if (
        not expected
        or not provided
        or len(expected) != len(provided)
        or not hmac.compare_digest(expected, provided)
    ):
        abort(404)

    service = current_app.config.get("REPORT_SERVICE")
    client = getattr(service, "client", None) if service is not None else None
    if client is None or not getattr(client, "configured", False):
        return jsonify({"ok": False, "error": "Reporting API not configured"}), 503

    year = request.args.get("year", type=int)
    through = request.args.get("through_month", type=int)
    scope = (request.args.get("scope") or "all").strip().lower()
    only_month = request.args.get("month", type=int)
    if scope not in ("ty", "ly", "all"):
        return jsonify({"ok": False, "error": "scope must be ty, ly, or all"}), 400
    try:
        from web.reporting.reconcile_salesman import reconcile
        return jsonify(reconcile(
            client, year=year, through_month=through, scope=scope,
            only_month=only_month,
        ))
    except Exception as exc:  # noqa: BLE001 - surface to the caller for one-shot ops
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500


@reports_bp.get("/api/reports/diagnostics/reconcile-number4-invoiced")
def reconcile_number4_invoiced_diagnostic():
    """One-shot: Number 4 rolling-12 vs invoiced_report (subtotal + Total Invoice).

    Gated by env DIAG_RECONCILE_KEY (?k=...). Optional ?view=by_customer|by_item,
    ?month=1..12 (index into the rolling window, 1=oldest) for gateway-safe slices.
    """
    import hmac

    expected = (os.environ.get("DIAG_RECONCILE_KEY") or "").strip()
    provided = (request.args.get("k") or "").strip()
    if (
        not expected
        or not provided
        or len(expected) != len(provided)
        or not hmac.compare_digest(expected, provided)
    ):
        abort(404)

    service = current_app.config.get("REPORT_SERVICE")
    client = getattr(service, "client", None) if service is not None else None
    if client is None or not getattr(client, "configured", False):
        return jsonify({"ok": False, "error": "Reporting API not configured"}), 503

    view = (request.args.get("view") or "by_customer").strip().lower()
    if view not in ("by_customer", "by_item"):
        return jsonify({"ok": False, "error": "view must be by_customer or by_item"}), 400
    only_month = request.args.get("month", type=int)
    as_of_raw = (request.args.get("as_of") or "").strip()
    as_of = None
    if as_of_raw:
        try:
            from datetime import date as _date
            as_of = _date.fromisoformat(as_of_raw[:10])
        except ValueError:
            return jsonify({"ok": False, "error": "as_of must be YYYY-MM-DD"}), 400
    try:
        from web.reporting.reconcile_number4 import reconcile
        return jsonify(reconcile(
            client, as_of=as_of, view=view, only_month=only_month,
        ))
    except Exception as exc:  # noqa: BLE001 - surface to the caller for one-shot ops
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500


def _recent_jobs(db, limit: int = 10) -> list[dict]:
    """Last few jobs with owner + status, so 'Lost track of the job' can be told
    apart: a 404 on poll is either the job not existing or its owner_user_id not
    matching the caller. NULL-owner (system) jobs are unreadable through the user
    API by design - that mismatch shows up plainly here."""
    with db.precious() as conn:
        rows = conn.execute(
            "SELECT id, type, status, owner_user_id, created_at FROM jobs"
            " ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [
        {"id": r["id"], "type": r["type"], "status": r["status"],
         "owner_user_id": r["owner_user_id"], "created_at": r["created_at"]}
        for r in rows
    ]


@reports_bp.route("/api/reports/diagnostics/claim-once", methods=["GET", "POST"])
@require_login
def claim_once_diagnostic():
    """Developer-only: call the REAL worker.repo.claim_next() from this request
    thread (the poller calls the same method but always gets None). If this
    claims a job, the poller's failure is thread-specific; if it returns None,
    the method itself is the problem. Safe: a job this request claimed is set
    back to 'queued' so the actual handler never runs.

    GET is rejected: this writes the jobs table, so CSRF must apply (POST).
    """
    p = _require_developer_principal()
    if request.method == "GET":
        return jsonify({"error": "Claim-once writes the jobs table; POST required"}), 405
    from datetime import datetime, timezone
    db = current_app.config["DB"]
    with db.precious() as conn:
        sel = conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
        ).fetchone()
        out: dict = {"select_found_id": sel["id"] if sel else None}
        if sel:
            upd = conn.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE id=? AND status='queued'",
                (datetime.now(timezone.utc).isoformat(), sel["id"]),
            )
            out["update_rowcount"] = upd.rowcount
            verify = conn.execute(
                "SELECT status FROM jobs WHERE id=?", (sel["id"],)
            ).fetchone()
            out["status_after_update"] = verify["status"] if verify else None
            if upd.rowcount == 1:
                conn.execute(
                    "UPDATE jobs SET status='queued', started_at=NULL WHERE id=?",
                    (sel["id"],),
                )
                out["reverted"] = True
            else:
                out["reverted"] = False
    return jsonify(out)


@reports_bp.route("/api/reports/diagnostics/precious-repair", methods=["GET", "POST"])
@require_login
def precious_repair_diagnostic():
    """Developer-only. The jobs 'status' index disagrees with the table by id
    (a queued row found by status doesn't exist by id) - SQLite corruption from
    the old /home SMB WAL, carried into the restore. action=check reports
    integrity + index-vs-scan counts. action=backup dumps every table to a JSON
    file on /home (insurance before a wipe). action=reindex rebuilds indexes from
    the real table rows. action=delete-ghosts removes the stuck queued rows.
    action=rebuild-jobs drops + recreates the corrupt jobs table. All read the
    same precious.db the worker uses.

    GET may only run check (read-only). Mutating actions require POST so CSRF
    applies — a GET would let a cross-site link wipe queued jobs.
    """
    p = _require_developer_principal()
    db = current_app.config["DB"]
    body = request.get_json(silent=True) or {}
    action = (request.args.get("action") or body.get("action") or "check")
    if isinstance(action, str):
        action = action.strip() or "check"
    else:
        action = "check"
    if request.method == "GET" and action != "check":
        return jsonify({
            "error": "Mutating repair actions require POST",
            "action": action,
        }), 405
    out: dict = {"action": action}
    with db.precious() as conn:
        if action == "check":
            out["integrity_check"] = [r[0] for r in conn.execute("PRAGMA integrity_check(30)").fetchall()]
            out["quick_check"] = [r[0] for r in conn.execute("PRAGMA quick_check(30)").fetchall()]
            out["jobs_indexes"] = [
                {"seq": r[0], "name": r[1], "unique": r[2], "origin": r[3], "partial": r[4]}
                for r in conn.execute("PRAGMA index_list('jobs')").fetchall()
            ]
            # status index path vs forced full table scan - if these disagree the
            # index has ghost entries the table doesn't back.
            out["queued_via_index"] = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0]
            out["queued_via_table_scan"] = conn.execute(
                "SELECT COUNT(*) FROM jobs NOT INDEXED WHERE status='queued'").fetchone()[0]
        elif action == "reindex":
            conn.execute("REINDEX jobs")
            out["reindexed"] = True
            out["queued_via_index"] = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0]
            out["queued_via_table_scan"] = conn.execute(
                "SELECT COUNT(*) FROM jobs NOT INDEXED WHERE status='queued'").fetchone()[0]
        elif action == "delete-ghosts":
            deleted = conn.execute("DELETE FROM jobs WHERE status='queued'").rowcount
            out["deleted"] = deleted
            out["queued_remaining"] = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0]
        elif action == "backup":
            # Insurance before any wipe: dump every table's rows to a JSON file on
            # persistent /home storage. Each table is read independently so the one
            # corrupt table (jobs) can't abort the backup of the good rows.
            out["backup"] = _backup_precious(conn)
        elif action == "rebuild-jobs":
            # The jobs PK index is malformed (rows missing from it), so per-row
            # DELETE/REINDEX errors out. The jobs table is pure transient work-queue
            # history - no business data - so drop the whole table (frees the corrupt
            # b-trees wholesale, which DROP tolerates) and recreate it empty from its
            # own captured schema: a fresh PK index plus the status/dedup indexes.
            schema = [r[0] for r in conn.execute(
                "SELECT sql FROM sqlite_master WHERE tbl_name='jobs' AND sql IS NOT NULL"
                " ORDER BY (type='table') DESC").fetchall()]
            out["captured_schema"] = schema
            conn.execute("DROP TABLE jobs")
            for stmt in schema:
                conn.execute(stmt)
            out["rebuilt"] = True
            out["jobs_count"] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            out["integrity_check"] = [r[0] for r in conn.execute("PRAGMA integrity_check(30)").fetchall()]
        else:
            abort(400, description="action must be check, backup, reindex, delete-ghosts, or rebuild-jobs")
    return jsonify(out)


def _backup_precious(conn) -> dict:
    """Dump every table to a timestamped JSON file under /home (persistent across
    container recycles). Reads each table on its own so a corrupt table records an
    error instead of killing the whole backup. Returns the path + per-table counts."""
    import json
    from datetime import datetime, timezone

    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
        " AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    dump: dict = {"created_at": datetime.now(timezone.utc).isoformat(), "tables": {}}
    counts: dict = {}
    errors: dict = {}
    for table in tables:
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            dump["tables"][table] = [dict(r) for r in rows]
            counts[table] = len(rows)
        except Exception as exc:  # noqa: BLE001 - one bad table must not lose the rest
            errors[table] = f"{type(exc).__name__}: {exc}"

    backup_dir = "/home/site/v3data"
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(backup_dir, f"precious-backup-{stamp}.json")
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(dump, fh)
    os.replace(tmp, path)
    return {"path": path, "row_counts": counts, "errors": errors}


def _worker_wiring(worker, app_db) -> dict:
    """Is the poller running the code we think, against the DB we think? The
    poller's claim_next() returns None while an identical inline query in this
    same process finds the job. Dump the ACTUAL deployed source of claim_next
    (a stale .pyc on the wwwroot share would differ from the repo) and confirm
    the worker's repo points at the very same Database object/path as requests."""
    import inspect
    repo = worker.repo
    out: dict = {
        "worker_db_is_app_db": repo.db is app_db,
        "worker_db_path": str(getattr(repo.db, "precious_path", None)),
        "app_db_path": str(getattr(app_db, "precious_path", None)),
    }
    try:
        out["claim_next_source"] = inspect.getsource(type(repo).claim_next)
    except Exception as exc:  # noqa: BLE001 - best-effort introspection
        out["claim_next_source_error"] = f"{type(exc).__name__}: {exc}"
    try:
        out["claim_next_file"] = inspect.getsourcefile(type(repo).claim_next)
    except Exception:  # noqa: BLE001
        out["claim_next_file"] = None
    return out


def _claim_probe(db) -> dict:
    """The poller's claim_next() returns None even though status_summary() sees
    'queued' jobs in the SAME file/process. Run the EXACT read claim_next uses
    and dump the RAW status/created_at of every active row, so we can see what's
    different about these rows (hidden characters in status, a NULL/odd
    created_at that breaks ORDER BY, a value that only LOOKS like 'queued')."""
    with db.precious() as conn:
        picked = conn.execute(
            "SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
        ).fetchone()
        rows = conn.execute(
            "SELECT id, status, created_at, typeof(status) AS s_type,"
            " typeof(created_at) AS ca_type FROM jobs"
            " WHERE status IN ('queued', 'running') ORDER BY created_at LIMIT 20"
        ).fetchall()
        eq_count = conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE status = 'queued'"
        ).fetchone()["n"]
        total = conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
        jmode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    return {
        "db_file": _db_file_identity(db.precious_path),
        "journal_mode": jmode,
        "total_jobs": total,
        "claim_next_would_pick": picked["id"] if picked else None,
        "rows_where_status_equals_queued": eq_count,
        "active_rows": [
            {"id": r["id"], "status_repr": repr(r["status"]), "status_type": r["s_type"],
             "created_at_repr": repr(r["created_at"]), "created_at_type": r["ca_type"]}
            for r in rows
        ],
    }


def _db_file_identity(path) -> dict:
    """Inode/size/mtime of the precious.db file (and its -wal). If the leader and
    a follower report different inodes for the same path, they're literally
    reading different files - that's the whole bug. If same inode but a big -wal,
    the data may be sitting in a WAL the poller's connection isn't seeing."""
    out: dict = {"path": str(path)}
    for label, p in (("main", path), ("wal", path.with_name(path.name + "-wal"))):
        try:
            st = os.stat(p)
            out[label] = {"inode": st.st_ino, "size": st.st_size, "mtime": int(st.st_mtime)}
        except OSError:
            out[label] = None
    return out


# --- saved reports (presets) ----------------------------------------------- #

@reports_bp.get("/api/saved-reports")
@require_login
def saved_reports_list():
    """All of the current user's presets (across reports they can still view)."""
    p = _principal_or_401()
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    authz = _authz()
    items = [_preset_dict(s) for s in _saved_repo().list_for_user(uid)
             if authz.can_view_report(p, s.report_key)]
    return jsonify({"presets": items})


@reports_bp.get("/api/reports/<report_key>/presets")
@require_login
def report_presets(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    authz = _authz()
    company = (
        [_company_view_dict(v, p) for v in _company_views_repo().list_for_report(report_key)]
        if authz.can_see_company_views(p) else []
    )
    mine = [s for s in _saved_repo().list_for_user(uid) if s.report_key == report_key]
    payload: dict = {
        "default": _default_dict(report_key, p, _defaults_repo().get(report_key)),
        "company": company,
        "presets": [_preset_dict(s) for s in mine],
    }
    if authz.is_privileged(p):
        users = {u.id: u for u in _users_repo().all_users()}
        grouped: dict[int, dict] = {}
        order: list[int] = []
        for row in _saved_repo().list_all():
            if row.report_key != report_key or row.user_id == uid:
                continue
            owner = users.get(row.user_id)
            if owner is None:
                continue
            if owner.id not in grouped:
                grouped[owner.id] = {
                    "user_id": owner.id,
                    "name": owner.display_name or owner.email,
                    "email": owner.email,
                    "presets": [],
                }
                order.append(owner.id)
            grouped[owner.id]["presets"].append(_preset_dict(row, owner))
        others = [grouped[i] for i in order if grouped[i]["presets"]]
        others.sort(key=lambda g: g["name"].lower())
        payload["others"] = others
    return jsonify(payload)


@reports_bp.post("/api/reports/<report_key>/presets")
@require_login
def create_preset(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        abort(400, description="A preset name is required")
    if name.lower() == "default":
        abort(400, description="Default is the company view. Edit it from Saved views.")
    owner_id = _owner_id_for_new_preset(body, p, default_uid=uid)
    pid = _saved_repo().create(owner_id, report_key, name,
                               body.get("params") or {}, body.get("layout") or {})
    return jsonify({"id": pid, "name": name, "owner_user_id": owner_id}), 201


@reports_bp.get("/api/reports/presets/<int:preset_id>")
@require_login
def get_preset(preset_id: int):
    p = _principal_or_401()
    s = _preset_for_caller(preset_id, p)
    owner = _users_repo().get_by_id(s.user_id)
    return jsonify(_preset_dict(s, owner))


@reports_bp.patch("/api/reports/presets/<int:preset_id>")
@require_login
def update_preset(preset_id: int):
    p = _principal_or_401()
    existing = _preset_for_caller(preset_id, p)
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    if name is not None and not str(name).strip():
        abort(400, description="A preset name is required")
    if name is not None and str(name).strip().lower() == "default":
        abort(400, description="Default is the company view. Edit it from Saved views.")
    ok = _saved_repo().update(
        preset_id, existing.user_id,
        name=None if name is None else str(name).strip(),
        params=body["params"] if "params" in body else None,
        layout=body["layout"] if "layout" in body else None,
    )
    if not ok:
        abort(400, description="Could not save that view (the name may already be used)")
    updated = _saved_repo().get_any(preset_id)
    owner = _users_repo().get_by_id(existing.user_id)
    return jsonify(_preset_dict(updated, owner) if updated else {"id": preset_id})


@reports_bp.delete("/api/reports/presets/<int:preset_id>")
@require_login
def delete_preset(preset_id: int):
    p = _principal_or_401()
    existing = _preset_for_caller(preset_id, p)
    if not _saved_repo().delete(preset_id, existing.user_id):
        abort(404, description="Unknown preset")
    return jsonify({"deleted": True})


@reports_bp.get("/api/reports/<report_key>/default-view")
@require_login
def get_default_view(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    return jsonify(_default_dict(report_key, p, _defaults_repo().get(report_key)))


@reports_bp.put("/api/reports/<report_key>/default-view")
@require_login
def put_default_view(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    if not _authz().can_see_company_schedules(p):
        abort(403, description="Only managers and admins can change Default.")
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    body = request.get_json(silent=True) or {}
    row = _defaults_repo().upsert(
        report_key,
        params=body.get("params") if isinstance(body.get("params"), dict) else {},
        layout=body.get("layout") if isinstance(body.get("layout"), dict) else {},
        updated_by=uid,
    )
    return jsonify(_default_dict(report_key, p, row))


@reports_bp.get("/api/reports/<report_key>/company-views/<int:view_id>")
@require_login
def get_company_view(report_key: str, view_id: int):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    if not _authz().can_see_company_views(p):
        abort(403, description="You do not have access to company views.")
    row = _company_views_repo().get(view_id)
    if row is None or row.report_key != report_key:
        abort(404, description="Unknown company view")
    return jsonify(_company_view_dict(row, p))


@reports_bp.put("/api/reports/<report_key>/company-views")
@require_login
def put_company_view(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    if not _authz().can_see_company_views(p):
        abort(403, description="You do not have access to company views.")
    if not _authz().can_see_company_schedules(p):
        abort(403, description="Only managers and admins can change company views.")
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        abort(400, description="A view name is required")
    try:
        row = _company_views_repo().upsert(
            report_key, name,
            params=params_without_window(
                body.get("params") if isinstance(body.get("params"), dict) else {}),
            layout=body.get("layout") if isinstance(body.get("layout"), dict) else {},
            updated_by=uid,
        )
    except ValueError as exc:
        abort(400, description=str(exc))
    return jsonify(_company_view_dict(row, p))


@reports_bp.delete("/api/reports/<report_key>/company-views/<int:view_id>")
@require_login
def delete_company_view(report_key: str, view_id: int):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    if not _authz().can_see_company_views(p):
        abort(403, description="You do not have access to company views.")
    if not _authz().can_see_company_schedules(p):
        abort(403, description="Only managers and admins can change company views.")
    if not _company_views_repo().delete(view_id, report_key):
        abort(404, description="Unknown company view")
    return jsonify({"deleted": True})


# --- delivery: email now + SharePoint picker -------------------------------- #

@reports_bp.post("/api/reports/<report_key>/email-now")
@require_login
def email_now(report_key: str):
    p = _principal_or_401()
    spec = _built_spec_or_404(report_key)
    authz = _authz()
    authz.assert_report_runnable(p, report_key)
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")

    body = request.get_json(silent=True) or {}
    recipients = (body.get("recipients") or "").strip()
    sharepoint_path = (body.get("sharepoint_path") or "").strip()
    # Validate up front so the user gets immediate feedback (the actual send is
    # off-thread). At least one delivery target is required.
    if not split_recipients(recipients) and not sharepoint_path:
        abort(400, description="Enter at least one valid recipient or a SharePoint folder.")
    if sharepoint_path and not authz.has_sharepoint_access(p):
        abort(403, description="You don't have SharePoint delivery access.")

    job_id = enqueue_delivery(_job_repo(), owner_user_id=uid, payload={
        "report_key": report_key, "identity": p.email,
        "visible_keys": _visible_list(authz.visible_salesman_keys(p)),
        "builder_version": spec.builder_version,
        "params": _params_for_viewer(p, report_key, body.get("params") or {}),
        "layout": body.get("layout") or {}, "recipients": recipients,
        "subject": (body.get("subject") or "").strip(), "report_name": spec.title,
        "sharepoint_path": sharepoint_path,
    })
    worker = current_app.config["JOB_WORKER"]
    if not worker.running and not current_app.config["APP_CONFIG"].is_prod:
        worker.drain()
    return jsonify({"job_id": job_id}), 202


@reports_bp.get("/api/sharepoint/status")
@require_login
def sharepoint_status():
    p = _principal_or_401()
    sp = _sharepoint()
    return jsonify({
        "enabled": _authz().has_sharepoint_access(p),
        "configured": sp.is_configured(),
        "root": sp.root_path(),
    })


@reports_bp.get("/api/sharepoint/folders")
@require_login
def sharepoint_folders():
    p = _principal_or_401()
    if not _authz().has_sharepoint_access(p):
        abort(403, description="You don't have SharePoint access.")
    path = (request.args.get("path") or "").strip()
    try:
        return jsonify({"path": path, "folders": _sharepoint().list_folders(path)})
    except Exception as exc:  # noqa: BLE001 - surface as a clean error, never 500 the picker
        return jsonify({"path": path, "folders": [], "error": graph_error_message(exc, what="SharePoint")}), 502


@reports_bp.get("/api/onedrive/status")
@require_login
def onedrive_status():
    od = current_app.config.get("ONEDRIVE_SERVICE")
    return jsonify({
        "enabled": True,
        "configured": bool(od and od.is_configured()),
        "root": "OneDrive",
    })


@reports_bp.get("/api/onedrive/folders")
@require_login
def onedrive_folders():
    p = _principal_or_401()
    od = current_app.config.get("ONEDRIVE_SERVICE")
    if od is None:
        abort(503, description="OneDrive is not available.")
    path = (request.args.get("path") or "").strip()
    try:
        return jsonify({"path": path, "folders": od.list_folders(p.email, path)})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"path": path, "folders": [], "error": graph_error_message(exc, what="OneDrive")}), 502


def _params_for_viewer(p, report_key: str, params: dict) -> dict:
    """Stamp viewer limits that the builder honors (salesmen never get Commissions)."""
    out = dict(params or {})
    if report_key == "invoiced" and not _authz().may_see_commissions(p):
        out["_skip_commissions"] = True
    return out


def _visible_list(keys) -> list | None:
    return None if keys is None else sorted(set(keys))
