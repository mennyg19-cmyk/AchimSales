"""Health and diagnostics routes."""

# === What's in this file ===
# /healthz is the cheap, fast check the deploy and the container warmup probe
# hit. It answers "is the app up, can it reach its database, is the schema
# there, is the worker alive". It must never run slow probes that pile up on
# real traffic. Admin-only repair endpoints (integrity check, jobs rebuild)
# arrive with the auth phase, since they need a logged-in admin.
#
# healthz() -- JSON snapshot of app + database + worker state, fast and safe

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from ..app import get_config, get_db
from ..data.connection import utc_now_iso

health_bp = Blueprint("health", __name__)


@health_bp.get("/healthz")
def healthz():
    config = get_config()
    db = get_db()

    database_ok = False
    schema_ready = False
    booted_at = None
    try:
        with db.precious() as conn:
            row = conn.fetchone(
                "SELECT value FROM app_meta WHERE key = 'booted_at'"
            )
            database_ok = True
            schema_ready = row is not None
            booted_at = row["value"] if row else None
    except Exception as exc:  # noqa: BLE001 - report the problem, don't crash the probe
        current_app.logger.warning("healthz database check failed: %s", exc)

    heartbeat = None
    queue_depth = None
    if schema_ready:
        try:
            from ..data.repositories.jobs import JobRepository

            jobs = JobRepository(db, config.job_queue_max, config.job_stale_seconds)
            heartbeat = jobs.latest_heartbeat()
            queue_depth = jobs.queue_depth()
        except Exception as exc:  # noqa: BLE001 - worker stats are best-effort
            current_app.logger.warning("healthz worker check failed: %s", exc)

    payload = {
        "app": "rebuild",
        "status": "ok" if database_ok else "degraded",
        "mount_path": config.mount_path,
        "env": config.app_env,
        "time": utc_now_iso(),
        "database": {"reachable": database_ok, "schema_ready": schema_ready, "booted_at": booted_at},
        "worker": {"mode": config.worker_mode, "heartbeat": heartbeat, "queue_depth": queue_depth},
        "litestream": {"configured": bool(config.litestream_blob_url), "required": config.require_litestream},
    }
    return jsonify(payload), (200 if database_ok else 503)
