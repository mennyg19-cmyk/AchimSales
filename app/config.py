"""Env and Azure-safe flags. Never treat reports.achimonline.com as the Reporting API."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_ENV = os.environ.get("APP_ENV", "preview").strip().lower()
PRODUCTION = APP_ENV in {"prod", "production"}
FIXTURES = ROOT / "fixtures"


def db_path() -> Path:
    return Path(os.environ.get("APP_DB_PATH", str(ROOT / "data" / "home.sqlite")))

LIVE_SITE_HOSTS = {"reports.achimonline.com"}
ROLES = ("admin", "developer", "manager", "salesman")
PRIVILEGED_ROLES = {"admin", "developer"}


def session_secret() -> str:
    env_secret = os.environ.get("SESSION_SECRET", "").strip()
    if PRODUCTION:
        if not env_secret or env_secret == "preview-only-not-for-production":
            raise RuntimeError(
                "APP_ENV is production but SESSION_SECRET is missing. "
                "Refusing to boot (no preview default in production)."
            )
        return env_secret
    return env_secret or "preview-only-not-for-production"


def reporting_api_base() -> str:
    raw = (os.environ.get("REPORTING_API_BASE_URL") or "").strip().rstrip("/")
    if not raw:
        return ""
    host = raw.split("://", 1)[-1].split("/", 1)[0].lower()
    if host in LIVE_SITE_HOSTS:
        raise RuntimeError(
            "REPORTING_API_BASE_URL points at the website host "
            f"{host}. That is not the office doorway. Refusing to boot."
        )
    return raw


def reporting_api_key() -> str:
    return (os.environ.get("REPORTING_API_KEY") or "").strip()
