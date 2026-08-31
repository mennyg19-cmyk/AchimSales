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


def _env_path_first(names: tuple[str, ...], default: str) -> Path:
    for name in names:
        raw = os.environ.get(name)
        if raw:
            return Path(raw).expanduser()
    return Path(default).expanduser()


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
    precious_db_path: Path
    cache_db_path: Path
    litestream_blob_url: str
    reporting_api_timeout: float = 300.0
    # The dashboard customer mirror is a side feature. When off, its 4-hour cron
    # and boot-prime never enqueue dashboard.refresh jobs - so a slow/wedged
    # Reporting API can't tie up worker slots with a refresh nobody asked for.
    dashboard_refresh_enabled: bool = True
    # Home app (is_beta): reports-only surface. Data comes from the Reporting API.
    # Dashboard stays off. Login is native MSAL / magic-link on this app.
    is_beta: bool = False
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
    litestream_azure_account_name: str = ""
    litestream_azure_account_key: str = ""
    litestream_azure_container: str = ""

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def reports_only(self) -> bool:
        """The live site is reports-only. Field name is still is_beta so Azure
        BETA_PRECIOUS_DB_PATH and the `session` cookie stay unchanged."""
        return self.is_beta

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
            # startup.sh / litestream.yml use the Azure account settings, not BLOB_URL.
            if not self.litestream_azure_account_key:
                problems.append("LITESTREAM_AZURE_ACCOUNT_KEY required in prod (precious.db durability)")
            if not self.litestream_azure_account_name:
                problems.append("LITESTREAM_AZURE_ACCOUNT_NAME required in prod")
            if not self.litestream_azure_container:
                problems.append("LITESTREAM_AZURE_CONTAINER required in prod")
            for label, p in (("PRECIOUS_DB_PATH", self.precious_db_path),
                             ("CACHE_DB_PATH", self.cache_db_path)):
                if _is_unc(p):
                    problems.append(f"{label} must be local disk, not a UNC/SMB share: {p}")
                elif _is_app_service_home(p):
                    problems.append(
                        f"{label} must be on local disk, not the App Service /home share "
                        f"(it's Azure Files/SMB; SQLite WAL can't share its index across "
                        f"processes there, so the job worker stops seeing queued jobs): {p}"
                    )

        if problems:
            raise ConfigError(
                "Refusing to boot - unsafe configuration:\n  - " + "\n  - ".join(problems)
            )


_DEFAULT_SECRET_SENTINEL = "CHANGE_ME"


def _is_unc(path: Path) -> bool:
    """True for Windows UNC (\\\\server\\share) or POSIX //share paths (SMB/Azure Files)."""
    s = str(path)
    return s.startswith("\\\\") or s.startswith("//")


def _is_app_service_home(path: Path) -> bool:
    """True for the App Service /home mount. That mount is Azure Files (SMB), and
    SQLite WAL can't coordinate readers/writers across processes on SMB -- the
    background job worker silently stops seeing jobs the web workers enqueue.
    Keep precious.db/cache.db on local disk (e.g. /tmp/v3data); Litestream gives
    precious.db its durability. (This is the bug _is_unc missed: the share shows
    up as a plain /home path, not a // UNC.)"""
    return str(path).replace("\\", "/").startswith("/home/")


def load_config(*, is_beta: bool = False) -> Config:
    """Build the Config from the environment and validate it.

    APP_ENV defaults to "prod" so that a forgotten setting fails CLOSED (an
    unconfigured deploy refuses to boot rather than silently running dev auth).
    Local dev must opt in explicitly with APP_ENV=dev (see .env.example).

    ``is_beta`` selects home-site DB path defaults (`BETA_PRECIOUS_DB_PATH`).
    Do not flip this to False in production: that would use PRECIOUS_DB_PATH
    and a different cookie name.
    """
    app_env = os.environ.get("APP_ENV", "prod").strip().lower()
    if is_beta:
        precious_default = "./.data/beta_precious.db"
        cache_default = "./.data/beta_cache.db"
        precious_names = ("SITE_PRECIOUS_DB_PATH", "BETA_PRECIOUS_DB_PATH")
        cache_names = ("SITE_CACHE_DB_PATH", "BETA_CACHE_DB_PATH")
    else:
        precious_default = "./.data/precious.db"
        cache_default = "./.data/cache.db"
        precious_names = ("PRECIOUS_DB_PATH",)
        cache_names = ("CACHE_DB_PATH",)
    # Home keeps the `session` cookie, so it must use FLASK_SECRET_KEY
    # (same value leftover Live cookies were signed with).
    if is_beta:
        flask_secret = (
            os.environ.get("FLASK_SECRET_KEY", "").strip()
            or os.environ.get("FLASK_SECRET", "").strip()
        )
    else:
        flask_secret = os.environ.get("FLASK_SECRET", "").strip()
    cfg = Config(
        app_env=app_env,
        auth_mode=os.environ.get("AUTH_MODE", "dev").strip().lower(),
        flask_secret=flask_secret,
        tenant_id=os.environ.get("GRAPH_TENANT_ID", "").strip(),
        client_id=os.environ.get("GRAPH_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("GRAPH_CLIENT_SECRET", "").strip(),
        reporting_api_base_url=os.environ.get("REPORTING_API_BASE_URL", "").strip().rstrip("/"),
        reporting_api_key=os.environ.get("REPORTING_API_KEY", "").strip(),
        reporting_api_timeout=float(os.environ.get("REPORTING_API_TIMEOUT_SECONDS", "300")),
        dashboard_refresh_enabled=(
            False if is_beta else _env_bool("DASHBOARD_REFRESH_ENABLED", True)
        ),
        is_beta=is_beta,
        precious_db_path=_env_path_first(precious_names, precious_default),
        cache_db_path=_env_path_first(cache_names, cache_default),
        litestream_blob_url=os.environ.get("LITESTREAM_BLOB_URL", "").strip(),
        litestream_azure_account_name=os.environ.get("LITESTREAM_AZURE_ACCOUNT_NAME", "").strip(),
        litestream_azure_account_key=os.environ.get("LITESTREAM_AZURE_ACCOUNT_KEY", "").strip(),
        litestream_azure_container=os.environ.get("LITESTREAM_AZURE_CONTAINER", "").strip(),
        outbox_dir=_env_path("OUTBOX_DIR", "./.data/outbox"),
        # Prefer EMAIL_FROM; fall back to live's EMAIL_FROM_ADDRESS (Azure has that).
        email_from=(
            os.environ.get("EMAIL_FROM", "").strip()
            or os.environ.get("EMAIL_FROM_ADDRESS", "").strip()
            or "reports@achimonline.com"
        ),
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
