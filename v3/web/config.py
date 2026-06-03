"""Single settings module for the v3 web app.

Non-negotiable (rule 6): no insecure defaults. The app REFUSES to boot in
production (`APP_ENV=prod`) when auth is in dev mode or the Flask secret is
unset/default. Everything is environment-driven; nothing secret is hardcoded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_TRUE = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser()


class ConfigError(RuntimeError):
    """Raised when the environment is unsafe to boot (fail-closed)."""


@dataclass(frozen=True)
class Config:
    app_env: str
    auth_mode: str
    flask_secret: str
    tenant_id: str
    client_id: str
    client_secret: str
    reporting_api_base_url: str
    reporting_api_key: str
    reporting_api_timeout: float
    precious_db_path: Path
    cache_db_path: Path
    litestream_blob_url: str
    new_app_marker: bool
    redirect_path: str = "/auth/callback"
    msal_scopes: tuple[str, ...] = field(default_factory=lambda: ("User.Read",))
    # Delivery (Phase C) - all optional; absent => email writes .eml to the outbox
    # dir and SharePoint runs in mock mode. None of these gate boot.
    outbox_dir: Path = field(default_factory=lambda: Path("./.data/outbox"))
    email_from: str = "reports@achimonline.com"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    sp_site_url: str = ""
    sp_drive_root: str = "D365 F&O"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    def validate(self) -> None:
        """Fail closed in prod. Never silently fall back to insecure values."""
        problems: list[str] = []

        if self.app_env not in ("dev", "prod"):
            problems.append(f"APP_ENV must be 'dev' or 'prod', got {self.app_env!r}")
        if self.auth_mode not in ("dev", "msal"):
            problems.append(f"AUTH_MODE must be 'dev' or 'msal', got {self.auth_mode!r}")

        if self.is_prod:
            if self.auth_mode == "dev":
                problems.append("AUTH_MODE=dev is forbidden when APP_ENV=prod")
            if not self.flask_secret or self.flask_secret == _DEFAULT_SECRET_SENTINEL:
                problems.append("FLASK_SECRET must be set to a strong value when APP_ENV=prod")
            if self.auth_mode == "msal" and not (self.tenant_id and self.client_id and self.client_secret):
                problems.append("GRAPH_TENANT_ID/CLIENT_ID/CLIENT_SECRET required for AUTH_MODE=msal")
            if not (self.reporting_api_base_url and self.reporting_api_key):
                problems.append("REPORTING_API_BASE_URL and REPORTING_API_KEY required in prod")
            # Rule 5: precious.db on local disk MUST be replicated by Litestream in
            # prod, and must never live on a UNC/SMB share (Azure Files).
            if not self.litestream_blob_url:
                problems.append("LITESTREAM_BLOB_URL required in prod (precious.db durability)")
            for label, p in (("PRECIOUS_DB_PATH", self.precious_db_path),
                             ("CACHE_DB_PATH", self.cache_db_path)):
                if _is_unc(p):
                    problems.append(f"{label} must be local disk, not a UNC/SMB share: {p}")

        if problems:
            raise ConfigError(
                "Refusing to boot - unsafe configuration:\n  - " + "\n  - ".join(problems)
            )


_DEFAULT_SECRET_SENTINEL = "CHANGE_ME"


def _is_unc(path: Path) -> bool:
    """True for Windows UNC (\\\\server\\share) or POSIX //share paths (SMB/Azure Files)."""
    s = str(path)
    return s.startswith("\\\\") or s.startswith("//")


def load_config() -> Config:
    """Build the Config from the environment and validate it.

    APP_ENV defaults to "prod" so that a forgotten setting fails CLOSED (an
    unconfigured deploy refuses to boot rather than silently running dev auth).
    Local dev must opt in explicitly with APP_ENV=dev (see .env.example).
    """
    app_env = os.environ.get("APP_ENV", "prod").strip().lower()
    cfg = Config(
        app_env=app_env,
        auth_mode=os.environ.get("AUTH_MODE", "dev").strip().lower(),
        flask_secret=os.environ.get("FLASK_SECRET", "").strip(),
        tenant_id=os.environ.get("GRAPH_TENANT_ID", "").strip(),
        client_id=os.environ.get("GRAPH_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("GRAPH_CLIENT_SECRET", "").strip(),
        reporting_api_base_url=os.environ.get("REPORTING_API_BASE_URL", "").strip().rstrip("/"),
        reporting_api_key=os.environ.get("REPORTING_API_KEY", "").strip(),
        reporting_api_timeout=float(os.environ.get("REPORTING_API_TIMEOUT_SECONDS", "300")),
        precious_db_path=_env_path("PRECIOUS_DB_PATH", "./.data/precious.db"),
        cache_db_path=_env_path("CACHE_DB_PATH", "./.data/cache.db"),
        litestream_blob_url=os.environ.get("LITESTREAM_BLOB_URL", "").strip(),
        new_app_marker=_env_bool("NEW_APP_MARKER", True),
        outbox_dir=_env_path("OUTBOX_DIR", "./.data/outbox"),
        email_from=os.environ.get("EMAIL_FROM", "reports@achimonline.com").strip(),
        smtp_host=os.environ.get("SMTP_HOST", "").strip(),
        smtp_port=int(os.environ.get("SMTP_PORT", "587") or "587"),
        smtp_user=os.environ.get("SMTP_USER", "").strip(),
        smtp_password=os.environ.get("SMTP_PASSWORD", ""),
        smtp_starttls=_env_bool("SMTP_STARTTLS", True),
        sp_site_url=os.environ.get("SP_SITE_URL", "").strip(),
        sp_drive_root=os.environ.get("DriveRootPath", "D365 F&O").strip().strip("/"),
    )
    cfg.validate()
    return cfg
