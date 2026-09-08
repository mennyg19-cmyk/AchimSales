"""
Bridge between the web app and existing report runners.

Calls the report runners programmatically, captures output files,
and reads back the Excel data as DataFrames for in-app display.
"""

import logging
import os
import sys
import traceback
from datetime import datetime

import pandas as pd

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

log = logging.getLogger(__name__)


def _find_newest_xlsx(directory: str, before: float) -> str | None:
    """Find the most recently created .xlsx file in a directory tree after `before` timestamp."""
    newest = None
    newest_time = before
    for root, _dirs, files in os.walk(directory):
        for f in files:
            if f.endswith(".xlsx"):
                path = os.path.join(root, f)
                try:
                    mtime = os.path.getmtime(path)
                    if mtime > newest_time:
                        newest_time = mtime
                        newest = path
                except OSError:
                    continue
    return newest


def _find_all_new_xlsx(directory: str, before: float) -> list[str]:
    """Find all .xlsx files created after `before` timestamp, newest first."""
    found: list[tuple[float, str]] = []
    for root, _dirs, files in os.walk(directory):
        for f in files:
            if f.endswith(".xlsx"):
                path = os.path.join(root, f)
                try:
                    mtime = os.path.getmtime(path)
                    if mtime > before:
                        found.append((mtime, path))
                except OSError:
                    continue
    found.sort(reverse=True)
    return [p for _, p in found]


# Multi-file reports write a master ("all reps") workbook plus individuals.
# Newest-mtime order often makes an individual the primary History download.
_CANONICAL_XLSX_NEEDLE = {
    "salesman": "Monthly Salesmen Report",
    "customer_activity": "Customer_Activity_All_",
}


def _prefer_canonical_xlsx(report_key: str, files: list[str]) -> list[str]:
    """Put the all-reps workbook first when a run also wrote per-salesman files."""
    if len(files) <= 1:
        return files
    needle = _CANONICAL_XLSX_NEEDLE.get(report_key)
    if not needle:
        return files
    preferred = [p for p in files if needle in os.path.basename(p)]
    if not preferred:
        return files
    rest = [p for p in files if p not in preferred]
    return preferred + rest


def _read_excel_sheets(filepath: str) -> dict[str, list[dict]]:
    """Read an Excel file and return {sheet_name: [row_dicts]} for display."""
    try:
        xls = pd.ExcelFile(filepath)
        result = {}
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            df = df.fillna("")
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = df[col].dt.strftime("%Y-%m-%d").fillna("")
                elif pd.api.types.is_float_dtype(df[col]):
                    pass  # keep as float for JS formatting
            result[sheet] = df.to_dict(orient="records")
        return result
    except Exception:
        log.exception("Failed to read Excel file: %s", filepath)
        return {}


_REPORT_PRIMARY_MONEY_COL = {
    "invoiced": ["Total Invoice"],
    "ordered": ["SubTotal"],
    "salesman": ["Total Invoice", "SubTotal Invoices"],
    "customer_activity": ["Total Invoice", "SubTotal"],
    "customer_aging": ["Balance", "Amount", "Total"],
    "number_4": ["Total Invoice", "SubTotal"],
}


def _compute_summary(sheets: dict[str, list[dict]], report_key: str) -> dict:
    """Compute summary stats from the report data for the dashboard cards.

    Picks a single primary money column per report to avoid double-counting
    overlapping fields (e.g. SubTotal vs Total Invoice).
    """
    summary = {}

    first_sheet = next(iter(sheets.values()), [])
    if not first_sheet:
        return summary

    df = pd.DataFrame(first_sheet)
    summary["total_rows"] = len(df)

    preferred = _REPORT_PRIMARY_MONEY_COL.get(report_key, [])
    primary_col = None
    for candidate in preferred:
        if candidate in df.columns:
            primary_col = candidate
            break

    if not primary_col:
        money_keywords = ("total invoice", "subtotal", "total", "amount", "net", "revenue")
        for kw in money_keywords:
            for c in df.columns:
                if kw in c.lower():
                    primary_col = c
                    break
            if primary_col:
                break

    if primary_col:
        try:
            vals = pd.to_numeric(df[primary_col], errors="coerce")
            s = vals.sum()
            if pd.notna(s) and s != 0:
                summary[f"total_{primary_col}"] = round(float(s), 2)
        except Exception:
            pass

    count_cols = [c for c in df.columns if any(kw in c.lower() for kw in
                  ("order", "invoice", "customer"))]
    for col in count_cols[:3]:
        try:
            summary[f"{col}_unique"] = int(df[col].nunique())
        except Exception:
            pass

    return summary


