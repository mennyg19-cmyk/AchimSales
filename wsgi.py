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


def _write_boot_error(text: str) -> None:
    """Best-effort dump of a v3 boot traceback to a downloadable location."""
    import tempfile

    for candidate in (
        os.environ.get("V3_BOOT_ERROR_LOG"),
        "/home/LogFiles/v3_boot_error.log",
        os.path.join(tempfile.gettempdir(), "v3_boot_error.log"),
    ):
        if not candidate:
            continue
        try:
            os.makedirs(os.path.dirname(candidate), exist_ok=True)
            with open(candidate, "w", encoding="utf-8") as fh:
                fh.write(text)
            log.error("v3 boot error written to %s", candidate)
            return
        except Exception:  # noqa: BLE001 - try the next candidate
            continue


def _bootstrap_v3_async(v3_web, app) -> None:
    """Run v3's migrate/seed/worker-start OFF the worker-import path.

    bootstrap_background touches SQLite (migrations + seeding) and starts the job
    worker. Doing that synchronously during `import wsgi` can block the gunicorn
    worker long enough to miss Azure's container warmup probe, which silently kills
    the whole site. Running it in a daemon thread lets the dispatcher come up
    immediately; v3's schema/seed land a moment later (healthz + login start don't
    need them).
    """
    import threading

    def _run():
        try:
            v3_web.bootstrap_background(app)
            log.info("v3 bootstrap_background complete")
        except Exception:  # noqa: BLE001 - never crash the process from a daemon thread
            log.exception("v3 bootstrap_background failed (v3 stays mounted, may be degraded)")

    threading.Thread(target=_run, name="v3-bootstrap", daemon=True).start()


def _build_v3_app():
    """Create the v3 app (fast, pure wiring). Bootstrap runs async, not here."""
    v3_root = str(_REPO_ROOT / "v3")
    # Insert at the FRONT so v3's top-level packages (web, report_engine) win over
    # any same-named site-package. Live/v2 import webapp / test.webapp, never these
    # names, so this can't shadow them.
    if v3_root in sys.path:
        sys.path.remove(v3_root)
    sys.path.insert(0, v3_root)
    import web as v3_web

    app = v3_web.create_app()
    _bootstrap_v3_async(v3_web, app)
    return app


if _env_bool("V3_MOUNT_ENABLED"):
    try:
        MOUNTS[_TEST_MOUNT] = _build_v3_app()
        log.info("v3 mounted at %s", _TEST_MOUNT)
    except Exception:  # noqa: BLE001 - never let v3 take down live / /test
        import traceback

        log.exception("v3 failed to boot; %s falls back to the v2 app", _TEST_MOUNT)
        _write_boot_error(traceback.format_exc())
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
