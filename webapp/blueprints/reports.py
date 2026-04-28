"""
Reports blueprint.

Routes: /home, /reports, /report/<key>, /report/<key>/run,
        /report/progress/<run_id>, /report/<key>/download,
        /history, /history/download/<record_id>, /history/view/<record_id>
"""

import json
import logging
import os
import threading
import time as _time

from flask import (
    Blueprint, flash, jsonify, redirect, render_template,
    request, send_file, session, url_for,
)

from webapp.helpers import get_current_user, get_salesmen_list, require_login
from webapp.user_map import (
    get_available_reports, get_salesman_key, is_admin, is_manager, is_salesman,
)
from webapp.report_api import run_report
from webapp.history import add_record, delete_record, update_record, get_history, get_record
from webapp.db import (
    add_notification, get_all_users, get_saved_reports,
    get_user_salesman_access,
    log_report_start, log_report_end, get_report_runs,
)

log = logging.getLogger(__name__)


class _ReportCancelled(Exception):
    """Raised inside the background thread when the user cancels a run."""


reports_bp = Blueprint("reports", __name__)

_progress_state: dict[str, dict] = {}
_cancel_flags: dict[str, bool] = {}


@reports_bp.route("/home")
@require_login
def home():
    return redirect(url_for("reports.reports_list"))


@reports_bp.route("/reports")
@require_login
def reports_list():
    user = get_current_user()
    available = get_available_reports(user)
    presets = get_saved_reports(user.get("email", ""))
    return render_template("reports.html", user=user, reports=available,
                           presets=presets, active_tab="reports")


@reports_bp.route("/report/customer-last-order")
@require_login
def customer_last_order_pick():
    """Customer picker for the in-app Customer's Last Order report.

    Salesman users see only their book; admins/managers see everyone they
    have access to. The actual customer list is loaded async via /api/customers.
    """
    user = get_current_user()
    available = get_available_reports(user)
    if "customer_last_order" not in available:
        flash("You do not have access to this report.", "error")
        return redirect(url_for("reports.reports_list"))

    report_cfg = available["customer_last_order"]
    user_is_admin = is_admin(user)
    user_is_manager = is_manager(user)

    salesmen_list = []
    show_salesman_picker = False
    if user_is_admin:
        salesmen_list = get_salesmen_list(user.get("email"))
        show_salesman_picker = True
    elif user_is_manager:
        allowed_keys = set(get_user_salesman_access(user.get("email", "")))
        all_sm = get_salesmen_list(user.get("email"))
        salesmen_list = [s for s in all_sm if s["key"] in allowed_keys]
        show_salesman_picker = bool(salesmen_list)

    return render_template(
        "customer_last_order_pick.html",
        user=user, report=report_cfg,
        show_salesman_picker=show_salesman_picker,
        salesmen_list=salesmen_list,
        active_tab="reports",
    )


def _check_customer_access_for_last_order(user, account, cust_info):
    """Salesman can only see their own book; manager only assigned books.

    Returns True if access is allowed. Flashes + returns False otherwise.
    """
    from webapp.db import normalize_key

    if is_admin(user):
        return True
    cust_sg = (cust_info.get("sales_group") or "").strip()
    norm_cust = normalize_key(cust_sg)
    if is_manager(user):
        allowed = {normalize_key(k) for k in get_user_salesman_access(user.get("email", ""))}
        if norm_cust in allowed:
            return True
    elif get_salesman_key(user):
        if normalize_key(get_salesman_key(user)) == norm_cust:
            return True
    return False


def _common_po_prefix(pos: list[str]) -> str:
    """Return the longest shared prefix across the given POs, stripped of
    trailing dashes/underscores. Falls back to the first PO when nothing
    meaningful is shared.

    Used to render a clean PO header when merged orders look like
    'PO12345' + 'PO12345-addon'.
    """
    pos = [p.strip() for p in pos if p and p.strip()]
    if not pos:
        return ""
    if len(pos) == 1:
        return pos[0]
    prefix = pos[0]
    for p in pos[1:]:
        i = 0
        while i < len(prefix) and i < len(p) and prefix[i] == p[i]:
            i += 1
        prefix = prefix[:i]
    prefix = prefix.rstrip("-_ ").strip()
    return prefix or pos[0]