def run_ordered_report(params: dict) -> dict:
    """Run the Ordered Report and return results."""
    from reports.ordered.runner import OrderedReportRunner

    argv = []
    if params.get("period") and params["period"] != "custom":
        argv.extend(["--period", params["period"]])
    if params.get("from_date") and params.get("to_date"):
        argv.extend(["--from", params["from_date"], "--to", params["to_date"]])
    elif params.get("date"):
        argv.extend(["--date", params["date"]])
    if params.get("salesman"):
        argv.extend(["--salesman", params["salesman"]])
    if params.get("customers"):
        argv.append("--customer")
        argv.extend(params["customers"])
    elif params.get("customer"):
        argv.extend(["--customer", params["customer"]])
    if params.get("status"):
        argv.extend(["--status", params["status"]])

    return _run_class_report(OrderedReportRunner, argv, "ordered")


def run_invoiced_report(params: dict) -> dict:
    """Run the Invoiced Report and return results."""
    from reports.invoiced.runner import InvoicedReportRunner

    argv = []
    if params.get("period") and params["period"] != "custom":
        argv.extend(["--period", params["period"]])
    if params.get("from_date") and params.get("to_date"):
        argv.extend(["--from", params["from_date"], "--to", params["to_date"]])
    elif params.get("date"):
        argv.extend(["--date", params["date"]])
    if params.get("salesman"):
        argv.extend(["--salesman", params["salesman"]])
    if params.get("customers"):
        argv.append("--customer")
        argv.extend(params["customers"])
    elif params.get("customer"):
        argv.extend(["--customer", params["customer"]])

    return _run_class_report(InvoicedReportRunner, argv, "invoiced")


def run_salesman_report(params: dict) -> dict:
    """Run the Salesman Report and return results."""
    from reports.salesman.runner import SalesmanReportRunner

    argv = []
    if params.get("year"):
        argv.extend(["--year", str(params["year"])])

    return _run_class_report(SalesmanReportRunner, argv, "salesman")


def run_number4_report(params: dict) -> dict:
    """Run the Number 4 Report and return results."""
    from reports.number_4.runner import Number4ReportRunner
    return _run_class_report(Number4ReportRunner, [], "number_4")


def run_customer_activity(params: dict) -> dict:
    """Run the Customer Activity Report and return results.

    When a salesman or manager runs this on demand, ``params`` carries a
    salesman scope so we only generate that rep's file(s) -- never the full
    all-salesmen set. Admins (no scope, or salesman == 'all') get everything.
    """
    from reports.customer_activity.runner import run as activity_run
    from config.paths import get_direct_reports_root
    import time

    # Resolve the salesman scope from the request params.
    salesman_keys: list[str] | None = None
    if params.get("salesman_list"):
        salesman_keys = [s for s in params["salesman_list"] if s]
    else:
        sk = (params.get("salesman") or "").strip()
        if sk and sk.lower() != "all":
            salesman_keys = [sk]

    output_root = get_direct_reports_root()
    before = time.time()

    try:
        activity_run(send_email=False, test_mode=False, salesman_keys=salesman_keys)

        all_files = _prefer_canonical_xlsx(
            "customer_activity",
            _find_all_new_xlsx(os.path.join(output_root, "Salesman Report"), before),
        )
        if not all_files:
            return {"success": False, "error": "Report generated but output file not found."}

        filepath = all_files[0]
        sheets = _read_excel_sheets(filepath)
        summary = _compute_summary(sheets, "customer_activity")
        result = {
            "success": True,
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "sheets": sheets,
            "summary": summary,
        }
        if len(all_files) > 1:
            result["extra_files"] = [
                {"filepath": p, "filename": os.path.basename(p)} for p in all_files[1:]
            ]
        return result
    except Exception as e:
        log.exception("Customer Activity failed")
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


