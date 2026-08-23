"""WSGI entry point for the Azure App Service container.

This is the single module gunicorn serves:

    gunicorn wsgi:application

It wires apps behind one process via werkzeug's DispatcherMiddleware:

    /          -> v3 in beta mode              [site home; hybrid SQL/OData]
    /legacy    -> live Flask app (webapp/)     [former home; OData]
    /test      -> v3 app (v3/web/)             [SQL sandbox]
    /beta      -> 302 to the same path without /beta
    /test-next -> ground-up rebuild (rebuild/) [preview]

The old green v2 sandbox (test/) was retired 2026-06-11 -- unused, and its
background mirror refresh kept overloading the on-prem Reporting API.

Safety: Beta-as-home is gated on BETA_MOUNT_ENABLED. If Beta fails to boot,
/ stays the live app so the site is never taken down. /test is gated on
V3_MOUNT_ENABLED the same way. Rebuild mounts behind REBUILD_MOUNT_ENABLED.
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

from wsgi_dispatch import mount_beta_as_home


def _env_bool(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


log.info("Creating live app...")
from webapp.app import app as live_app

MOUNTS: dict[str, object] = {}

_TEST_MOUNT = os.environ.get("V3_URL_PREFIX", "/test")
_BETA_REDIRECT = os.environ.get("BETA_URL_PREFIX", "/beta")
_LEGACY_MOUNT = os.environ.get("LEGACY_URL_PREFIX", "/legacy")


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
    # any same-named site-package. The live app imports webapp, never these names,
    # so this can't shadow it.
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
    except Exception:  # noqa: BLE001 - never let v3 take down live
        import traceback

        log.exception("v3 failed to boot; %s will return 404", _TEST_MOUNT)
        _write_boot_error(traceback.format_exc())
else:
    log.info("V3_MOUNT_ENABLED off; %s not mounted", _TEST_MOUNT)


def _build_rebuild_app():
    """Create the ground-up rebuild app and run its DB setup off the import path.

    The mount path is checked BEFORE the app is built or any DB setup starts, so
    a bad slot can't migrate a database or spawn a bootstrap thread for a mount
    we're going to reject. Like v3, the app build itself is fast (pure wiring)
    and the slow setup runs in a daemon thread so it can't block Azure's warmup.
    """
    import threading

    import rebuild as rebuild_pkg

    config = rebuild_pkg.load_config()
    mount = config.mount_path
    if mount in ("", "/", _TEST_MOUNT, _BETA_REDIRECT, _LEGACY_MOUNT):
        raise ValueError(
            f"REBUILD_MOUNT_PATH resolved to {mount!r}, which collides with /, /legacy, "
            f"/test, or /beta. Use a distinct slot like /test-next."
        )

    app = rebuild_pkg.create_app(config)

    def _run():
        try:
            rebuild_pkg.bootstrap_background(app)
            log.info("rebuild bootstrap_background complete")
        except Exception:  # noqa: BLE001 - never crash the process from a daemon thread
            log.exception("rebuild bootstrap_background failed (rebuild stays mounted, may be degraded)")

    threading.Thread(target=_run, name="rebuild-bootstrap", daemon=True).start()
    return app, mount


if _env_bool("REBUILD_MOUNT_ENABLED"):
    try:
        _rebuild_app, _rebuild_mount = _build_rebuild_app()
        MOUNTS[_rebuild_mount] = _rebuild_app
        log.info("rebuild mounted at %s", _rebuild_mount)
    except Exception:  # noqa: BLE001 - never let the rebuild take down live or /test
        import traceback

        log.exception("rebuild failed to boot; its slot will return 404")
        _write_boot_error(traceback.format_exc())
else:
    log.info("REBUILD_MOUNT_ENABLED off; rebuild not mounted")


def _build_beta_app():
    """Create the Beta surface: v3 look + reports-only + hybrid SQL/OData sources."""
    import threading

    v3_root = str(_REPO_ROOT / "v3")
    if v3_root in sys.path:
        sys.path.remove(v3_root)
    sys.path.insert(0, v3_root)
    import web as v3_web

    cfg = v3_web.load_config(is_beta=True) if hasattr(v3_web, "load_config") else None
    if cfg is None:
        from web.config import load_config as _load

        cfg = _load(is_beta=True)
    app = v3_web.create_app(cfg)

    def _run():
        try:
            v3_web.bootstrap_background(app)
            log.info("beta bootstrap_background complete")
        except Exception:  # noqa: BLE001 - never crash the process from a daemon thread
            log.exception("beta bootstrap_background failed (beta stays mounted, may be degraded)")

    threading.Thread(target=_run, name="beta-bootstrap", daemon=True).start()
    return app


_beta_app = None
if _env_bool("BETA_MOUNT_ENABLED"):
    try:
        if _LEGACY_MOUNT in ("", "/", _TEST_MOUNT):
            raise ValueError(
                f"LEGACY_URL_PREFIX resolved to {_LEGACY_MOUNT!r}, which collides with / or /test"
            )
        _beta_app = _build_beta_app()
        log.info("beta will serve / ; live at %s", _LEGACY_MOUNT)
    except Exception:  # noqa: BLE001 - never let beta take down live or /test
        import traceback

        log.exception("beta failed to boot; / stays the live app")
        _write_boot_error(traceback.format_exc())
        _beta_app = None
else:
    log.info("BETA_MOUNT_ENABLED off; / stays the live app")

if _beta_app is not None:
    application = mount_beta_as_home(
        _beta_app,
        live_app,
        MOUNTS,
        legacy=_LEGACY_MOUNT,
        beta_redirect=_BETA_REDIRECT,
    )
    log.info(
        "WSGI dispatcher ready: beta -> /, live -> %s, extra mounts -> %s, /beta redirects",
        _LEGACY_MOUNT,
        sorted(MOUNTS),
    )
else:
    application = DispatcherMiddleware(live_app, MOUNTS)
    log.info("WSGI dispatcher ready: live -> /, mounts -> %s", sorted(MOUNTS))


if __name__ == "__main__":
    from werkzeug.serving import run_simple

    port = int(os.environ.get("PORT", "5002"))
    run_simple("0.0.0.0", port, application, use_reloader=False, use_debugger=True)
