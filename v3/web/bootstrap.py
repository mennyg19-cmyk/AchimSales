"""CLI: ``python -m web.bootstrap`` — migrate + seed, then exit.

Gunicorn must not do this. The supervisor runs this once before traffic.
"""

from __future__ import annotations

import logging
import sys

from web.process_log import configure_process_logging


def main() -> int:
    configure_process_logging()
    from web.background import home_app, run_bootstrap_cli

    try:
        run_bootstrap_cli(home_app())
    except Exception:  # noqa: BLE001 - CLI records the marker and exits 1
        logging.getLogger("web.bootstrap").exception("bootstrap failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
