"""WSGI entry for Azure App Service.

    gunicorn wsgi:application

HTTP only: create the Flask app. Migrations, seeds, job claiming, and the
scheduler run in separate processes (see tools/supervise-web.sh).

/ is v3 in home mode (is_beta=True: reports-only, SQL Reporting API).
/beta/... 302s to the same path without /beta (old bookmarks).
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

from wsgi_dispatch import PrefixRedirectMiddleware


def _write_boot_error(text: str) -> None:
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


def _build_home_app():
    v3_root = str(_REPO_ROOT / "v3")
    if v3_root in sys.path:
        sys.path.remove(v3_root)
    sys.path.insert(0, v3_root)
    import web as v3_web

    cfg = v3_web.load_config(is_beta=True) if hasattr(v3_web, "load_config") else None
    if cfg is None:
        from web.config import load_config as _load

        cfg = _load(is_beta=True)
    return v3_web.create_app(cfg)


def _unavailable(environ, start_response):
    body = b"site unavailable"
    start_response(
        "503 Service Unavailable",
        [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))],
    )
    return [body]


_BETA_REDIRECT = os.environ.get("BETA_URL_PREFIX", "/beta")

try:
    _home = _build_home_app()
    application = PrefixRedirectMiddleware(_home, _BETA_REDIRECT)
    log.info("WSGI ready: v3 home at /, %s redirects", _BETA_REDIRECT)
except Exception:  # noqa: BLE001 - never leave gunicorn with a half-imported module
    import traceback

    log.exception("v3 failed to boot")
    _write_boot_error(traceback.format_exc())
    application = _unavailable


if __name__ == "__main__":
    from werkzeug.serving import run_simple

    port = int(os.environ.get("PORT", "5001"))
    run_simple("0.0.0.0", port, application, use_reloader=False, use_debugger=True)
