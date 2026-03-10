"""
Sales Reports Web App -- Flask entry point.

Mobile-friendly web app for running D365 sales reports.
Authenticated via Microsoft Entra ID (Azure AD).
"""

import json
import logging
import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from webapp.config import FLASK_SECRET
from webapp.db import (
    init_db,
    normalize_key,
    add_notification,
    get_notification_counts,
    get_notifications,
    dismiss_notification,
    dismiss_notifications_by_type,
    get_excluded_customers,
    set_excluded_customers,
    get_excluded_salesmen,
    set_excluded_salesmen,
    get_all_users,
    add_user as db_add_user,
    update_user as db_update_user,
    delete_user as db_delete_user,
    get_saved_reports,
    add_saved_report,
    delete_saved_report,
)

DEV_BYPASS_AUTH = os.environ.get("DEV_BYPASS_AUTH", "").lower() in ("1", "true", "yes")

from webapp.user_map import (
    get_available_reports,
    get_salesman_key,
    get_user,
    is_admin,
    is_salesman,
    is_developer,
    reload_map,
    REPORTS_CONFIG,
)
from webapp.report_api import run_report
from webapp.history import add_record, update_record, get_history

import threading
import queue
import time as _time

_progress_queues: dict[str, queue.Queue] = {}
_sse_connected: dict[str, bool] = {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)
app.secret_key = FLASK_SECRET
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if os.environ.get("WEBSITE_SITE_NAME"):
    app.config["SESSION_COOKIE_SECURE"] = True

init_db()

from webapp.dashboard_data import start_background_refresh
start_background_refresh()


def _cleanup_old_reports(max_age_days: int = 7):
    """Delete report output files older than max_age_days."""
    from webapp.config import REPORT_OUTPUT_DIR
    import time
    cutoff = time.time() - (max_age_days * 86400)
    try:
        for fname in os.listdir(REPORT_OUTPUT_DIR):
            fpath = os.path.join(REPORT_OUTPUT_DIR, fname)
            if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
                log.info("Cleaned up old report file: %s", fname)
    except Exception:
        log.exception("Report cleanup failed")


_cleanup_old_reports()


@app.context_processor
def inject_theme():
    """Make theme available in all templates."""
    return {"theme": session.get("theme", "light")}


# -- Helpers ---------------------------------------------------------------

def _get_salesmen_list(user_email: str | None = None) -> list[dict]:
    """Return salesman list with excluded ones filtered out."""
    try:
        from config.salesman_map import SALESMAN_MAP
        excluded = get_excluded_salesmen(user_email) if user_email else []
        salesmen = [
            {"key": k, "name": v[1], "display": v[2]}
            for k, v in SALESMAN_MAP.items()
            if v[0] != "?unassigned" and k not in excluded
        ]
        salesmen.sort(key=lambda x: x["name"])
        return salesmen
    except Exception:
        log.exception("Failed to load salesmen list")
        return []


# -- Auth helpers ----------------------------------------------------------

def _get_current_user():
    """Return the current user dict from session, or None."""
    return session.get("user")


def _require_login(f):
    """Decorator: redirect to login if not authenticated."""
    from functools import wraps

    @wraps(f)
    def wrapper(*args, **kwargs):
        user = _get_current_user()
        if not user:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapper


# -- D365 connection helper ------------------------------------------------

def _get_d365_connection():
    """Return (base_url, token, company_id) for D365 OData calls."""
    from config.settings import (
        get_client_id, get_client_secret, get_company_id,
        get_d365_env_url, get_tenant_id, validate_d365_config,
    )
    from core.auth import get_d365_token

    validate_d365_config()
    env_url = get_d365_env_url().rstrip("/")
    base_url = (
        f"{env_url}/data/"
        if "/data" not in env_url.lower()
        else (env_url if env_url.endswith("/") else f"{env_url}/")
    )
    token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), env_url)
    company = get_company_id() or None
    return base_url, token, company


# -- Auth routes -----------------------------------------------------------

@app.route("/")
def index():
    user = _get_current_user()
    if user:
        return redirect(url_for("reports"))
    return redirect(url_for("login"))


@app.route("/login")
def login():
    user = _get_current_user()
    if user:
        return redirect(url_for("reports"))
    if DEV_BYPASS_AUTH:
        return render_template("login_dev.html")
    return render_template("login.html")


