"""
Web app configuration.

Loads settings from the parent scripts/.env and adds web-specific config.
"""

import os
import sys
import secrets

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
USER_MAP_PATH = os.path.join(WEBAPP_DIR, "user_map.json")

REPORT_OUTPUT_DIR = os.path.join(WEBAPP_DIR, "_report_output")
os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)

DEV_BYPASS_AUTH = os.environ.get("DEV_BYPASS_AUTH", "").lower() in ("1", "true", "yes")
