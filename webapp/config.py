"""
Web app configuration.

Loads settings from the parent scripts/.env and adds web-specific config.
"""

import os
import secrets
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from config.settings import get_client_id, get_client_secret, get_tenant_id


TENANT_ID = get_tenant_id()
CLIENT_ID = get_client_id()
CLIENT_SECRET = get_client_secret()
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

SCOPES = ["User.Read"]

REDIRECT_PATH = "/auth/callback"

_fallback_secret = secrets.token_hex(32)
FLASK_SECRET = os.environ.get("FLASK_SECRET_KEY") or _fallback_secret
if FLASK_SECRET == _fallback_secret:
    import warnings
    warnings.warn(
        "FLASK_SECRET_KEY is not set — sessions will not persist across restarts. "
        "Set FLASK_SECRET_KEY in your environment / Azure App Settings.",
        stacklevel=1,
    )

WEBAPP_DIR = os.path.dirname(os.path.abspath(__file__))

REPORT_OUTPUT_DIR = os.path.join(WEBAPP_DIR, "_report_output")
os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)


def _is_dev_app_env() -> bool:
    return os.environ.get("APP_ENV", "prod").strip().lower() == "dev"


def _on_azure() -> bool:
    return bool(os.environ.get("WEBSITE_SITE_NAME") or os.environ.get("WEBSITE_INSTANCE_ID"))


def _dev_bypass_requested() -> bool:
    return os.environ.get("DEV_BYPASS_AUTH", "").strip().lower() in ("1", "true", "yes")


def reject_production_dev_bypass() -> None:
    """Refuse boot when DEV_BYPASS_AUTH is set outside local APP_ENV=dev."""
    if not _dev_bypass_requested():
        return
    if _on_azure() or not _is_dev_app_env():
        raise RuntimeError(
            "DEV_BYPASS_AUTH is forbidden unless APP_ENV=dev (and never on Azure)"
        )


def dev_bypass_auth() -> bool:
    """True only for local APP_ENV=dev with DEV_BYPASS_AUTH set."""
    if not _dev_bypass_requested():
        return False
    if _on_azure() or not _is_dev_app_env():
        return False
    return True


GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

_DEFAULT_PUBLIC_ORIGIN = "https://reports.achimonline.com"


def magic_link_public_origin() -> str:
    """Host used in emailed magic-link URLs. Never taken from the request Host header."""
    explicit = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    if _on_azure():
        return _DEFAULT_PUBLIC_ORIGIN
    return "http://127.0.0.1:5001"