@app.route("/login/start")
def login_start():
    """Redirect to Microsoft login."""
    if DEV_BYPASS_AUTH:
        return redirect(url_for("dev_login"))
    try:
        from webapp.auth import build_login_url
        auth_url = build_login_url()
        return redirect(auth_url)
    except Exception:
        log.exception("Failed to build login URL")
        flash("Could not connect to Microsoft login. Please try again.", "error")
        return redirect(url_for("login"))


@app.route("/dev-login", methods=["GET", "POST"])
def dev_login():
    """Dev-only: bypass Microsoft login, pick a role to sign in as."""
    if not DEV_BYPASS_AUTH:
        return redirect(url_for("login"))

    if request.method == "POST":
        role = request.form.get("role", "admin")
        if role == "admin":
            session["user"] = {
                "email": "dev-admin@localhost",
                "name": "Dev Admin",
                "role": "admin",
                "salesman_key": None,
            }
        else:
            sm_key = request.form.get("salesman_key", "mkolko")
            from config.salesman_map import lookup_salesman
            _, full_name, display_name = lookup_salesman(sm_key)
            session["user"] = {
                "email": f"dev-{sm_key}@localhost",
                "name": full_name,
                "role": "salesman",
                "salesman_key": sm_key,
            }
        return redirect(url_for("reports"))

    return render_template("login_dev.html", salesmen=_get_salesmen_list())


@app.route("/auth/callback", methods=["GET", "POST"])
def auth_callback():
    """Handle the redirect from Microsoft after login."""
    from webapp.auth import complete_login
    ms_user = complete_login()
    if not ms_user:
        flash("Login failed. Please try again.", "error")
        return redirect(url_for("login"))

    email = ms_user.get("email", "")
    user_info = get_user(email)
    if not user_info:
        return render_template("unauthorized.html", email=email)

    if is_developer(user_info):
        dev_name = ms_user.get("name", email)
        session["user"] = {
            "email": email,
            "name": dev_name,
            "role": "developer",
            "salesman_key": None,
            "_dev": True,
            "_dev_name": dev_name,
        }
        from webapp.db import get_setting
        session["theme"] = get_setting(email, "theme", "light")
        return redirect(url_for("role_picker"))

    session["user"] = {
        "email": email,
        "name": ms_user.get("name", email),
        "role": user_info["role"],
        "salesman_key": user_info.get("salesman_key"),
    }
    from webapp.db import get_setting as _gs
    session["theme"] = _gs(email, "theme", "light")
    return redirect(url_for("reports"))


@app.route("/dev/role-picker", methods=["GET", "POST"])
@_require_login
def role_picker():
    """Let authenticated developers pick a role to impersonate."""
    user = _get_current_user()
    if not is_developer(user) and not user.get("_dev"):
        return redirect(url_for("reports"))

    if request.method == "POST":
        role = request.form.get("role", "admin")
        real_email = user.get("email", "")
        # Always use the original dev name, stripping any previous "(as ...)"
        raw_name = user.get("_dev_name") or user.get("name", real_email)
        dev_name = raw_name.split(" (as ")[0] if " (as " in raw_name else raw_name

        if role == "admin":
            session["user"] = {
                "email": real_email,
                "name": dev_name,
                "role": "admin",
                "salesman_key": None,
                "_dev": True,
                "_dev_name": dev_name,
            }
        else:
            sm_key = request.form.get("salesman_key", "")
            from config.salesman_map import lookup_salesman
            _, full_name, display_name = lookup_salesman(sm_key)
            session["user"] = {
                "email": real_email,
                "name": f"{full_name} (as {dev_name})",
                "role": "salesman",
                "salesman_key": sm_key,
                "_dev": True,
                "_dev_name": dev_name,
            }
        return redirect(url_for("reports"))

    return render_template("role_picker.html", user=user,
                           salesmen=_get_salesmen_list(user.get("email")))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -- Main pages ------------------------------------------------------------

@app.route("/home")
@_require_login
def home():
    """Redirect to reports for backward compatibility."""
    return redirect(url_for("reports"))


@app.route("/reports")
@_require_login
def reports():
    """Report list page."""
    user = _get_current_user()
    available = get_available_reports(user)
    presets = get_saved_reports(user.get("email", ""))
    return render_template("reports.html", user=user, reports=available,
                           presets=presets, active_tab="reports")


