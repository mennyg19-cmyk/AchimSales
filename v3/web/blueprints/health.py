"""Health / readiness endpoint.

Rule 9 / security: returns the MINIMUM needed for a load balancer or Azure health
probe. It must NOT leak auth mode, secrets, paths, or any operational detail
(the live `/healthz` leaked config - we do not repeat that).
"""

from __future__ import annotations

from flask import Blueprint

health_bp = Blueprint("health", __name__)


@health_bp.get("/healthz")
def healthz():
    return {"status": "ok"}, 200
