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


USE_MOCK_DATA: bool = _truthy(os.environ.get("V2_USE_MOCK_DATA", os.environ.get("USE_MOCK_DATA", "false")))

FLASK_SECRET: str = (
    os.environ.get("V2_FLASK_SECRET")
    or os.environ.get("FLASK_SECRET")
    or os.environ.get("FLASK_SECRET_KEY")  # Azure App Service uses FLASK_SECRET_KEY
    or "change-me-in-prod"
)

# Where to keep writable runtime state on Azure App Service.
#
# /home/ is the only persistent path on App Service, but only
# /home/data/ is on the local SSD -- /home/site/wwwroot/ is the
# deploy mount, served from Azure Files (SMB), which is hostile to
# SQLite (file locking flakes, WAL -shm/-wal creation fails with
# "unable to open database file" under any kind of concurrency).
#
# Detection: WEBSITE_SITE_NAME is the canonical "we are on App
# Service" env var. The live app's db.py uses the same signal and
# lands on /home/data/app.db; we mirror that for the v2 sandbox at
# /home/data/v2_app.db so both apps live on the same local SSD.
_ON_AZURE = bool(os.environ.get("WEBSITE_SITE_NAME"))
_AZURE_V2_DATA = Path("/home/data") if _ON_AZURE else None

if _AZURE_V2_DATA is not None:
    try:
        _AZURE_V2_DATA.mkdir(parents=True, exist_ok=True)
    except Exception:
        # If /home/data/ isn't writable for some reason, fall through
        # to the wwwroot path -- it will at least let the app boot so
        # we can surface the error in logs instead of crashing.
        _AZURE_V2_DATA = None

APP_DB_PATH: Path = Path(
    os.environ.get("V2_APP_DB")
    or (_AZURE_V2_DATA / "v2_app.db" if _AZURE_V2_DATA is not None else TEST_ROOT / "app.db")
)

# One-time migration: if the new (correct) Azure path is empty but
# the old wwwroot path has a populated DB from previous boots, copy
# it over so the mirror, user prefs, and refresh history survive the
# path change. Runs at most once per process and is a no-op everywhere
# except the very first boot after this change.
def _migrate_legacy_db_path() -> None:
    if _AZURE_V2_DATA is None:
        return
    if APP_DB_PATH.exists():
        return
    legacy = TEST_ROOT / "app.db"
    if not legacy.exists():
        return
    try:
        import shutil
        APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Copy the main DB plus any leftover -wal/-shm sidecars so
        # we don't lose recently-committed transactions still living
        # in the write-ahead log.
        shutil.copy2(legacy, APP_DB_PATH)
        for suffix in ("-wal", "-shm"):
            side = legacy.with_name(legacy.name + suffix)
            if side.exists():
                shutil.copy2(side, APP_DB_PATH.with_name(APP_DB_PATH.name + suffix))
    except Exception:
        # Don't crash boot if the copy fails. Worst case: a fresh
        # empty DB at the new location.
        pass


_migrate_legacy_db_path()

# Email outbox folder (for test sandbox .eml files)
OUTBOX_DIR: Path = Path(
    os.environ.get("V2_OUTBOX_DIR")
    or (_AZURE_V2_DATA / "outbox" if _AZURE_V2_DATA is not None else REPO_ROOT / "test" / "outbox")
)

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
    or os.environ.get("GRAPH_TENANT_ID")  # Azure App Service uses GRAPH_*
    or ""
)
AZURE_CLIENT_ID: str = (
    os.environ.get("V2_AZURE_CLIENT_ID")
    or os.environ.get("AZURE_CLIENT_ID")
    or os.environ.get("GRAPH_CLIENT_ID")
    or ""
)
AZURE_CLIENT_SECRET: str = (
    os.environ.get("V2_AZURE_CLIENT_SECRET")
    or os.environ.get("AZURE_CLIENT_SECRET")
    or os.environ.get("GRAPH_CLIENT_SECRET")
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