@app.route("/dashboard")
@_require_login
def dashboard():
    """Customer activity dashboard."""
    user = _get_current_user()
    from webapp.dashboard_data import (
        get_dashboard_data, get_dashboard_summary, get_refresh_status,
    )

    salesman_key = get_salesman_key(user)
    email = user.get("email", "")
    excluded = get_excluded_customers(email)
    customers = get_dashboard_data(salesman_key=salesman_key, exclude_accounts=excluded)
    summary = get_dashboard_summary(customers)
    refresh = get_refresh_status(salesman_key=salesman_key)

    alerts = get_notifications(email, dismissed=False)
    alerts = [a for a in alerts if a["type"] == "overdue_customer"]

    return render_template(
        "dashboard.html", user=user, customers=customers, summary=summary,
        refresh=refresh, alerts=alerts, active_tab="dashboard",
    )


@app.route("/settings")
@_require_login
def settings_page():
    """User settings page."""
    user = _get_current_user()
    from webapp.db import get_cached_customer_list, get_setting

    salesman_key = get_salesman_key(user)
    email = user.get("email", "")
    excluded = get_excluded_customers(email)
    customers = get_cached_customer_list(salesman_key=salesman_key)

    show_admin_settings = is_admin(user)
    app_users = get_all_users() if show_admin_settings else []

    all_salesmen = []
    excluded_salesmen = []
    if show_admin_settings:
        try:
            from config.salesman_map import SALESMAN_MAP
            all_salesmen = [
                {"key": k, "name": v[1]}
                for k, v in SALESMAN_MAP.items()
                if v[0] != "?unassigned"
            ]
            all_salesmen.sort(key=lambda x: x["name"])
        except Exception:
            pass
        excluded_salesmen = get_excluded_salesmen(email)

    theme = get_setting(email, "theme", "light")

    return render_template(
        "settings.html", user=user, customers=customers,
        excluded=excluded, active_tab="settings",
        show_user_mgmt=show_admin_settings, app_users=app_users,
        show_admin_settings=show_admin_settings,
        all_salesmen=all_salesmen, excluded_salesmen=excluded_salesmen,
        theme=theme,
    )


# -- Customer / Order detail routes ----------------------------------------

@app.route("/customer/<account>")
@_require_login
def customer_detail(account):
    """Customer detail page — fetches info + recent orders from D365 on demand."""
    import re as _re_val
    if not _re_val.match(r"^[A-Za-z0-9\-_]+$", account):
        flash("Invalid customer account.", "error")
        return redirect(url_for("dashboard"))
    user = _get_current_user()
    salesman_key = get_salesman_key(user)

    from webapp.db import get_db
    cust_info = {"account": account, "name": account}
    orders = []
    active_period = "7"
    cached = None
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM dashboard_cache WHERE customer_account = ?", (account,)
        ).fetchone()
        if row:
            cached = dict(row)
    finally:
        conn.close()

    if salesman_key and cached:
        if normalize_key(salesman_key) != normalize_key(cached.get("sales_group") or ""):
            flash("You do not have access to this customer.", "error")
            return redirect(url_for("dashboard"))

    try:
        base_url, token, company = _get_d365_connection()
        from data.d365_entities import fetch_customers, fetch_sales_order_headers
        from core.dates import get_today_eastern, convert_d365_dates_to_eastern
        from datetime import date as _date, timedelta

        cust_df = fetch_customers(base_url, token, company_id=company, customer_account=account)
        if not cust_df.empty:
            r = cust_df.iloc[0]
            cust_info = {
                "account": str(r.get("CustomerAccount", "")),
                "name": str(r.get("CustomerName", "")),
                "sales_group": str(r.get("SalesGroup", "")),
            }

            if salesman_key and not is_admin(user):
                if normalize_key(salesman_key) != normalize_key(cust_info["sales_group"]):
                    flash("You do not have access to this customer.", "error")
                    return redirect(url_for("dashboard"))

        if cached:
            cust_info["status"] = cached.get("status", "")
            cust_info["days_since_last"] = cached.get("days_since_last")
            cust_info["avg_gap_days"] = cached.get("avg_gap_days")
            cust_info["overdue_threshold"] = cached.get("overdue_threshold")

        today = get_today_eastern()

        days_param = request.args.get("days", type=int)
        last_param = request.args.get("last", type=int)
        active_period = "7"

        if last_param:
            start_date = _date(2000, 1, 1)
            active_period = f"last{last_param}"
        elif days_param:
            start_date = today - timedelta(days=days_param)
            active_period = str(days_param)
        else:
            start_date = today - timedelta(days=7)
            active_period = "7"

        headers_df = fetch_sales_order_headers(
            base_url, token, start_date, today,
            company_id=company, customer_account=account,
        )

        orders = []
        if not headers_df.empty:
            if "OrderDate" in headers_df.columns:
                headers_df["OrderDate"] = convert_d365_dates_to_eastern(headers_df["OrderDate"])

            headers_df = headers_df.sort_values("OrderDate", ascending=False)

            if last_param:
                headers_df = headers_df.head(last_param)

            for _, row in headers_df.iterrows():
                od = row.get("OrderDate")
                orders.append({
                    "order_number": str(row.get("SalesOrderNumber", "")),
                    "order_date": od.strftime("%Y-%m-%d") if hasattr(od, "strftime") else str(od)[:10] if od else "",
                    "status": str(row.get("OrderStatus", "")),
                    "processing_status": str(row.get("OrderProcessingStatus", "")),
                    "customer_req": str(row.get("CustomerRequisition", "")),
                    "order_name": str(row.get("SalesOrderName", "")),
                })

    except Exception:
        log.exception("Failed to load customer detail for %s", account)
        flash("Could not load customer data from D365.", "error")

    email = user.get("email", "")
    excluded = get_excluded_customers(email)
    is_excluded = account in excluded

    return render_template(
        "customer.html", user=user, customer=cust_info, orders=orders,
        active_period=active_period, is_excluded=is_excluded,
        active_tab="dashboard",
    )