def _rollup_lines(lines: list[dict]) -> list[dict]:
    """Combine identical (item, sales_price) rows across orders. Different
    items, or same item at different prices, stay as separate rows so the
    rep can see the price discrepancy.
    """
    grouped: dict[tuple[str, float], dict] = {}
    order_for_key: dict[tuple[str, float], list[str]] = {}
    for ln in lines:
        key = (ln["item"], round(float(ln["sales_price"] or 0), 4))
        if key not in grouped:
            grouped[key] = {
                "item":          ln["item"],
                "description":   ln["description"],
                "qty_ordered":   0.0,
                "qty_shipped":   0.0,
                "qty_cancelled": 0.0,
                "sales_price":   ln["sales_price"],
                "total":         0.0,
            }
            order_for_key[key] = []
        g = grouped[key]
        g["qty_ordered"]   += float(ln["qty_ordered"]   or 0)
        g["qty_shipped"]   += float(ln["qty_shipped"]   or 0)
        g["qty_cancelled"] += float(ln["qty_cancelled"] or 0)
        g["total"]         += float(ln["total"]         or 0)
        if ln.get("order_number") and ln["order_number"] not in order_for_key[key]:
            order_for_key[key].append(ln["order_number"])
    rows = list(grouped.values())
    for r, k in zip(rows, grouped.keys()):
        r["qty_ordered"]   = round(r["qty_ordered"], 2)
        r["qty_shipped"]   = round(r["qty_shipped"], 2)
        r["qty_cancelled"] = round(r["qty_cancelled"], 2)
        r["total"]         = round(r["total"], 2)
        r["from_orders"]   = order_for_key[k]
    rows.sort(key=lambda r: r["item"])
    return rows


@reports_bp.route("/api/report/customer-last-order/<account>/recent-invoiced")
@require_login
def api_customer_last_order_recent_invoiced(account):
    """Return the customer's last 10 invoiced orders, for the picker modal."""
    from webapp.services.d365 import fetch_customer_info, fetch_recent_invoiced_orders

    user = get_current_user()
    available = get_available_reports(user)
    if "customer_last_order" not in available:
        return jsonify({"error": "forbidden"}), 403

    cust_info = {}
    try:
        cust_info = fetch_customer_info(account) or {}
    except Exception:
        log.exception("customer info fetch failed for %s", account)

    if not _check_customer_access_for_last_order(user, account, cust_info):
        return jsonify({"error": "forbidden"}), 403

    try:
        orders = fetch_recent_invoiced_orders(account, limit=10)
    except Exception:
        log.exception("recent invoiced fetch failed for %s", account)
        return jsonify({"error": "Could not load invoiced orders."}), 500
    return jsonify({"orders": orders})


@reports_bp.route("/report/customer-last-order/<account>")
@require_login
def customer_last_order_view(account):
    """Show the customer's last invoiced order, with the option to merge in
    earlier invoiced orders ("addon" pattern).

    Pulls live from D365 and runs the Ordered Report's classifier so the
    Qty Shipped / Qty Cancelled columns match the Excel report exactly.
    Designed to be fast enough to flip open during an in-store visit.

    Query params:
        ``orders=ORD123,ORD456`` -- explicit list of orders to merge.
        Omit to auto-load just the most recent invoiced order.
    """
    from webapp.services.d365 import (
        fetch_customer_info,
        fetch_recent_invoiced_orders,
        fetch_orders_with_qty_breakdown,
    )

    user = get_current_user()
    available = get_available_reports(user)
    if "customer_last_order" not in available:
        flash("You do not have access to this report.", "error")
        return redirect(url_for("reports.reports_list"))

    cust_info = {"account": account, "name": account, "sales_group": ""}
    try:
        cust_info = fetch_customer_info(account) or cust_info
    except Exception:
        log.exception("Failed to fetch customer info for %s", account)

    if not _check_customer_access_for_last_order(user, account, cust_info):
        flash("You do not have access to this customer.", "error")
        return redirect(url_for("reports.customer_last_order_pick"))

    requested_orders = [
        o.strip() for o in (request.args.get("orders") or "").split(",")
        if o.strip()
    ]

    headers: list[dict] = []
    lines: list[dict] = []
    error = None
    try:
        if not requested_orders:
            recent = fetch_recent_invoiced_orders(account, limit=1)
            if recent:
                requested_orders = [recent[0]["order_number"]]

        if requested_orders:
            headers, lines = fetch_orders_with_qty_breakdown(account, requested_orders)
    except Exception as e:
        log.exception("Customer last order fetch failed for %s (orders=%s)",
                      account, requested_orders)
        error = str(e)

    rolled = _rollup_lines(lines) if lines else []
    primary = headers[0] if headers else {}

    pos = [h.get("customer_req", "") for h in headers if h.get("customer_req")]
    display_po = _common_po_prefix(pos) if pos else (primary.get("customer_req") or "")

    totals = {
        "qty_ordered":   round(sum(r["qty_ordered"]   for r in rolled), 2),
        "qty_shipped":   round(sum(r["qty_shipped"]   for r in rolled), 2),
        "qty_cancelled": round(sum(r["qty_cancelled"] for r in rolled), 2),
        "total":         round(sum(r["total"]         for r in rolled), 2),
    }

    return render_template(
        "customer_last_order_view.html",
        user=user, customer=cust_info,
        headers=headers, primary=primary, display_po=display_po,
        rolled_lines=rolled, totals=totals,
        selected_orders=requested_orders, error=error,
        active_tab="reports",
    )


