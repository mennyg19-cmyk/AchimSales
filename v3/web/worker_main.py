"""CLI: ``python -m web.worker_main`` — job claiming, scheduler, heartbeats.

Not an HTTP process. The supervisor starts this next to Gunicorn.
"""

from __future__ import annotations

import sys

from web.process_log import configure_process_logging


def main() -> int:
    configure_process_logging()
    from web.background import home_app, run_worker

    run_worker(home_app())
    return 0


if __name__ == "__main__":
    sys.exit(main())
