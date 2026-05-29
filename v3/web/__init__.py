"""v3 web app factory.

Boots fail-closed: load_config() raises in prod on insecure settings (rule 6),
so an unsafe container never serves traffic. The factory wires config, CSRF, the
"new app" marker, and blueprints. Heavy subsystems (data, jobs, reporting) are
registered as later phases land - this file stays thin.
"""

from __future__ import annotations

from flask import Flask, jsonify

from web.auth.authorization import Authorization, Forbidden
from web.config import Config, load_config
from web.data.connection import from_config
from web.extensions import init_csrf


def create_app(config: Config | None = None) -> Flask:
    cfg = config or load_config()

    app = Flask(__name__, static_folder="static_dist", static_url_path="/static")
    app.config["APP_CONFIG"] = cfg
    # In dev with no secret, use an ephemeral one (sessions won't persist across
    # restarts, which is fine locally). In prod, validate() already guaranteed a
    # real secret, so this never falls back insecurely.
    app.secret_key = cfg.flask_secret or _ephemeral_dev_secret(cfg)

    db = from_config(cfg)
    app.config["DB"] = db
    app.config["AUTHZ"] = Authorization(db)

    init_csrf(app)
    _register_context(app, cfg)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_cli(app, db)
    return app


def _ephemeral_dev_secret(cfg: Config) -> str:
    if cfg.is_prod:  # defensive: should be unreachable after validate()
        raise RuntimeError("prod reached ephemeral secret path")
    import secrets

    return secrets.token_hex(32)


def _register_context(app: Flask, cfg: Config) -> None:
    from flask import url_for

    def _safe_url(endpoint: str, **kw) -> str:
        # Nav links resolve as their blueprints land; until then they're inert (#)
        # so the shell renders at every build stage. A missing endpoint is logged at
        # WARNING (not silently swallowed) so a real routing bug can't hide behind "#".
        try:
            return url_for(endpoint, **kw)
        except Exception:
            app.logger.warning("nav endpoint not registered yet: %s", endpoint)
            return "#"

    @app.context_processor
    def inject_globals():
        nav = {
            "reports": _safe_url("reports.reports_list"),
            "dashboard": _safe_url("dashboard.dashboard"),
            "settings": _safe_url("settings.settings_page"),
            "login": _safe_url("auth.login_page"),
            "logout": _safe_url("auth.logout_route"),
        }
        return {
            "new_app_marker": cfg.new_app_marker,  # removable header pill; deleted at cutover
            "app_env": cfg.app_env,
            "nav": nav,
            # Feature gates (default off). Wired to config flags as those pages land.
            "dashboard_enabled": False,
            "test_site_enabled": False,
        }


def _register_blueprints(app: Flask) -> None:
    from web.blueprints.auth import auth_bp
    from web.blueprints.health import health_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(Forbidden)
    def _forbidden(exc: Forbidden):
        return jsonify({"error": str(exc), "status": exc.status_code}), exc.status_code


def _register_cli(app: Flask, db) -> None:
    @app.cli.command("migrate")
    def migrate_cmd():  # pragma: no cover - invoked via `flask migrate`
        from web.data.migrate import migrate

        applied = migrate(db)
        print("Applied migrations:", applied)
