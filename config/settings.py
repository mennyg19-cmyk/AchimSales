"""
Central configuration loader.

Priority: Azure Automation variables > .env file > environment variables > defaults.
"""

import os
import logging

log = logging.getLogger(__name__)

_LOADED_DOTENV = False


def _load_dotenv_once():
    global _LOADED_DOTENV
    if _LOADED_DOTENV:
        return
    _LOADED_DOTENV = True
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.isfile(env_path):
            load_dotenv(env_path)
            log.info("Loaded .env from %s", env_path)
    except ImportError:
        pass


def _get_automation_variable(name: str) -> str | None:
    """Try to read from Azure Automation variables (only available in runbook context)."""
    try:
        from automationassets import get_automation_variable
        v = get_automation_variable(name)
        if v is not None and str(v).strip():
            return str(v).strip()
    except ImportError:
        pass
    except Exception:
        log.debug("Failed to read automation variable '%s'", name, exc_info=True)
    return None


def get_config(name: str, env_keys: list[str] | None = None, default: str = "") -> str:
    """Get a config value. Checks Azure Automation, then .env/env vars, then default.

    Args:
        name: Azure Automation variable name
        env_keys: list of environment variable names to check (in order)
        default: fallback value
    """
    v = _get_automation_variable(name)
    if v:
        return v

    _load_dotenv_once()

    for key in (env_keys or [name]):
        v = os.environ.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()

    return default


def get_d365_env_url() -> str:
    return get_config("D365_ENV_URL", ["D365_ENV_URL", "D365_ENVIRONMENT_URL"])


def get_tenant_id() -> str:
    return get_config("GRAPH_TENANT_ID", ["GRAPH_TENANT_ID", "AZURE_TENANT_ID"])


def get_client_id() -> str:
    return get_config("GRAPH_CLIENT_ID", ["GRAPH_CLIENT_ID", "AZURE_CLIENT_ID"])


def get_client_secret() -> str:
    return get_config("GRAPH_CLIENT_SECRET", ["GRAPH_CLIENT_SECRET", "AZURE_CLIENT_SECRET"])


def get_company_id() -> str:
    return get_config("D365_COMPANY_ID", ["D365_COMPANY_ID"])


def validate_d365_config() -> None:
    """Raise if required D365 config is missing."""
    missing = []
    if not get_d365_env_url():
        missing.append("D365_ENV_URL")
    if not get_tenant_id():
        missing.append("GRAPH_TENANT_ID")
    if not get_client_id():
        missing.append("GRAPH_CLIENT_ID")
    if not get_client_secret():
        missing.append("GRAPH_CLIENT_SECRET")
    if missing:
        raise RuntimeError(f"Missing required config: {', '.join(missing)}")
    env_url = get_d365_env_url()
    log.info("D365 config validated: env_url=%s..., company=%s",
             env_url[:30] if len(env_url) > 30 else env_url,
             get_company_id() or "(default)")


# ---------------------------------------------------------------------------
# Email (Amazon Weekly report)
# ---------------------------------------------------------------------------

def get_email_recipients() -> list[str]:
    """Comma- or semicolon-separated list of email addresses for Amazon Weekly report. Empty = no email."""
    raw = get_config("AMAZON_EMAIL_RECIPIENTS", ["AMAZON_EMAIL_RECIPIENTS"], default="")
    if not raw or not str(raw).strip():
        return []
    return [a.strip() for a in str(raw).replace(";", ",").split(",") if a.strip()]


def get_smtp_host() -> str:
    return get_config("SMTP_HOST", ["SMTP_HOST"], default="smtp.office365.com")


def get_smtp_port() -> int:
    try:
        return int(get_config("SMTP_PORT", ["SMTP_PORT"], default="587"))
    except ValueError:
        return 587


def get_smtp_user() -> str:
    return get_config("SMTP_USER", ["SMTP_USER", "EMAIL_FROM"])


def get_smtp_password() -> str:
    return get_config("SMTP_PASSWORD", ["SMTP_PASSWORD", "EMAIL_PASSWORD"])


def get_graph_email_from() -> str:
    """When using Graph to send mail: the mailbox to send from (UPN, e.g. reports@company.com). Empty = do not use Graph for email."""
    return get_config("AMAZON_EMAIL_FROM", ["EMAIL_FROM_ADDRESS", "AMAZON_EMAIL_FROM", "GRAPH_EMAIL_FROM"], default="").strip()


def get_alert_recipients() -> list[str]:
    """Semicolon-separated list of addresses that receive operational alerts (failures, digests)."""
    raw = get_config("ALERT_RECIPIENTS", ["ALERT_RECIPIENTS"], default="")
    if not raw or not str(raw).strip():
        return []
    return [a.strip() for a in str(raw).replace(",", ";").split(";") if a.strip()]


def get_test_email() -> str:
    """Email address used when ``--test`` flag is passed. All emails are redirected here."""
    return get_config("TEST_EMAIL", ["TEST_EMAIL"], default="")
