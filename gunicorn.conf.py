"""Gunicorn hooks for the Azure App Service container.

Only worker 0 runs the email-distribution background loop. Other workers
still serve HTTP (dashboard, reports, API) so memory stays split across
processes without duplicate daily emails.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("gunicorn.conf")


def post_fork(server, worker):
    """Mark leader worker and start email-distribution check on worker 0 only."""
    is_leader = worker.age == 0
    os.environ["GUNICORN_EMAIL_DIST_LEADER"] = "1" if is_leader else "0"
    log.info(
        "post_fork pid=%s worker.age=%s email_dist_leader=%s",
        worker.pid,
        worker.age,
        is_leader,
    )
    if not is_leader:
        return
    try:
        from webapp.services.email_distributions import start_distribution_check

        start_distribution_check()
        log.info("Email distribution check started on leader worker pid=%s", worker.pid)
    except Exception:
        log.exception("Failed to start email distribution check on leader worker")