def run_customer_aging(params: dict) -> dict:
    """Run the Customer Aging Report and return results."""
    from reports.customer_aging.runner import CustomerAgingReportRunner

    argv = []
    if params.get("salesman"):
        argv.extend(["--salesman", params["salesman"]])
    if params.get("customers"):
        argv.append("--customer")
        argv.extend(params["customers"])
    elif params.get("customer"):
        argv.extend(["--customer", params["customer"]])

    return _run_class_report(CustomerAgingReportRunner, argv, "customer_aging")


def _safe_path_part(raw: str, fallback: str) -> str:
    """Single directory name only. Reject traversal and empty junk."""
    if not raw or ".." in raw or "/" in raw or "\\" in raw:
        return fallback
    cleaned = "".join(
        c if c.isalnum() or c in (" ", "-", "_") else "_" for c in raw
    ).strip()
    return cleaned or fallback


def _copy_to_preset_dir(filepath: str, salesman_key: str, preset_name: str) -> str:
    """Copy a report file into the salesman/<key>/<preset_name>/ directory."""
    import shutil
    from config.paths import get_direct_reports_root

    safe_preset = _safe_path_part(preset_name, "preset")
    safe_sm = _safe_path_part(salesman_key, "shared")
    dest_dir = os.path.join(get_direct_reports_root(), "salesman", safe_sm, safe_preset)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, os.path.basename(filepath))
    shutil.copy2(filepath, dest_path)
    return dest_path


def _run_class_report(runner_cls, argv: list[str], report_key: str) -> dict:
    """Run a BaseReportRunner subclass and capture results.

    For runners that produce multiple output files (e.g. Number 4's
    By Item + By Customer), ``extra_files`` carries the additional paths
    so callers can surface all downloads.
    """
    from config.paths import get_direct_reports_root
    import time

    output_root = get_direct_reports_root()
    before = time.time()

    try:
        runner = runner_cls()
        exit_code = runner.main(argv)

        if exit_code != 0:
            return {"success": False, "error": f"Report exited with code {exit_code}"}

        report_name = runner.report_name
        search_dir = os.path.join(output_root, report_name)
        all_files = _prefer_canonical_xlsx(
            report_key, _find_all_new_xlsx(search_dir, before),
        )

        if not all_files:
            search_dir = output_root
            all_files = _prefer_canonical_xlsx(
                report_key, _find_all_new_xlsx(search_dir, before),
            )

        if not all_files:
            return {
                "success": True,
                "filepath": None,
                "filename": None,
                "sheets": {},
                "summary": {"message": "Report completed but no data found for the selected parameters."},
            }

        filepath = all_files[0]
        sheets = _read_excel_sheets(filepath)
        summary = _compute_summary(sheets, report_key)

        result = {
            "success": True,
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "sheets": sheets,
            "summary": summary,
        }

        if len(all_files) > 1:
            extra = []
            for ef in all_files[1:]:
                extra.append({"filepath": ef, "filename": os.path.basename(ef)})
            result["extra_files"] = extra

        return result

    except Exception as e:
        log.exception("Report %s failed", report_key)
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


REPORT_RUNNERS = {
    "ordered": run_ordered_report,
    "invoiced": run_invoiced_report,
    "salesman": run_salesman_report,
    "number_4": run_number4_report,
    "customer_activity": run_customer_activity,
    "customer_aging": run_customer_aging,
}


def run_report(report_key: str, params: dict) -> dict:
    """Dispatch to the appropriate report runner."""
    preset_name = params.pop("_preset_name", None)
    salesman_key = params.pop("_salesman_key", None)

    runner_fn = REPORT_RUNNERS.get(report_key)
    if not runner_fn:
        return {"success": False, "error": f"Unknown report: {report_key}"}

    result = runner_fn(params)

    if preset_name and result.get("success") and result.get("filepath"):
        try:
            preset_path = _copy_to_preset_dir(result["filepath"], salesman_key or "", preset_name)
            result["filepath"] = preset_path
            result["filename"] = os.path.basename(preset_path)
        except Exception:
            log.exception("Failed to copy report to preset directory")

    return result
