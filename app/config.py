"""Env and Azure-safe flags. Never treat reports.achimonline.com as the Reporting API."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_ENV = os.environ.get("APP_ENV", "preview").strip().lower()
PRODUCTION = APP_ENV in {"prod", "production"}
THEME_COLOR = "#2563eb"


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


DEFAULT_REPORTING_API_BASE = (
    "https://achim-reporting-api-test-hpadbffpcwe0dnga.westus3-01.azurewebsites.net"
)


def reporting_api_base() -> str:
    raw = (os.environ.get("REPORTING_API_BASE_URL") or DEFAULT_REPORTING_API_BASE).strip().rstrip("/")
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


def graph_tenant() -> str:
    return (os.environ.get("GRAPH_TENANT_ID") or "").strip()


def graph_client_id() -> str:
    return (os.environ.get("GRAPH_CLIENT_ID") or "").strip()


def graph_client_secret() -> str:
    return (os.environ.get("GRAPH_CLIENT_SECRET") or "").strip()


def email_from() -> str:
    return (
        os.environ.get("EMAIL_FROM") or os.environ.get("EMAIL_FROM_ADDRESS") or ""
    ).strip()


def graph_mail_configured() -> bool:
    return bool(graph_tenant() and graph_client_id() and graph_client_secret() and email_from())


def entra_configured() -> bool:
    return bool(graph_tenant() and graph_client_id() and graph_client_secret())


def entra_redirect_path() -> str:
    path = (os.environ.get("ENTRA_REDIRECT_PATH") or "/auth/callback").strip() or "/auth/callback"
    if not path.startswith("/"):
        path = "/" + path
    return path


def clock_disabled() -> bool:
    raw = (os.environ.get("DISABLE_SCHEDULE_CLOCK") or "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))
