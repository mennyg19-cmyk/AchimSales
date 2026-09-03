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


def _dev_bypass_enabled() -> bool:
    return (
        os.environ.get("DEV_BYPASS_AUTH", "").lower() in ("1", "true", "yes")
        and not os.environ.get("WEBSITE_SITE_NAME")
        and os.environ.get("APP_ENV", "").lower() != "prod"
    )


DEV_BYPASS_AUTH = _dev_bypass_enabled()

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")


def _public_base_url_missing_in_prod() -> bool:
    in_azure_or_prod = bool(os.environ.get("WEBSITE_SITE_NAME")) or (
        os.environ.get("APP_ENV", "").lower() == "prod"
    )
    return in_azure_or_prod and not os.environ.get("PUBLIC_BASE_URL", "").strip()


if _public_base_url_missing_in_prod():
    import warnings
    warnings.warn(
        "PUBLIC_BASE_URL is not set — magic-link emails will use the request Host. "
        "Set PUBLIC_BASE_URL to https://reports.achimonline.com in Azure App Settings.",
        stacklevel=1,
    )
