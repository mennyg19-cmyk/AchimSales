"""Azure Runbook: Salesman Report."""
from reports.salesman.runner import SalesmanReportRunner
from runbooks.base_runbook import run_report_in_runbook

if __name__ == "__main__":
    exit(run_report_in_runbook(SalesmanReportRunner))