@app.route("/order/<order_number>")
@_require_login
def order_detail(order_number):
    """Order detail page — fetches header + line items from D365 on demand."""
    user = _get_current_user()
    salesman_key = get_salesman_key(user)

    try:
        base_url, token, company = _get_d365_connection()
        from data.d365_entities import fetch_sales_order_lines
        from core.odata import fetch_odata_entity
        from data.field_maps import (
            SALES_ORDER_HEADER_SELECT, SALES_ORDER_HEADER_FIELD_MAP,
        )
        from data.d365_entities import rename_columns
        from core.dates import convert_d365_dates_to_eastern

        import re as _re_odata
        safe_num = order_number.replace("'", "''")
        if not _re_odata.match(r"^[A-Za-z0-9\-_]+$", order_number):
            flash("Invalid order number.", "error")
            return redirect(url_for("dashboard"))
        filter_expr = f"SalesOrderNumber eq '{safe_num}'"
        hdr_df = fetch_odata_entity(
            base_url, "SalesOrderHeadersV3", token,
            select=SALES_ORDER_HEADER_SELECT,
            filter_expr=filter_expr,
            company_id=company,
        )
        hdr_df = rename_columns(hdr_df, SALES_ORDER_HEADER_FIELD_MAP)

        header = {}
        customer_account = ""
        if not hdr_df.empty:
            if "OrderDate" in hdr_df.columns:
                hdr_df["OrderDate"] = convert_d365_dates_to_eastern(hdr_df["OrderDate"])
            r = hdr_df.iloc[0]
            od = r.get("OrderDate")
            customer_account = str(r.get("CustomerAccount", ""))
            header = {
                "order_number": str(r.get("SalesOrderNumber", "")),
                "order_date": od.strftime("%Y-%m-%d") if hasattr(od, "strftime") else str(od)[:10] if od else "",
                "status": str(r.get("OrderStatus", "")),
                "processing_status": str(r.get("OrderProcessingStatus", "")),
                "customer_account": customer_account,
                "customer_name": str(r.get("CustomerName", "")),
                "salesman": str(r.get("Salesman", "")),
                "customer_req": str(r.get("CustomerRequisition", "")),
                "order_name": str(r.get("SalesOrderName", "")),
            }

            if salesman_key and not is_admin(user):
                from webapp.db import get_db
                conn = get_db()
                try:
                    row = conn.execute(
                        "SELECT sales_group FROM dashboard_cache WHERE customer_account = ?",
                        (customer_account,),
                    ).fetchone()
                    if row:
                        if normalize_key(salesman_key) != normalize_key(row["sales_group"] or ""):
                            flash("You do not have access to this order.", "error")
                            return redirect(url_for("dashboard"))
                finally:
                    conn.close()

        lines_df = fetch_sales_order_lines(base_url, token, {order_number}, company_id=company)
        def _safe_float(val, default=0.0):
            try:
                import math
                f = float(val)
                return f if not math.isnan(f) else default
            except (TypeError, ValueError):
                return default

        lines = []
        if not lines_df.empty:
            lines_df = lines_df.sort_values("LineNumber")
            for _, r in lines_df.iterrows():
                lines.append({
                    "line_number": r.get("LineNumber", ""),
                    "item": str(r.get("Item#", "")),
                    "description": str(r.get("LineDescription", "")),
                    "qty_ordered": _safe_float(r.get("QtyOrdered")),
                    "sales_price": _safe_float(r.get("SalesPrice")),
                    "total": _safe_float(r.get("Total")),
                    "status": str(r.get("RawLineStatus", "")),
                })

    except Exception:
        log.exception("Failed to load order detail for %s", order_number)
        flash("Could not load order data from D365.", "error")
        header = {"order_number": order_number}
        lines = []
        customer_account = ""

    return render_template(
        "order.html", user=user, header=header, lines=lines,
        customer_account=customer_account, active_tab="dashboard",
    )


