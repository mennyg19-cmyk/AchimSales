"""Azure Runbook: Invoiced Report."""
from reports.invoiced.runner import InvoicedReportRunner
from runbooks.base_runbook import run_report_in_runbook

if __name__ == "__main__":
    exit(run_report_in_runbook(InvoicedReportRunner))
