"""Azure Runbook: Customer Activity Report.

Runs the report with email enabled (monthly schedule),
then uploads results to SharePoint.
"""
from reports.customer_activity.runner import run
from runbooks.base_runbook import _upload_results
from core.logging import setup_logging

import logging
import sys

log = logging.getLogger(__name__)


def main() -> int:
    setup_logging()
    log.info("=== Azure Runbook: Customer Activity Report ===")

    try:
        exit_code = run(send_email=True)
        if exit_code != 0:
            log.error("Report runner returned exit code %d", exit_code)
            return exit_code

        _upload_results()
        log.info("=== Azure Runbook: Customer Activity Report completed ===")
        return 0

    except Exception:
        log.exception("Runbook failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
