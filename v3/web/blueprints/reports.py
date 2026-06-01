"""Reports: list, view, and the run/poll/result/export JSON API.

Thin by design. Routes authenticate, authorize (the single Authorization
layer), enqueue a durable job, and read back the one cache. The on-screen
interactive table is driven entirely by report.js against this JSON API; the
math + column shape live in report_engine, the orchestration in
web.reporting.report_service.

Scope note: the principal's visible-salesman scope is folded into the cache key
(scope-safe cache) AND the dedup key, so two users with different scope never
share a cached payload. Per-grantee DATA filtering for non-privileged users is a
pending business sign-off (REVIEW-LOG); today only unrestricted (admin/dev)
users can reach a report at all, via the fail-closed Authorization default.
"""

from __future__ import annotations

from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    url_for,
)

import io
from urllib.parse import urlencode

from report_engine import registry
from report_engine.registry import ReportStatus
from web.auth.decorators import require_login
from web.auth.session import current_principal
from web.data.repositories.saved_reports import SavedReport, SavedReportRepository
from web.data.repositories.users import UserRepository
from web.reporting import params as P
from web.reporting.export import payload_to_xlsx
from web.reporting.jobs import enqueue_report_run

reports_bp = Blueprint("reports", __name__)

# Which filter inputs each report exposes (rendered by report_view.html and read
# by report.js). Reports with a fixed server-side window expose none.
REPORT_FILTERS: dict[str, tuple[str, ...]] = {
    "ordered": ("period", "status", "customers", "salesman"),
    "invoiced": ("period", "customers", "salesman"),
    "salesman": ("year",),
    "number_4": (),
    "customer_activity": ("salesman",),
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


def _lookups():
    return current_app.config["LOOKUP_SERVICE"]


def _saved_repo() -> SavedReportRepository:
    return SavedReportRepository(current_app.config["DB"])


def _preset_dict(s: SavedReport) -> dict:
    return {"id": s.id, "report_key": s.report_key, "name": s.name,
            "params": s.params, "layout": s.layout, "created_at": s.created_at}


def _principal_or_401():
    p = current_principal()
    if p is None:
        abort(401, description="Sign in required")
    return p


def _user_id(email: str) -> int | None:
    row = UserRepository(current_app.config["DB"]).get_by_email(email)
    return row.id if row else None


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


@reports_bp.get("/reports/<report_key>")
@require_login
def report_view(report_key: str):
    p = _principal_or_401()
    spec = _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    return render_template(
        "report_view.html", active_tab="reports", report=spec,
        filters=REPORT_FILTERS.get(report_key, ()), period_options=PERIOD_OPTIONS,
        status_options=STATUS_OPTIONS, year_options=_year_options(),
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

    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    visible = authz.visible_salesman_keys(p)
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


@reports_bp.get("/api/reports/result/<job_id>")
@require_login
def report_result(job_id: str):
    p = _principal_or_401()
    job = _owned_job_or_404(job_id, _user_id(p.email))
    # Re-check access live: a revoked grant must not be able to pull old results.
    _authz().assert_report_runnable(p, job.params.get("report_key"))
    if job.status != "success":
        return jsonify({"status": job.status, "error": job.error}), 409
    cached = _cache().get(job.result_ref)
    if cached is None:
        abort(404, description="Result expired; please re-run")
    return jsonify(cached.payload)


@reports_bp.get("/reports/<report_key>/export/<job_id>")
@require_login
def export_report(report_key: str, job_id: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    job = _owned_job_or_404(job_id, _user_id(p.email))
    # Authorize against the job's OWN report key (not just the URL) and re-resolve live.
    job_report_key = job.params.get("report_key")
    if job_report_key != report_key:
        abort(404, description="Unknown job")
    _authz().assert_report_runnable(p, job_report_key)
    if job.status != "success":
        abort(409, description="Report is not ready to export")
    cached = _cache().get(job.result_ref)
    if cached is None:
        abort(404, description="Result expired; please re-run")
    data = payload_to_xlsx(cached.payload)
    return send_file(
        io.BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name=f"{report_key}.xlsx",
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
    return jsonify({"salesmen": _lookups().salesmen()})


@reports_bp.get("/api/reports/<report_key>/customers")
@require_login
def report_customers(report_key: str):
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)
    salesman = (request.args.get("salesman") or "").strip() or None
    return jsonify({"customers": _lookups().customers(salesman)})


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
    """
    p = _principal_or_401()
    _built_spec_or_404(report_key)
    _authz().assert_report_runnable(p, report_key)

    filters = request.get_json(silent=True)
    if not isinstance(filters, dict):
        filters = request.form.to_dict()

    cfg = current_app.config["APP_CONFIG"]
    base = (cfg.reporting_api_base_url or "").rstrip("/")
    try:
        report_id = P.report_id_for(report_key)
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
    items = [_preset_dict(s) for s in _saved_repo().list_for_user(uid)
             if s.report_key == report_key]
    return jsonify({"presets": items})


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
    pid = _saved_repo().create(uid, report_key, name,
                               body.get("params") or {}, body.get("layout") or {})
    return jsonify({"id": pid, "name": name}), 201


@reports_bp.get("/api/reports/presets/<int:preset_id>")
@require_login
def get_preset(preset_id: int):
    p = _principal_or_401()
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    s = _saved_repo().get(preset_id, uid)
    if s is None or not _authz().can_view_report(p, s.report_key):
        abort(404, description="Unknown preset")
    return jsonify(_preset_dict(s))


@reports_bp.delete("/api/reports/presets/<int:preset_id>")
@require_login
def delete_preset(preset_id: int):
    p = _principal_or_401()
    uid = _user_id(p.email)
    if uid is None:
        abort(403, description="Unknown user")
    if not _saved_repo().delete(preset_id, uid):
        abort(404, description="Unknown preset")
    return jsonify({"deleted": True})
