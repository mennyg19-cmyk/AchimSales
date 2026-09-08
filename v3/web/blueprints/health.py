"""Health / readiness endpoint.

Rule 9 / security: returns the MINIMUM needed for a load balancer or Azure health
probe. It must NOT leak auth mode, secrets, paths, or any operational detail
(the live `/healthz` leaked config - we do not repeat that).
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, url_for
from web.jobs.status import is_ready

health_bp = Blueprint("health", __name__)


@health_bp.get("/healthz")
def healthz():
    return {"status": "ok"}, 200


@health_bp.get("/readyz")
def readyz():
    if is_ready(current_app.config["DB"]):
        return {"status": "ready"}, 200
    return {"status": "starting"}, 503


@health_bp.get("/manifest.json")
def manifest():
    """Mount-aware PWA manifest.

    The app can be served under a prefix (e.g. /test via DispatcherMiddleware),
    so start_url/scope/icons are resolved with url_for instead of being hardcoded
    to "/". A static manifest would point the installed app at the wrong origin
    path and break launch + offline scope under the prefix.
    """
    return jsonify({
        "name": "Achim Sales Reports",
        "short_name": "Sales",
        "description": "Sales reports and customer dashboard",
        "start_url": url_for("reports.reports_list"),
        "scope": url_for("health.healthz").rsplit("/", 1)[0] + "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#2563eb",
        "orientation": "portrait",
        "icons": [
            {"src": url_for("static", filename="icon-192.png"),
             "sizes": "192x192", "type": "image/png"},
            {"src": url_for("static", filename="icon-512.png"),
             "sizes": "512x512", "type": "image/png"},
        ],
    })
