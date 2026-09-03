"""Non-HTTP entry point for v3 job processing and scheduling."""

from __future__ import annotations

import logging
import signal
import sys
from threading import Event

from web import bootstrap_database, create_app, start_worker_services, stop_worker_services
from web.config import load_config, _env_bool

log = logging.getLogger(__name__)
_stopping = Event()


def enabled_apps():
    """Same BETA/V3 mount flags as wsgi.py; keep those two readers in lockstep."""
    apps = []
    if _env_bool("BETA_MOUNT_ENABLED"):
        apps.append(create_app(load_config(is_beta=True)))
    if _env_bool("V3_MOUNT_ENABLED"):
        apps.append(create_app(load_config()))
    return apps


def run_worker_app(app) -> None:
    """Bootstrap and begin background services for one enabled v3 database."""
    bootstrap_database(app)
    start_worker_services(app)


def run() -> int:
    apps = enabled_apps()
    if not apps:
        log.error("worker requires BETA_MOUNT_ENABLED or V3_MOUNT_ENABLED")
        return 1
    for app in apps:
        run_worker_app(app)
    _stopping.wait()
    for app in reversed(apps):
        stop_worker_services(app)
    return 0


def _stop(_signum, _frame) -> None:
    _stopping.set()


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    sys.exit(run())


if __name__ == "__main__":
    main()
