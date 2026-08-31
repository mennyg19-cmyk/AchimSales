"""CLI: ``python -m web.jobs.child JOB_ID`` — run one already-claimed job.

The parent worker claimed the row (status=running) and waits with a hard
timeout. This process is killable; it must not start a poller or scheduler.
"""

from __future__ import annotations

import logging
import os
import sys


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1 or not argv[0].strip():
        sys.stderr.write("usage: python -m web.jobs.child JOB_ID\n")
        return 2
    job_id = argv[0].strip()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    log = logging.getLogger("web.jobs.child")
    from web.background import home_app

    app = home_app()
    worker = app.config["JOB_WORKER"]
    job = worker.repo.get(job_id)
    if job is None or job.status != "running":
        log.warning("child: job %s is not running; nothing to do", job_id)
        return 0
    worker._run(job)
    return 0


if __name__ == "__main__":
    sys.exit(main())