@reports_bp.route("/report/<report_key>")
@require_login
def report_form(report_key):
    user = get_current_user()
    available = get_available_reports(user)

    if report_key not in available:
        flash("You do not have access to this report.", "error")
        return redirect(url_for("reports.reports_list"))

    # In-app-only reports have their own dedicated routes.
    if available[report_key].get("in_app_only"):
        if report_key == "customer_last_order":
            return redirect(url_for("reports.customer_last_order_pick"))
        flash("This report has no filter form.", "error")
        return redirect(url_for("reports.reports_list"))

    report_cfg = available[report_key]
    salesman_key = get_salesman_key(user)
    user_is_admin = is_admin(user)
    user_is_manager = is_manager(user)

    admin_default_salesman = None
    salesmen_list = []
    show_salesman_picker = False

    if report_cfg.get("salesman_filter"):
        if user_is_admin:
            salesmen_list = get_salesmen_list(user.get("email"))
            admin_default_salesman = user.get("salesman_key") or None
            show_salesman_picker = True
        elif user_is_manager:
            allowed_keys = set(get_user_salesman_access(user.get("email", "")))
            all_sm = get_salesmen_list(user.get("email"))
            salesmen_list = [s for s in all_sm if s["key"] in allowed_keys]
            show_salesman_picker = bool(salesmen_list)

    preset_params = {}
    if request.args.get("preset"):
        for k, v in request.args.items():
            if k not in ("preset",):
                preset_params[k] = v
        preset_params["customers"] = request.args.getlist("customers")

    app_users = get_all_users() if user_is_admin else []

    return render_template(
        "report_form.html",
        user=user, report_key=report_key, report=report_cfg,
        salesman_key=salesman_key, is_admin=user_is_admin,
        is_manager=user_is_manager,
        show_salesman_picker=show_salesman_picker,
        salesmen_list=salesmen_list, active_tab="reports",
        preset_params=preset_params, app_users=app_users,
        admin_default_salesman=admin_default_salesman,
    )


