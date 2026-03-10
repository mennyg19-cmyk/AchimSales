"""Azure Runbook: Ordered Report."""
from reports.ordered.runner import OrderedReportRunner
from runbooks.base_runbook import run_report_in_runbook

if __name__ == "__main__":
    exit(run_report_in_runbook(OrderedReportRunner))