# -- Report routes ---------------------------------------------------------

@app.route("/report/<report_key>")
@_require_login
def report_form(report_key):
    """Show the parameter form for a specific report."""
    user = _get_current_user()
    available = get_available_reports(user)

    if report_key not in available:
        flash("You do not have access to this report.", "error")
        return redirect(url_for("reports"))

    report_cfg = available[report_key]
    salesman_key = get_salesman_key(user)
    user_is_admin = is_admin(user)

    admin_default_salesman = None
    salesmen_list = []
    if user_is_admin and report_cfg.get("salesman_filter"):
        salesmen_list = _get_salesmen_list(user.get("email"))
        admin_default_salesman = user.get("salesman_key") or None

    preset_params = {}
    if request.args.get("preset"):
        for k, v in request.args.items():
            if k != "preset":
                preset_params[k] = v
        preset_params["customers"] = request.args.getlist("customers")

    app_users = []
    if user_is_admin:
        app_users = get_all_users()

    return render_template(
        "report_form.html",
        user=user,
        report_key=report_key,
        report=report_cfg,
        salesman_key=salesman_key,
        is_admin=user_is_admin,
        salesmen_list=salesmen_list,
        active_tab="reports",
        preset_params=preset_params,
        app_users=app_users,
        admin_default_salesman=admin_default_salesman,
    )


@app.route("/report/<report_key>/run", methods=["POST"])
@_require_login
def report_run(report_key):
    """Start a report run: create history record, launch background thread, return run_id for SSE."""
    user = _get_current_user()
    available = get_available_reports(user)

    if report_key not in available:
        return jsonify({"success": False, "error": "Access denied"}), 403

    params = request.get_json() or {}

    if is_salesman(user) and user.get("salesman_key"):
        report_cfg = available[report_key]
        if report_cfg.get("salesman_filter"):
            params["salesman"] = user["salesman_key"]

    report_cfg = available[report_key]
    email = user.get("email", "")

    record_id = add_record(
        email=email,
        report_key=report_key,
        report_name=report_cfg.get("name", report_key),
        params=params,
        status="running",
    )

    progress_q = queue.Queue()
    _progress_queues[record_id] = progress_q
    _sse_connected[record_id] = False

    def _run_in_background():
        try:
            progress_q.put({"step": "connecting", "pct": 10, "msg": "Connecting to D365..."})
            _time.sleep(0.3)
            progress_q.put({"step": "fetching", "pct": 25, "msg": "Fetching data from D365..."})

            result = run_report(report_key, params)

            if result.get("success"):
                progress_q.put({"step": "processing", "pct": 70, "msg": "Processing data..."})
                _time.sleep(0.2)
                progress_q.put({"step": "writing", "pct": 85, "msg": "Writing Excel file..."})
                _time.sleep(0.2)

                update_record(
                    email, record_id,
                    status="completed" if result.get("filepath") else "no_data",
                    filepath=result.get("filepath"),
                    filename=result.get("filename"),
                    summary=result.get("summary", {}),
                )
                result.pop("traceback", None)
                progress_q.put({"step": "done", "pct": 100, "msg": "Report complete!", "result": result})
            else:
                err = result.get("error", "Unknown error")
                update_record(email, record_id, status="failed", error=err)
                result.pop("traceback", None)
                progress_q.put({"step": "error", "pct": 100, "msg": f"Failed: {err}", "result": result})
        except Exception as e:
            update_record(email, record_id, status="failed", error=str(e))
            progress_q.put({"step": "error", "pct": 100, "msg": f"Failed: {e}",
                            "result": {"success": False, "error": str(e)}})
        finally:
            progress_q.put(None)

            _time.sleep(1)
            if not _sse_connected.get(record_id, False):
                report_name = report_cfg.get("name", report_key)
                add_notification(
                    user_email=email,
                    ntype="report_ready",
                    title=f"{report_name} is ready",
                    message="Your report has finished. Tap to view.",
                    data={"record_id": record_id, "report_key": report_key},
                )

            _sse_connected.pop(record_id, None)

    thread = threading.Thread(target=_run_in_background, daemon=True)
    thread.start()

    log.info("Running report %s (run_id=%s) with params: %s (user: %s)",
             report_key, record_id, params, email)

    return jsonify({"run_id": record_id})


