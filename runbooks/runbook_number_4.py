"""Azure Runbook: Number 4 Report."""
from reports.number_4.runner import Number4ReportRunner
from runbooks.base_runbook import run_report_in_runbook

if __name__ == "__main__":
    exit(run_report_in_runbook(Number4ReportRunner))
