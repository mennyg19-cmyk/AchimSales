"""Settings for the rebuilt reports app."""

# === What's in this file ===
# Everything the app needs to run comes from environment variables. Nothing
# secret is hardcoded. In production the app REFUSES to boot when a setting is
# unsafe (dev auth, missing secret, a database path on a network share). That
# "fail closed" rule is why a misconfigured deploy stops loudly instead of
# quietly running insecure.
#
# This app shares one Azure process with the live app and the old /test app, so
# they all see the same environment variables. To avoid stepping on each other,
# this app reads its OWN database paths and mount settings from REBUILD_* names.
# It reuses the shared backend resources (Entra app registration, Reporting API)
# because those point at the same real services.
#
# _env_bool / _env_path -- read a flag or a filesystem path from the environment
# Config -- the frozen settings object every part of the app reads
# Config.validate() -- the fail-closed checks (raises ConfigError on anything unsafe)
# load_config() -- build Config from the environment and validate it

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _to_absolute(path: Path) -> Path:
    """Make a path absolute without requiring it to exist yet.

    Relative paths resolve against the current working directory. On Azure App
    Service that directory is /home/site/wwwroot -- which is the SMB share -- so
    resolving BEFORE the safety check is what catches a relative database path
    that would otherwise quietly land on the share and corrupt SQLite.
    """
    return Path(os.path.abspath(path.expanduser()))

_TRUE = {"1", "true", "yes", "on"}
_DEFAULT_SECRET = "CHANGE_ME"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser()


class ConfigError(RuntimeError):
    """The environment is unsafe to boot. Raised so a bad deploy fails loudly."""


def _is_network_share(path: Path) -> bool:
    """True for a Windows UNC (\\\\server\\share) or POSIX //share path."""
    text = str(path)
    return text.startswith("\\\\") or text.startswith("//")


def _is_app_service_home(path: Path) -> bool:
    """True for the Azure App Service /home mount.

    /home is Azure Files (a network share). SQLite's write-ahead log can't
    coordinate readers and writers across processes on a network share, so the
    background worker silently stops seeing jobs the web side queued. Keep the
    databases on local disk (e.g. /tmp); Litestream gives the durable one its
    backup. This is the bug the plain network-share check misses, because the
    share shows up as a normal /home path, not a // prefix.

    A leading Windows drive letter is stripped first so the check behaves the
    same whether a path is examined on the Linux host or in a local test.
    """
    text = str(path).replace("\\", "/")
    if len(text) >= 2 and text[1] == ":":
        text = text[2:]
    return text.startswith("/home/")


