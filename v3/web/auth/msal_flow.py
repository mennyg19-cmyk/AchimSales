"""MSAL (Entra ID) auth-code flow, config-driven (no hardcoded creds).

Mirrors the live app's flow (webapp/auth.py): authorization-code, https-forced
redirect behind the proxy, email from id_token claims.
"""

from __future__ import annotations

import logging

from flask import request, session

from web.config import Config

log = logging.getLogger(__name__)

_FLOW_KEY = "v3_auth_flow"


def _msal_app(cfg: Config):
    import msal

    return msal.ConfidentialClientApplication(
        cfg.client_id, authority=cfg.authority, client_credential=cfg.client_secret
    )


def _redirect_uri(cfg: Config) -> str:
    from web.auth.public_origin import public_origin

    return public_origin().rstrip("/") + cfg.redirect_path


def build_login_url(cfg: Config) -> str:
    flow = _msal_app(cfg).initiate_auth_code_flow(
        scopes=list(cfg.msal_scopes), redirect_uri=_redirect_uri(cfg)
    )
    session[_FLOW_KEY] = flow
    return flow["auth_uri"]


def complete_login(cfg: Config) -> dict:
    """Finish the redirect. Returns {'email','name'} on success or {'error': ...}."""
    flow = session.pop(_FLOW_KEY, None)
    if not flow:
        return {"error": "No auth flow in session. Start login again."}
    try:
        result = _msal_app(cfg).acquire_token_by_auth_code_flow(flow, request.values.to_dict())
    except Exception:  # noqa: BLE001 - never echo library internals to the browser
        log.exception("MSAL token acquisition failed")
        return {"error": "Sign-in failed. Start login again."}
    if "error" in result:
        log.warning(
            "MSAL token error: %s",
            result.get("error_description") or result.get("error"),
        )
        return {"error": "Sign-in failed. Start login again."}
    claims = result.get("id_token_claims") or {}
    email = (claims.get("preferred_username") or claims.get("email") or claims.get("upn") or "").strip().lower()
    if not email:
        return {"error": "Microsoft did not return an email claim."}
    return {"email": email, "name": claims.get("name") or email}
