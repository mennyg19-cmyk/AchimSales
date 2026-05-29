"""v3 web app factory.

Boots fail-closed: load_config() raises in prod on insecure settings (rule 6),
so an unsafe container never serves traffic. The factory wires config, CSRF, the
"new app" marker, and blueprints. Heavy subsystems (data, jobs, reporting) are
registered as later phases land - this file stays thin.
"""

from __future__ import annotations

from flask import Flask

from web.config import Config, load_config
from web.extensions import init_csrf


def create_app(config: Config | None = None) -> Flask:
    cfg = config or load_config()

    app = Flask(__name__)
    app.config["APP_CONFIG"] = cfg
    # In dev with no secret, use an ephemeral one (sessions won't persist across
    # restarts, which is fine locally). In prod, validate() already guaranteed a
    # real secret, so this never falls back insecurely.
    app.secret_key = cfg.flask_secret or _ephemeral_dev_secret(cfg)

    init_csrf(app)
    _register_context(app, cfg)
    _register_blueprints(app)
    return app


def _ephemeral_dev_secret(cfg: Config) -> str:
    if cfg.is_prod:  # defensive: should be unreachable after validate()
        raise RuntimeError("prod reached ephemeral secret path")
    import secrets

    return secrets.token_hex(32)


def _register_context(app: Flask, cfg: Config) -> None:
    @app.context_processor
    def inject_globals():
        # `new_app_marker` drives the small removable header pill; deleted at cutover.
        return {"new_app_marker": cfg.new_app_marker, "app_env": cfg.app_env}


def _register_blueprints(app: Flask) -> None:
    from web.blueprints.health import health_bp

    app.register_blueprint(health_bp)