@reports_bp.route("/report/<report_key>/run", methods=["POST"])
@require_login
def report_run(report_key):
    user = get_current_user()
    available = get_available_reports(user)

    if report_key not in available:
        return jsonify({"success": False, "error": "Access denied"}), 403

    params = request.get_json() or {}
    report_cfg = available[report_key]

    if is_salesman(user) and user.get("salesman_key"):
        if report_cfg.get("salesman_filter"):
            params["salesman"] = user["salesman_key"]
    elif is_manager(user) and report_cfg.get("salesman_filter"):
        allowed_keys = set(get_user_salesman_access(user.get("email", "")))
        requested = params.get("salesman", "")
        if requested and requested in allowed_keys:
            params["salesman"] = requested
        elif len(allowed_keys) == 1:
            params["salesman"] = next(iter(allowed_keys))
        elif allowed_keys:
            params["salesman_list"] = list(allowed_keys)
        else:
            return jsonify({"success": False, "error": "No salesmen assigned to your account"}), 403
    email = user.get("email", "")
    preset_name = params.pop("preset_name", None)
    display_name = f"{preset_name} ({report_cfg.get('name', report_key)})" if preset_name else report_cfg.get("name", report_key)

    record_id = add_record(
        email=email, report_key=report_key,
        report_name=display_name,
        params=params, status="running",
    )

    _progress_state[record_id] = {"step": "starting", "pct": 0, "msg": "Starting..."}
    _cancel_flags[record_id] = False

    def _check_cancelled():
        if _cancel_flags.get(record_id, False):
            raise _ReportCancelled()

    log_report_start(record_id, email, report_key, display_name, params)

    def _update(step, pct, msg, result=None):
        state = {"step": step, "pct": pct, "msg": msg}
        if result is not None:
            state["result"] = result
        _progress_state[record_id] = state

    def _run_in_background():
        final_status = "failed"
        final_error = None
        try:
            _check_cancelled()
            _update("connecting", 10, "Connecting to D365...")
            _time.sleep(0.3)
            _check_cancelled()
            _update("fetching", 25, "Fetching data from D365...")

            run_params = dict(params)
            if preset_name:
                run_params["_preset_name"] = preset_name
                run_params["_salesman_key"] = user.get("salesman_key") or params.get("salesman") or ""
            result = run_report(report_key, run_params)

            _check_cancelled()
            if result.get("success"):
                _update("processing", 70, "Processing data...")
                _time.sleep(0.2)
                _check_cancelled()
                _update("writing", 85, "Writing Excel file...")
                _time.sleep(0.2)
                final_status = "completed" if result.get("filepath") else "no_data"
                update_record(
                    email, record_id,
                    status=final_status,
                    filepath=result.get("filepath"),
                    filename=result.get("filename"),
                    summary=result.get("summary", {}),
                    extra_files=result.get("extra_files", []),
                )
                result.pop("traceback", None)
                _update("done", 100, "Report complete!", result)
            else:
                final_error = result.get("error", "Unknown error")
                update_record(email, record_id, status="failed", error=final_error)
                result.pop("traceback", None)
                _update("error", 100, f"Failed: {final_error}", result)
        except _ReportCancelled:
            final_error = "Cancelled by user"
            update_record(email, record_id, status="failed", error=final_error)
            _update("error", 100, "Report cancelled.",
                    {"success": False, "error": final_error})
        except Exception as e:
            final_error = str(e)
            update_record(email, record_id, status="failed", error=final_error)
            _update("error", 100, f"Failed: {e}",
                    {"success": False, "error": final_error})
        finally:
            log_report_end(record_id, final_status, final_error)
            _cancel_flags.pop(record_id, None)
            report_name = report_cfg.get("name", report_key)
            add_notification(
                user_email=email, ntype="report_ready",
                title=f"{report_name} is ready",
                message="Your report has finished. Tap to view.",
                data={"record_id": record_id, "report_key": report_key},
            )

    threading.Thread(target=_run_in_background, daemon=True).start()
    log.info("Running report %s (run_id=%s) with params: %s (user: %s)",
             report_key, record_id, params, email)
    return jsonify({"run_id": record_id})


@reports_bp.route("/report/progress/<run_id>")
@require_login
def report_progress(run_id):
    state = _progress_state.get(run_id)
    if state:
        if state.get("step") in ("done", "error"):
            _progress_state.pop(run_id, None)
        return jsonify(state)

    # Not in memory -- check the DB (handles multi-worker and fast-finish cases)
    user = get_current_user()
    records = get_history(user.get("email", ""))
    for rec in records:
        if rec.get("record_id") == run_id:
            status = rec.get("status", "")
            if status == "running":
                return jsonify({"step": "fetching", "pct": 30,
                                "msg": "Report is running..."})
            if status in ("completed", "no_data"):
                return jsonify({"step": "done", "pct": 100,
                                "msg": "Report complete!",
                                "result": {"success": True,
                                           "summary": rec.get("summary", {}),
                                           "filename": rec.get("filename")}})
            if status == "failed":
                return jsonify({"step": "error", "pct": 100,
                                "msg": rec.get("error") or "Report failed.",
                                "result": {"success": False,
                                           "error": rec.get("error") or "Report failed."}})

    return jsonify({"step": "starting", "pct": 5, "msg": "Initializing..."})


@reports_bp.route("/report/cancel/<run_id>", methods=["POST"])
@require_login
def report_cancel(run_id):
    """Signal a running report to stop at the next checkpoint."""
    if run_id in _progress_state:
        _cancel_flags[run_id] = True
        return jsonify({"success": True, "message": "Cancel signal sent"})

    user = get_current_user()
    email = user.get("email", "")
    update_record(email, run_id, status="failed", error="Cancelled (report was no longer running on server)")
    log_report_end(run_id, "failed", error="Cancelled (stale)")
    return jsonify({"success": True, "message": "Stale report marked as failed"})


@reports_bp.route("/report/<report_key>/download")
@require_login
def report_download(report_key):
    user = get_current_user()
    filepath = session.get(f"download_{report_key}")

    if not filepath or not os.path.isfile(filepath):
        records = get_history(user.get("email", ""))
        for rec in records:
            if rec.get("report_key") == report_key and rec.get("file_available"):
                filepath = rec["filepath"]
                break

    if not filepath or not os.path.isfile(filepath):
        flash("No report file available for download. Please run the report first.", "error")
        return redirect(url_for("reports.report_form", report_key=report_key))

    return send_file(filepath, as_attachment=True, download_name=os.path.basename(filepath))