@app.route("/report/progress/<run_id>")
@_require_login
def report_progress(run_id):
    """SSE endpoint: stream progress updates for a running report."""
    progress_q = _progress_queues.get(run_id)
    _sse_connected[run_id] = True

    def generate():
        if not progress_q:
            yield f"data: {json.dumps({'step': 'error', 'pct': 100, 'msg': 'Run not found', 'result': {'success': False, 'error': 'Run not found'}})}\n\n"
            return

        try:
            while True:
                try:
                    msg = progress_q.get(timeout=120)
                except queue.Empty:
                    yield f"data: {json.dumps({'step': 'error', 'pct': 100, 'msg': 'Timeout', 'result': {'success': False, 'error': 'Report timed out'}})}\n\n"
                    break

                if msg is None:
                    _progress_queues.pop(run_id, None)
                    break

                yield f"data: {json.dumps(msg, default=str)}\n\n"

                if msg.get("step") in ("done", "error"):
                    _progress_queues.pop(run_id, None)
                    _sse_connected[run_id] = True
                    break
        except GeneratorExit:
            _sse_connected[run_id] = False

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/report/<report_key>/download")
@_require_login
def report_download(report_key):
    """Download the most recently generated Excel file for a report."""
    user = _get_current_user()
    filepath = session.get(f"download_{report_key}")

    if not filepath or not os.path.isfile(filepath):
        records = get_history(user.get("email", ""))
        for rec in records:
            if rec.get("report_key") == report_key and rec.get("file_available"):
                filepath = rec["filepath"]
                break

    if not filepath or not os.path.isfile(filepath):
        flash("No report file available for download. Please run the report first.", "error")
        return redirect(url_for("report_form", report_key=report_key))

    return send_file(filepath, as_attachment=True, download_name=os.path.basename(filepath))


# -- History routes --------------------------------------------------------

@app.route("/history")
@_require_login
def history():
    """Show the user's report run history."""
    user = _get_current_user()
    records = get_history(user.get("email", ""))
    return render_template("history.html", user=user, records=records, active_tab="reports")


@app.route("/history/download/<int:record_idx>")
@_require_login
def history_download(record_idx):
    """Download an Excel file from history."""
    user = _get_current_user()
    records = get_history(user.get("email", ""))
    if record_idx < 0 or record_idx >= len(records):
        flash("Report not found in history.", "error")
        return redirect(url_for("history"))

    rec = records[record_idx]
    filepath = rec.get("filepath")
    if not filepath or not os.path.isfile(filepath):
        flash("The file for this report is no longer available.", "error")
        return redirect(url_for("history"))

    return send_file(filepath, as_attachment=True, download_name=rec.get("filename", os.path.basename(filepath)))


@app.route("/history/view/<int:record_idx>")
@_require_login
def history_view(record_idx):
    """Re-view results from a past report run."""
    user = _get_current_user()
    records = get_history(user.get("email", ""))
    if record_idx < 0 or record_idx >= len(records):
        flash("Report not found in history.", "error")
        return redirect(url_for("history"))

    rec = records[record_idx]
    filepath = rec.get("filepath")

    sheets = {}
    if filepath and os.path.isfile(filepath):
        from webapp.report_api import _read_excel_sheets
        sheets = _read_excel_sheets(filepath)

    return render_template(
        "history_view.html", user=user, record=rec,
        record_idx=record_idx, sheets=sheets, active_tab="reports",
    )


