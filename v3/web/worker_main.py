"""CLI: ``python -m web.worker_main`` — job claiming, scheduler, heartbeats.

Not an HTTP process. The supervisor starts this next to Gunicorn.
"""

from __future__ import annotations

import logging
import os
import sys


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    from web.background import home_app, run_worker

    run_worker(home_app())
    return 0


if __name__ == "__main__":
    sys.exit(main())