@dataclass(frozen=True)
class Config:
    app_env: str
    auth_mode: str
    flask_secret: str
    # Where this app lives behind the shared dispatcher. Defaults to a temporary
    # slot so the live /test app is untouched until the owner signs off. Taking
    # over /test (and later /) is just changing this value plus an Entra URL.
    mount_path: str
    precious_db_path: Path
    cache_db_path: Path
    litestream_blob_url: str
    require_litestream: bool
    instance_count: int
    tenant_id: str
    client_id: str
    client_secret: str
    reporting_api_base_url: str
    reporting_api_key: str
    reporting_api_timeout: float = 300.0
    msal_scopes: tuple[str, ...] = field(default_factory=lambda: ("User.Read",))

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def redirect_path(self) -> str:
        """The Entra login callback, derived from the mount path.

        The callback URL registered in Entra is this app's public URL + this
        path, e.g. https://report.achimonline.com/test-next/auth/callback.
        """
        return f"{self.mount_path}/auth/callback"

    @property
    def session_cookie_name(self) -> str:
        """A cookie name unique to this mount so it never clashes with the live
        app's or the old /test app's session on the same domain."""
        slug = self.mount_path.strip("/").replace("/", "_") or "root"
        return f"rebuild_{slug}_session"

    def validate(self) -> None:
        problems: list[str] = []

        if self.app_env not in ("dev", "prod"):
            problems.append(f"REBUILD_APP_ENV must be 'dev' or 'prod', got {self.app_env!r}")
        if self.auth_mode not in ("dev", "msal"):
            problems.append(f"REBUILD_AUTH_MODE must be 'dev' or 'msal', got {self.auth_mode!r}")
        if not self.mount_path.startswith("/"):
            problems.append(f"REBUILD_MOUNT_PATH must start with '/', got {self.mount_path!r}")

        if self.is_prod:
            if self.auth_mode == "dev":
                problems.append("REBUILD_AUTH_MODE=dev is forbidden when REBUILD_APP_ENV=prod")
            if not self.flask_secret or self.flask_secret == _DEFAULT_SECRET:
                problems.append("FLASK_SECRET must be a strong value when REBUILD_APP_ENV=prod")
            if self.auth_mode == "msal" and not (self.tenant_id and self.client_id and self.client_secret):
                problems.append("GRAPH_TENANT_ID/CLIENT_ID/CLIENT_SECRET required for msal auth")
            for label, db_path in (
                ("REBUILD_PRECIOUS_DB_PATH", self.precious_db_path),
                ("REBUILD_CACHE_DB_PATH", self.cache_db_path),
            ):
                resolved = _to_absolute(db_path)
                if _is_network_share(resolved):
                    problems.append(f"{label} must be local disk, not a network share: {resolved}")
                elif _is_app_service_home(resolved):
                    problems.append(
                        f"{label} must be on local disk, not the App Service /home share "
                        f"(it's a network share where SQLite's worker coordination breaks). "
                        f"{db_path} resolves to {resolved} -- use an absolute local path like /tmp/rebuilddata."
                    )
            # SQLite + Litestream only works on a SINGLE instance: two instances
            # writing the same file over different disks corrupts it. We can't see
            # Azure's scale setting from inside, so the deploy passes the count in.
            if self.instance_count != 1:
                problems.append(
                    f"REBUILD_INSTANCE_COUNT must be 1 for SQLite (got {self.instance_count}). "
                    f"Scale the App Service to one instance, or move to the Postgres off-ramp first."
                )
            # DELIBERATE TEMPORARY-SLOT EXCEPTION: Litestream is the durable
            # database's backup and becomes mandatory at cutover (plan todo T1.05).
            # Until then the preview slot is allowed to run without it so it can
            # deploy and be reviewed. Turning REBUILD_REQUIRE_LITESTREAM on (which
            # cutover will) restores the hard requirement.
            if self.require_litestream and not self.litestream_blob_url:
                problems.append("REBUILD_LITESTREAM_BLOB_URL required when REBUILD_REQUIRE_LITESTREAM is on")

        if problems:
            raise ConfigError(
                "Refusing to boot - unsafe configuration:\n  - " + "\n  - ".join(problems)
            )


def load_config() -> Config:
    """Build Config from the environment and validate it.

    REBUILD_APP_ENV defaults to 'prod' so a forgotten setting fails closed: an
    unconfigured deploy refuses to boot rather than quietly running dev auth.
    Local dev opts in with REBUILD_APP_ENV=dev.
    """
    cfg = Config(
        app_env=os.environ.get("REBUILD_APP_ENV", "prod").strip().lower(),
        auth_mode=os.environ.get("REBUILD_AUTH_MODE", "dev").strip().lower(),
        flask_secret=os.environ.get("FLASK_SECRET", "").strip(),
        mount_path="/" + os.environ.get("REBUILD_MOUNT_PATH", "/test-next").strip().strip("/"),
        precious_db_path=_env_path("REBUILD_PRECIOUS_DB_PATH", "./.rebuild-data/precious.db"),
        cache_db_path=_env_path("REBUILD_CACHE_DB_PATH", "./.rebuild-data/cache.db"),
        litestream_blob_url=os.environ.get("REBUILD_LITESTREAM_BLOB_URL", "").strip(),
        require_litestream=_env_bool("REBUILD_REQUIRE_LITESTREAM", False),
        instance_count=int(os.environ.get("REBUILD_INSTANCE_COUNT", "1") or "1"),
        tenant_id=os.environ.get("GRAPH_TENANT_ID", "").strip(),
        client_id=os.environ.get("GRAPH_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("GRAPH_CLIENT_SECRET", "").strip(),
        reporting_api_base_url=os.environ.get("REPORTING_API_BASE_URL", "").strip().rstrip("/"),
        reporting_api_key=os.environ.get("REPORTING_API_KEY", "").strip(),
        reporting_api_timeout=float(os.environ.get("REPORTING_API_TIMEOUT_SECONDS", "300") or "300"),
    )
    cfg.validate()
    return cfg
