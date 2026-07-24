"""
Unified CLI entry point for all reports.

Usage:
  python run.py ordered                          # all periods (Daily, MTD, YTD, This Week)
  python run.py ordered --period daily            # single period
  python run.py ordered --from 2026-01-01 --to 2026-01-31
  python run.py invoiced
  python run.py salesman
  python run.py number_4
  python run.py all                               # run all 4 reports
"""

import sys

REPORTS = {
    "ordered": "reports.ordered.runner",
    "invoiced": "reports.invoiced.runner",
    "salesman": "reports.salesman.runner",
    "number_4": "reports.number_4.runner",
    "customer_activity": "reports.customer_activity.runner",
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python run.py <report> [options]")
        print(f"Reports: {', '.join(REPORTS.keys())}, all")
        print("Options: --period <daily|mtd|ytd|this_week>  --date YYYY-MM-DD")
        print("         --from YYYY-MM-DD --to YYYY-MM-DD   --company <id>")
        print("         ordered --email: email customer-filtered runs (AMAZON_EMAIL_RECIPIENTS)")
        print("         customer_activity: use --email to send individual reports")
        sys.exit(0)

    report_name = sys.argv[1].lower().replace("-", "_")
    report_args = sys.argv[2:]

    if report_name == "all":
        exit_code = 0
        for name, module_path in REPORTS.items():
            print(f"\n{'=' * 60}")
            print(f"Running: {name}")
            print(f"{'=' * 60}")
            code = _run_report(module_path, report_args)
            if code != 0:
                exit_code = code
        sys.exit(exit_code)

    if report_name not in REPORTS:
        print(f"Unknown report: {report_name}")
        print(f"Available: {', '.join(REPORTS.keys())}, all")
        sys.exit(1)

    sys.exit(_run_report(REPORTS[report_name], report_args))


def _run_report(module_path: str, argv: list[str]) -> int:
    import importlib
    mod = importlib.import_module(module_path)
    return mod.main(argv)


if __name__ == "__main__":
    main()
