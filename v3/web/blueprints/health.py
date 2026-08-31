"""Health / readiness endpoints.

Rule 9 / security: liveness returns the MINIMUM needed for a load balancer.
It must NOT leak auth mode, secrets, paths, or any operational detail
(the live `/healthz` leaked config - we do not repeat that).

`/healthz` is liveness (process up). `/readyz` is readiness: precious.db in
prod, no failed Litestream restore, bootstrap did not fail, and (prod) worker
+ scheduler heartbeats are fresh.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, url_for

from web.jobs.limits import (
    SCHEDULER_HEARTBEAT_STALE_SECONDS,
    WORKER_HEARTBEAT_STALE_SECONDS,
)

health_bp = Blueprint("health", __name__)


def bootstrap_failed_marker(cfg) -> Path:
    return Path(cfg.precious_db_path).with_name(".bootstrap-failed")


@health_bp.get("/healthz")
def healthz():
    return {"status": "ok"}, 200


@health_bp.get("/readyz")
def readyz():
    cfg = current_app.config.get("APP_CONFIG")
    if cfg is None:
        return {"status": "not_ready"}, 503
    if bootstrap_failed_marker(cfg).is_file():
        return {"status": "not_ready"}, 503
    if getattr(cfg, "is_prod", False):
        if not Path(cfg.precious_db_path).is_file():
            return {"status": "not_ready"}, 503
        marker = Path(cfg.precious_db_path).with_name(".litestream-restore-failed")
        if marker.is_file():
            return {"status": "not_ready"}, 503
        if not _heartbeats_fresh(current_app):
            return {"status": "not_ready"}, 503
    return {"status": "ok"}, 200


def _heartbeats_fresh(app) -> bool:
    from web.data.repositories.app_settings import AppSettingsRepository

    db = app.config.get("DB")
    if db is None:
        return False
    try:
        settings = AppSettingsRepository(db)
        worker_age = settings.heartbeat_age_seconds("worker_heartbeat")
        sched_age = settings.heartbeat_age_seconds("scheduler_heartbeat")
    except Exception:  # noqa: BLE001 - missing schema or locked DB is not ready
        return False
    if worker_age is None or worker_age > WORKER_HEARTBEAT_STALE_SECONDS:
        return False
    if sched_age is None or sched_age > SCHEDULER_HEARTBEAT_STALE_SECONDS:
        return False
    return True


@health_bp.get("/manifest.json")
def manifest():
    """Mount-aware PWA manifest.

    start_url/scope/icons use url_for so a future URL prefix cannot point the
    installed app at the wrong path.
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
