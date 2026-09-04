"""Run one already-claimed job in an isolated interpreter."""

from __future__ import annotations

import logging
import os
import sys

from web import create_app
from web.config import load_config

log = logging.getLogger(__name__)


def run(job_id: str) -> int:
    cfg = load_config(is_beta=os.environ.get("V3_RUN_ONE_BETA") == "1")
    app = create_app(cfg)
    worker = app.config["JOB_WORKER"]
    job = worker.repo.get(job_id)
    if job is None:
        log.error("job child cannot find job %s", job_id)
        return 1
    if job.status != "running":
        log.error("job child expected running job %s, found %s", job_id, job.status)
        return 1
    worker._run(job)
    finished = worker.repo.get(job_id)
    if finished is not None and finished.status == "success":
        return 0
    log.error("job child did not record success for %s", job_id)
    return 1


def main() -> None:
    if len(sys.argv) != 2:
        log.error("usage: python -m web.jobs.run_one <job_id>")
        sys.exit(2)
    sys.exit(run(sys.argv[1]))


if __name__ == "__main__":
    main()
