"""Entry point for running the worker as its OWN process (no Flask).

Run with: python -m rebuild.worker_main

This is the production-shape worker (one container can run gunicorn AND this
side by side). The temporary preview slot runs the worker in-process instead
(WORKER_MODE=in_process), but this is the same Worker code either way.
"""

from __future__ import annotations

import logging


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    from .config import load_config
    from .data.connection import Database
    from .data.migrate import apply_precious_migrations
    from .jobs.handlers import register_all
    from .jobs.types import registry
    from .jobs.worker import Worker

    config = load_config()
    config.validate()

    db = Database(config)
    apply_precious_migrations(db)

    from .reports.seeds import seed_all

    seed_all(db)
    register_all(registry)

    # One process owns the schedule tick. In this standalone-worker shape that's
    # this process; the in-process mode starts the same poller next to the worker.
    from .scheduling.poller import SchedulePoller

    SchedulePoller(db, config).start()
    Worker(db, config, registry).run_forever()


if __name__ == "__main__":
    main()
