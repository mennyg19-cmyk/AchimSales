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

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from urllib.parse import urlencode

from report_engine import registry
from report_engine.registry import ReportStatus
from report_engine.lib import salesman_key
from web.auth.decorators import require_login
from web.auth.session import current_principal
from web.data.repositories.company_views import CompanyView, CompanyViewRepository
from web.data.repositories.report_defaults import (
    DEFAULT_VIEW_NAME,
    ReportDefault,
    ReportDefaultRepository,
)
from web.data.repositories.saved_reports import SavedReport, SavedReportRepository
from web.data.repositories.users import UserRepository
from web.reporting import params as P

reports_bp = Blueprint("reports", __name__)

# Which filter inputs each report exposes (rendered by report_view.html and read
# by report.js). Reports with a fixed server-side window expose none.
REPORT_FILTERS: dict[str, tuple[str, ...]] = {
    "ordered": ("period", "status", "customers", "salesman"),
    "invoiced": ("period", "customers", "salesman"),
    "salesman": ("year",),
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


def _preset_dict(s: SavedReport) -> dict:
    return {"id": s.id, "report_key": s.report_key, "name": s.name,
            "params": s.params, "layout": s.layout, "created_at": s.created_at}


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
        user_email=p.email,
        hide_commissions=not authz.may_see_commissions(p),
        can_edit_default=authz.can_see_company_schedules(p),
    )


def _year_options() -> list[int]:
    """Descending years for the year picker (current back to D365 go-live year)."""
    from report_engine.dates import D365_GO_LIVE, today_eastern

    return list(range(today_eastern().year, D365_GO_LIVE.year - 1, -1))


# --- JSON API -------------------------------------------------------------- #


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
    p = _require_developer()
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


def _require_developer():
    p = _principal_or_401()
    _authz().assert_developer(p)
    return p


def _params_for_viewer(p, report_key: str, params: dict) -> dict:
    """Stamp viewer limits that the builder honors (salesmen never get Commissions)."""
    out = dict(params or {})
    if report_key == "invoiced" and not _authz().may_see_commissions(p):
        out["_skip_commissions"] = True
    return out


def _visible_list(keys) -> list | None:
    return None if keys is None else sorted(set(keys))


from web.blueprints import report_jobs as _report_jobs  # noqa: F401, E402
from web.blueprints import report_clo as _report_clo  # noqa: F401, E402
from web.blueprints import report_diagnostics as _report_diagnostics  # noqa: F401, E402
from web.blueprints import report_views as _report_views  # noqa: F401, E402
from web.blueprints import report_delivery as _report_delivery  # noqa: F401, E402
