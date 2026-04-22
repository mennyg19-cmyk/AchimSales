"""WSGI entry point for the Azure App Service container.

This is the single module gunicorn serves:

    gunicorn wsgi:application

It wires the live Flask app at / and the rebuild (test/) at /v2 through
werkzeug's DispatcherMiddleware, so a single container process serves both
URL prefixes without either app knowing about the other.

Cutover (Phase 3): change `MOUNTS` to `{}` and swap `live_app` for
`create_v2_app()` in the last line. url_for() calls inside test/ keep
working because they already use the URL_PREFIX-aware static endpoint.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("wsgi")

from werkzeug.middleware.dispatcher import DispatcherMiddleware

log.info("Creating live (/) app...")
from webapp.app import app as live_app

log.info("Creating v2 (/v2) app...")
from test.webapp.app import create_app as _create_v2_app

_v2_app = _create_v2_app()

MOUNTS = {"/v2": _v2_app}

application = DispatcherMiddleware(live_app, MOUNTS)

log.info("WSGI dispatcher ready: live -> /, v2 -> /v2")


if __name__ == "__main__":
    from werkzeug.serving import run_simple

    port = int(os.environ.get("PORT", "5002"))
    run_simple("0.0.0.0", port, application, use_reloader=False, use_debugger=True)