# -- API routes ------------------------------------------------------------

@app.route("/api/customers")
@_require_login
def api_customers():
    """Return customer list, optionally filtered by salesman."""
    user = _get_current_user()
    salesman_key = None

    if is_salesman(user):
        salesman_key = user.get("salesman_key")
    elif is_admin(user) and request.args.get("salesman"):
        salesman_key = request.args.get("salesman")

    try:
        from data.d365_entities import fetch_customers

        base_url, token, company = _get_d365_connection()
        df = fetch_customers(base_url, token, company)

        if df.empty:
            return jsonify([])

        if salesman_key and "SalesGroup" in df.columns:
            norm = normalize_key(salesman_key)
            df["_norm_sg"] = df["SalesGroup"].fillna("").astype(str).apply(normalize_key)
            df = df[df["_norm_sg"] == norm].drop(columns=["_norm_sg"])

        customers = []
        for _, row in df.iterrows():
            customers.append({
                "account": str(row.get("CustomerAccount", "")),
                "name": str(row.get("CustomerName", "")),
            })

        customers.sort(key=lambda c: c["name"])
        return jsonify(customers)

    except Exception:
        log.exception("Failed to fetch customers")
        return jsonify([]), 500


@app.route("/api/notifications")
@_require_login
def api_notifications():
    """Return unread notification counts and items."""
    user = _get_current_user()
    email = user.get("email", "")
    counts = get_notification_counts(email)
    items = get_notifications(email, dismissed=False)
    return jsonify({
        "report_ready_count": counts.get("report_ready", 0),
        "overdue_count": counts.get("overdue_customer", 0),
        "total": counts.get("total", 0),
        "items": items,
    })


@app.route("/api/notifications/dismiss", methods=["POST"])
@_require_login
def api_notifications_dismiss():
    """Dismiss a notification by id or all of a type."""
    user = _get_current_user()
    email = user.get("email", "")
    data = request.get_json() or {}

    if "id" in data:
        try:
            nid = int(data["id"])
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid notification id"}), 400
        dismiss_notification(nid, user_email=email)
    elif "type" in data:
        dismiss_notifications_by_type(email, data["type"])

    return jsonify({"success": True})


@app.route("/api/settings/excluded-customers", methods=["POST"])
@_require_login
def api_excluded_customers():
    """Save excluded customers list."""
    user = _get_current_user()
    data = request.get_json() or {}
    accounts = data.get("accounts", [])
    set_excluded_customers(user.get("email", ""), accounts)
    return jsonify({"success": True})


@app.route("/api/settings/toggle-customer-exclusion", methods=["POST"])
@_require_login
def api_toggle_customer_exclusion():
    """Add or remove a single customer from the exclusion list."""
    user = _get_current_user()
    data = request.get_json() or {}
    account = data.get("account", "")
    include = data.get("include", True)
    email = user.get("email", "")

    excluded = get_excluded_customers(email)
    if include:
        excluded = [a for a in excluded if a != account]
    else:
        if account not in excluded:
            excluded.append(account)
    set_excluded_customers(email, excluded)
    return jsonify({"success": True})


@app.route("/api/settings/excluded-salesmen", methods=["POST"])
@_require_login
def api_excluded_salesmen():
    """Save excluded salesmen list."""
    user = _get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    keys = data.get("keys", [])
    set_excluded_salesmen(user.get("email", ""), keys)
    return jsonify({"success": True})


@app.route("/api/settings/theme", methods=["POST"])
@_require_login
def api_set_theme():
    """Save user theme preference."""
    user = _get_current_user()
    data = request.get_json() or {}
    theme = data.get("theme", "light")
    from webapp.db import set_setting
    set_setting(user.get("email", ""), "theme", theme)
    session["theme"] = theme
    return jsonify({"success": True})


@app.route("/api/users", methods=["GET"])
@_require_login
def api_list_users():
    user = _get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    return jsonify({"users": get_all_users()})


@app.route("/api/users", methods=["POST"])
@_require_login
def api_add_user():
    user = _get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    email = (data.get("email") or "").lower().strip()
    role = data.get("role", "salesman")
    salesman_key = data.get("salesman_key", "").strip() or None
    display_name = data.get("display_name", "").strip() or None

    if not email or "@" not in email:
        return jsonify({"error": "Valid email is required"}), 400
    if role not in ("admin", "salesman", "developer"):
        return jsonify({"error": "Role must be admin, salesman, or developer"}), 400
    if role == "salesman" and not salesman_key:
        return jsonify({"error": "Salesman key is required for salesman role"}), 400

    ok = db_add_user(email, role, salesman_key, display_name)
    if not ok:
        return jsonify({"error": "User already exists"}), 409
    return jsonify({"success": True})


