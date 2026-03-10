"""
Output path resolution for all reports.

All reports write to: D365 F&O/Direct Reports/{report_name}/{sub_report?}/{period_subfolder}/
Working files go to:  D365 F&O/Direct Reports/_working/
"""

import os


def _get_d365_root() -> str:
    """Return the D365 F&O root directory (parent of scripts/)."""
    scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.dirname(scripts_dir)


def get_direct_reports_root() -> str:
    """Return the Direct Reports output root directory."""
    return os.path.join(_get_d365_root(), "Direct Reports")


def get_working_dir() -> str:
    """Return the _working directory for intermediate files."""
    return os.path.join(get_direct_reports_root(), "_working")


def get_output_dir(report_name: str, period_subfolder: str, sub_report: str | None = None) -> str:
    """Build and ensure the output directory for a report.

    Args:
        report_name: e.g. "Ordered Report", "Invoiced Report", "Number 4 Report"
        period_subfolder: e.g. "Daily", "MTD", "YTD", "This Week", "Custom"
        sub_report: optional sub-report name, e.g. "By Item", "By Customer"

    Returns:
        Full path to the output directory (created if needed).
    """
    parts = [get_direct_reports_root(), report_name]
    if sub_report:
        parts.append(sub_report)
    if period_subfolder:
        parts.append(period_subfolder)

    path = os.path.join(*parts)
    os.makedirs(path, exist_ok=True)
    return path


def get_output_path(
    report_name: str,
    period_subfolder: str,
    filename: str,
    sub_report: str | None = None,
) -> str:
    """Build the full output file path for a report.

    Args:
        report_name: e.g. "Ordered Report"
        period_subfolder: e.g. "Daily"
        filename: e.g. "Ordered_Report_2026-02-19.xlsx"
        sub_report: optional, e.g. "By Item"
    """
    out_dir = get_output_dir(report_name, period_subfolder, sub_report)
    return os.path.join(out_dir, filename)
