"""Configuration for the v2 app (test/).

Plain env-var driven settings. Keep this file small; add things as they're
actually needed.
"""

from __future__ import annotations

import os
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = TEST_ROOT.parent


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


USE_MOCK_DATA: bool = _truthy(os.environ.get("USE_MOCK_DATA", "true"))

FLASK_SECRET: str = os.environ.get("V2_FLASK_SECRET") or os.environ.get(
    "FLASK_SECRET", "change-me-in-prod"
)

APP_DB_PATH: Path = Path(os.environ.get("V2_APP_DB") or (TEST_ROOT / "app.db"))

URL_PREFIX: str = os.environ.get("V2_URL_PREFIX", "/v2")

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
# V2_AUTH_MODE=dev  (default): self-serve dev bypass (any email)
# V2_AUTH_MODE=msal          : Microsoft Entra ID via MSAL auth-code flow
AUTH_MODE: str = (os.environ.get("V2_AUTH_MODE") or "dev").strip().lower()

AZURE_TENANT_ID: str = (
    os.environ.get("V2_AZURE_TENANT_ID")
    or os.environ.get("AZURE_TENANT_ID")
    or ""
)
AZURE_CLIENT_ID: str = (
    os.environ.get("V2_AZURE_CLIENT_ID")
    or os.environ.get("AZURE_CLIENT_ID")
    or ""
)
AZURE_CLIENT_SECRET: str = (
    os.environ.get("V2_AZURE_CLIENT_SECRET")
    or os.environ.get("AZURE_CLIENT_SECRET")
    or ""
)
AUTH_REDIRECT_PATH: str = os.environ.get("V2_AUTH_REDIRECT_PATH", "/auth/callback")

# Comma- or semicolon-separated list of admin emails.
_admin_raw = os.environ.get("V2_ADMIN_EMAILS", "")
ADMIN_EMAILS: set[str] = {
    e.strip().lower()
    for e in _admin_raw.replace(";", ",").split(",")
    if e.strip()
}

# Fallback identity used by code paths without a request context.
DEV_USER_EMAIL: str = os.environ.get("V2_DEV_USER", "dev@local")
