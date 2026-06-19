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

from datetime import date

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
from web.auth.principal import ROLE_DEVELOPER
from web.auth.session import current_principal
from web.data.repositories.saved_reports import SavedReport, SavedReportRepository
from web.data.repositories.users import UserRepository
from web.delivery.email import split_recipients
from web.delivery.jobs import enqueue_delivery
from web.reporting import params as P
from web.reporting.export_jobs import EXPORT_JOB_TYPE, enqueue_export
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


def _exports():
    return current_app.config["EXPORT_REPO"]


def _lookups():
    return current_app.config["LOOKUP_SERVICE"]


def _saved_repo() -> SavedReportRepository:
    return SavedReportRepository(current_app.config["DB"])


def _sharepoint():
    return current_app.config["SHAREPOINT_SERVICE"]


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


def _assert_scope_compatible(p, job):
    """Deny if the user's current scope is narrower than the job's build scope.

    Prevents a demoted user from reading a cached result that contains data
    they can no longer access (e.g. admin -> salesman demotion).
    """
    current_keys = _authz().visible_salesman_keys(p)
    if current_keys is None:
        return  # unrestricted user can see everything
    job_keys = job.params.get("visible_keys")
    if job_keys is None:
        abort(403, description="Result scope exceeds your current access; please re-run")
    normalized_current = {salesman_key(k) for k in current_keys}
    normalized_job = {salesman_key(k) for k in job_keys}
    if not normalized_job.issubset(normalized_current):
        abort(403, description="Result scope exceeds your current access; please re-run")


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
    # In-app reports (customer picker driven) have their own pages.
    if spec.in_app and report_key == "customer_last_order":
        return redirect(url_for("reports.customer_last_order_pick"))
    authz = _authz()
    authz.assert_report_runnable(p, report_key)
    return render_template(
        "report_view.html", active_tab="reports", report=spec,
        filters=REPORT_FILTERS.get(report_key, ()), period_options=PERIOD_OPTIONS,
        status_options=STATUS_OPTIONS, year_options=_year_options(),
        is_developer=(p.role == ROLE_DEVELOPER),
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
    return jsonify(cached.payload)


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


def _clo_facts_or_403(p, account: str):
    """Resolve the customer authoritatively, enforce scope, then fetch history.

    Returns (facts, customer_dict). Scope is checked against the CUSTOMER MASTER's
    sales group (LookupService), never the order lines - salesline_release lines
    can carry a blank SalesGroup, so trusting them would both deny valid customers
    and skip authorization on empty history. When the master knows the customer we
    authorize on its group even with zero orders; when it can't resolve the account
    (unknown, or universe not warm) we fall back to the facts' group and only
    authorize when there ARE facts (an empty unknown account leaks nothing).
    """
    info = _lookups().customer(account)
    facts = _report_service().last_order_facts(account)
    if info is not None:
        sales_group, name = info["salesman"], info["name"]
        _authz().assert_can_view_customer(p, sales_group)
    else:
        sales_group = next((f.sales_group for f in facts if f.sales_group), "")
        name = next((f.customer_name for f in facts if f.customer_name), "")
        if facts:
            _authz().assert_can_view_customer(p, sales_group)
    return facts, {"account": account, "name": name or account, "sales_group": sales_group}


@reports_bp.get("/api/report/customer-last-order/<account>/recent-invoiced")
@require_login
def customer_last_order_recent_invoiced(account: str):
    p = _principal_or_401()
    _assert_clo_access(p)
    facts, _ = _clo_facts_or_403(p, account)
    orders = [
        {"order_number": o.order_number, "order_date": o.order_date,
         "status": o.status, "customer_req": o.customer_req, "order_name": o.order_name}
        for o in clo.invoiced_orders(facts)[:10]
    ]
    return jsonify({"orders": orders})


@reports_bp.get("/report/customer-last-order/<account>")
@require_login
def customer_last_order_view(account: str):
    p = _principal_or_401()
    _assert_clo_access(p)

    requested = [o.strip() for o in (request.args.get("orders") or "").split(",") if o.strip()]
    error = None
    try:
        facts, customer = _clo_facts_or_403(p, account)
        view = clo.build(facts, requested_orders=requested)
    except Exception as exc:  # noqa: BLE001 - render a clean error card, never 500
        if getattr(exc, "status_code", None) == 403:
            raise
        current_app.logger.exception("customer last order failed for %s", account)
        return render_template(
            "customer_last_order_view.html", active_tab="reports",
            customer={"account": account, "name": account, "sales_group": ""},
            view=None, error=str(exc), provisional_note=clo.PROVISIONAL_NOTE,
        )
    return render_template(
        "customer_last_order_view.html", active_tab="reports",
        customer=customer, view=view, error=None, provisional_note=clo.PROVISIONAL_NOTE,
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
    all_custs = _lookups().customers(salesman)
    if visible is not None:
        all_custs = [c for c in all_custs if salesman_key(c.get("salesman", "")) in visible]
    return jsonify({"customers": all_custs})


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
    p = _principal_or_401()
    if p.role != ROLE_DEVELOPER:
        abort(403, description="Developer role required")
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


def _probe_reporting_api(cfg) -> dict:
    """Hit the on-prem Reporting API straight from this request (no worker, no
    cache, no dedup) so we can prove whether our calls leave the app and reach
    the endpoint at all. Two independent checks, both with short timeouts so the
    request can't hang:

      tcp  - open a raw socket to host:port. Proves the Azure Hybrid Connection
             tunnel reaches the on-prem listener (no HTTP, no stored procedure).
      http - a GET to the API root. ANY status code means the API process
             answered and the DBA should see this request land. A connect/read
             timeout here (with tcp ok) points at the API, not the tunnel.

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
    return out


@reports_bp.get("/api/reports/diagnostics/reporting-api")
@require_login
def reporting_api_diagnostics():
    """Admin/developer check: is the Reporting API reachable from the app right
    now, and is the job worker backed up? Answers 'why aren't our calls hitting
    the endpoint' without guessing. Developer-only (exposes the API host)."""
    p = _principal_or_401()
    if p.role != ROLE_DEVELOPER:
        abort(403, description="Developer role required")
    cfg = current_app.config["APP_CONFIG"]
    from web import is_background_leader_process
    worker = current_app.config["JOB_WORKER"]
    return jsonify({
        "reporting_api": _probe_reporting_api(cfg),
        "jobs": _job_repo().status_summary(),
        "claim_probe": _claim_probe(current_app.config["DB"]),
        "wiring": _worker_wiring(worker, current_app.config["DB"]),
        "worker": {
            "pid": os.getpid(),
            "is_leader_process": is_background_leader_process(),
            **worker.health(),
        },
    })


@reports_bp.get("/api/reports/diagnostics/claim-once")
@require_login
def claim_once_diagnostic():
    """Developer-only: call the REAL worker.repo.claim_next() from this request
    thread (the poller calls the same method but always gets None). If this
    claims a job, the poller's failure is thread-specific; if it returns None,
    the method itself is the problem. Safe: any claimed job is immediately set
    back to 'queued' so the actual handler never runs and nothing is lost."""
    p = _principal_or_401()
    if p.role != ROLE_DEVELOPER:
        abort(403, description="Developer role required")
    from datetime import datetime, timezone
    db = current_app.config["DB"]
    # Replicate claim_next() step by step so we can see WHICH step bails: does the
    # SELECT find the row, and does the UPDATE (id + status='queued') actually
    # match it? Then revert so the job is never really claimed.
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
            # Revert no matter what so this is a pure read-only probe.
            conn.execute(
                "UPDATE jobs SET status='queued', started_at=NULL WHERE id=?", (sel["id"],)
            )
            out["reverted"] = True
    return jsonify(out)


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
        "builder_version": spec.builder_version, "params": body.get("params") or {},
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
        return jsonify({"path": path, "folders": [], "error": str(exc)}), 200


def _visible_list(keys) -> list | None:
    return None if keys is None else sorted(set(keys))