@app.route("/api/users/<path:email>", methods=["PUT"])
@_require_login
def api_update_user(email):
    user = _get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    role = data.get("role", "salesman")
    salesman_key = data.get("salesman_key", "").strip() or None
    display_name = data.get("display_name", "").strip() or None

    if role not in ("admin", "salesman", "developer"):
        return jsonify({"error": "Role must be admin, salesman, or developer"}), 400
    if role == "salesman" and not salesman_key:
        return jsonify({"error": "Salesman key is required for salesman role"}), 400

    ok = db_update_user(email, role, salesman_key, display_name)
    if not ok:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"success": True})


@app.route("/api/users/<path:email>", methods=["DELETE"])
@_require_login
def api_delete_user(email):
    user = _get_current_user()
    if not is_admin(user):
        return jsonify({"error": "forbidden"}), 403
    if email.lower().strip() == user.get("email", "").lower().strip():
        return jsonify({"error": "Cannot delete yourself"}), 400
    ok = db_delete_user(email)
    if not ok:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"success": True})


# -- Saved reports (presets) API -------------------------------------------

@app.route("/api/saved-reports", methods=["GET"])
@_require_login
def api_list_saved_reports():
    user = _get_current_user()
    return jsonify({"presets": get_saved_reports(user.get("email", ""))})


@app.route("/api/saved-reports", methods=["POST"])
@_require_login
def api_save_report():
    user = _get_current_user()
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    report_key = data.get("report_key", "")
    report_name = data.get("report_name", "")
    params = data.get("params", {})
    for_user_email = (data.get("for_user_email") or "").strip()

    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not report_key:
        return jsonify({"error": "Report key is required"}), 400

    target_email = user.get("email", "")
    if for_user_email and for_user_email != target_email:
        if not is_admin(user):
            return jsonify({"error": "Only admins/devs can save presets for other users"}), 403
        target_email = for_user_email

    preset_id = add_saved_report(
        target_email, name, report_key, report_name, params)
    return jsonify({"success": True, "id": preset_id})


@app.route("/api/saved-reports/<int:preset_id>", methods=["DELETE"])
@_require_login
def api_delete_saved_report(preset_id):
    user = _get_current_user()
    ok = delete_saved_report(preset_id, user.get("email", ""))
    if not ok:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


@app.route("/api/dashboard/refresh", methods=["POST"])
@_require_login
def api_dashboard_refresh():
    """Trigger a manual dashboard cache refresh (non-blocking).

    Salesmen only refresh their own customers; admins refresh everything.
    """
    from webapp.dashboard_data import (
        refresh_cache, get_last_refresh, mark_refresh_requested,
    )

    user = _get_current_user()
    salesman_key = get_salesman_key(user)
    before = get_last_refresh() or ""
    requested_at = mark_refresh_requested()

    def _do_refresh():
        try:
            refresh_cache(salesman_key=salesman_key)
        except Exception:
            log.exception("Manual dashboard refresh failed")

    thread = threading.Thread(target=_do_refresh, daemon=True)
    thread.start()
    return jsonify({
        "success": True, "started": True,
        "before": before, "requested_at": requested_at,
    })


@app.route("/api/dashboard/refresh-status")
@_require_login
def api_dashboard_refresh_status():
    """Return current refresh state scoped to the logged-in user."""
    from webapp.dashboard_data import get_refresh_status
    user = _get_current_user()
    salesman_key = get_salesman_key(user)
    before = request.args.get("before", "")
    status = get_refresh_status(salesman_key=salesman_key)
    current = status["last_completed"] or ""
    done = bool(current and current != before)
    return jsonify({
        "done": done,
        "running": status["running"],
        "step": status.get("step", ""),
        "last_requested": status["last_requested"],
        "last_completed": current,
    })


@app.route("/api/reload-users", methods=["POST"])
@_require_login
def api_reload_users():
    """Reload the user map from disk (admin only)."""
    user = _get_current_user()
    if not is_admin(user):
        return jsonify({"error": "Admin only"}), 403
    reload_map()
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