@reports_bp.route("/report/download-file")
@require_login
def report_download_file():
    """Download a report output file by path (validated to be under Direct Reports)."""
    from config.paths import get_direct_reports_root

    filepath = request.args.get("path", "")
    if not filepath:
        flash("No file specified.", "error")
        return redirect(url_for("reports.reports_list"))

    reports_root = os.path.realpath(get_direct_reports_root())
    real_path = os.path.realpath(filepath)
    if not real_path.startswith(reports_root) or not real_path.endswith(".xlsx"):
        flash("Invalid file path.", "error")
        return redirect(url_for("reports.reports_list"))

    if not os.path.isfile(real_path):
        flash("File not found.", "error")
        return redirect(url_for("reports.reports_list"))

    return send_file(real_path, as_attachment=True, download_name=os.path.basename(real_path))


# -- History ---------------------------------------------------------------

@reports_bp.route("/history")
@require_login
def history():
    user = get_current_user()
    records = get_history(user.get("email", ""))
    return render_template("history.html", user=user, records=records, active_tab="reports")


@reports_bp.route("/history/download/<record_id>")
@require_login
def history_download(record_id):
    user = get_current_user()
    rec = get_record(user.get("email", ""), record_id)
    if not rec:
        flash("Report not found in history.", "error")
        return redirect(url_for("reports.history"))

    filepath = rec.get("filepath")
    if not filepath or not os.path.isfile(filepath):
        flash("The file for this report is no longer available.", "error")
        return redirect(url_for("reports.history"))

    return send_file(filepath, as_attachment=True,
                     download_name=rec.get("filename", os.path.basename(filepath)))


@reports_bp.route("/history/download-extra/<record_id>/<int:file_idx>")
@require_login
def history_download_extra(record_id, file_idx):
    """Download one of the extra_files attached to a multi-file history record."""
    user = get_current_user()
    rec = get_record(user.get("email", ""), record_id)
    if not rec:
        flash("Report not found in history.", "error")
        return redirect(url_for("reports.history"))

    extras = rec.get("extra_files") or []
    if file_idx < 0 or file_idx >= len(extras):
        flash("File not found in history.", "error")
        return redirect(url_for("reports.history"))

    ef = extras[file_idx]
    fp = ef.get("filepath") if isinstance(ef, dict) else None
    fname = (ef.get("filename") if isinstance(ef, dict) else None) or (
        os.path.basename(fp) if fp else "report.xlsx"
    )
    if not fp or not os.path.isfile(fp):
        flash("The file for this report is no longer available.", "error")
        return redirect(url_for("reports.history"))

    return send_file(fp, as_attachment=True, download_name=fname)


@reports_bp.route("/history/view/<record_id>")
@require_login
def history_view(record_id):
    user = get_current_user()
    rec = get_record(user.get("email", ""), record_id)
    if not rec:
        flash("Report not found in history.", "error")
        return redirect(url_for("reports.history"))

    filepath = rec.get("filepath")
    sheets = {}
    if filepath and os.path.isfile(filepath):
        from webapp.report_api import _read_excel_sheets
        sheets = _read_excel_sheets(filepath)

    return render_template("history_view.html", user=user, record=rec,
                           sheets=sheets, active_tab="reports")


@reports_bp.route("/history/delete/<record_id>", methods=["POST"])
@require_login
def history_delete(record_id):
    """Delete a single history record for the current user."""
    user = get_current_user()
    deleted = delete_record(user.get("email", ""), record_id)
    if deleted:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Record not found"}), 404


# -- Report audit log (admin / developer only) ----------------------------

@reports_bp.route("/report-log")
@require_login
def report_log():
    user = get_current_user()
    if not is_admin(user):
        flash("Access denied.", "error")
        return redirect(url_for("reports.reports_list"))
    runs = get_report_runs(limit=500)
    return render_template("report_log.html", user=user, runs=runs,
                           active_tab="settings")


@reports_bp.route("/runbook-history")
@require_login
def runbook_history():
    user = get_current_user()
    if not is_admin(user):
        flash("Access denied.", "error")
        return redirect(url_for("reports.reports_list"))
    from webapp.db import get_runbook_history
    rows = get_runbook_history(limit=500)
    return render_template("runbook_history.html", user=user, rows=rows,
                           active_tab="settings")
