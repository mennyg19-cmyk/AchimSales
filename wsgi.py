"""WSGI entry point for the Azure App Service container.

This is the single module gunicorn serves:

    gunicorn wsgi:application

It wires three apps behind one process via werkzeug's DispatcherMiddleware:

    /            -> live Flask app (webapp/)            [production, unchanged]
    /test-legacy -> v2 rebuild (test/webapp/)           [the old sandbox, kept]
    /v2          -> v2 rebuild                           [dev alias]
    /test        -> v3 rebuild (v3/web/) when enabled,   [the new app]
                    otherwise the v2 app (current behavior preserved)

Safety: mounting v3 at /test is gated on V3_MOUNT_ENABLED and wrapped in
try/except. If v3 is disabled OR fails to boot (e.g. its prod config isn't set
yet), /test transparently falls back to the v2 app and the live app is never
affected. Flip V3_MOUNT_ENABLED=1 (with v3's env vars set) to cut /test over.
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


def _env_bool(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


log.info("Creating live (/) app...")
from webapp.app import app as live_app

log.info("Creating v2 app...")
from test.webapp.app import create_app as _create_v2_app

_v2_app = _create_v2_app()

# v2 is always reachable at its dev alias and the explicit legacy path.
MOUNTS: dict[str, object] = {
    "/v2": _v2_app,
    os.environ.get("LEGACY_URL_PREFIX", "/test-legacy"): _v2_app,
}

_TEST_MOUNT = os.environ.get("V3_URL_PREFIX", "/test")


def _build_v3_app():
    """Create the v3 app and start its background worker. Raises on bad config."""
    v3_root = _REPO_ROOT / "v3"
    if str(v3_root) not in sys.path:
        sys.path.append(str(v3_root))  # append: never shadow live's top-level modules
    import web as v3_web

    app = v3_web.create_app()
    v3_web.bootstrap_background(app)
    return app


if _env_bool("V3_MOUNT_ENABLED"):
    try:
        MOUNTS[_TEST_MOUNT] = _build_v3_app()
        log.info("v3 mounted at %s", _TEST_MOUNT)
    except Exception:  # noqa: BLE001 - never let v3 take down live / /test
        log.exception("v3 failed to boot; %s falls back to the v2 app", _TEST_MOUNT)
        MOUNTS[_TEST_MOUNT] = _v2_app
else:
    # v3 disabled: preserve the current behavior (v2 serves /test).
    MOUNTS[_TEST_MOUNT] = _v2_app
    log.info("V3_MOUNT_ENABLED off; %s served by the v2 app", _TEST_MOUNT)

application = DispatcherMiddleware(live_app, MOUNTS)

log.info("WSGI dispatcher ready: live -> /, mounts -> %s", sorted(MOUNTS))


if __name__ == "__main__":
    from werkzeug.serving import run_simple

    port = int(os.environ.get("PORT", "5002"))
    run_simple("0.0.0.0", port, application, use_reloader=False, use_debugger=True)
