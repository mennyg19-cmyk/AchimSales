"""The Microsoft (Entra) sign-in handshake."""

# === What's in this file ===
# Two steps of the standard Microsoft authorization-code sign-in:
#   1. build_login_url() -- where to send the browser to sign in.
#   2. complete_login()  -- finish when Microsoft redirects back, and read the
#      person's email and name out of the returned token.
# No credentials are hardcoded; they come from config (the Entra app
# registration). The redirect URL is built from the live request so it matches
# whatever slot the app is mounted on -- and it must be registered in Entra.
#
# _confidential_app() -- the MSAL client built from config
# _redirect_uri() -- this request's callback URL (https-forced behind the proxy)
# build_login_url() -- start sign-in; returns the Microsoft URL to redirect to
# complete_login() -- finish sign-in; returns {'email','name'} or {'error'}

from __future__ import annotations

import logging

from flask import request, session

from ..config import Config

log = logging.getLogger("rebuild.auth")

_FLOW_KEY = "auth_flow"


def _confidential_app(config: Config):
    import msal

    return msal.ConfidentialClientApplication(
        config.client_id,
        authority=config.authority,
        client_credential=config.client_secret,
    )


def _redirect_uri(config: Config) -> str:
    root = request.url_root.rstrip("/")
    # Azure terminates TLS at the proxy, so the request reaches us as http even
    # though the browser used https. Force https so the redirect URL matches the
    # one registered in Entra.
    if request.headers.get("X-Forwarded-Proto") == "https" and root.startswith("http://"):
        root = "https://" + root[len("http://"):]
    return root + config.redirect_path


def build_login_url(config: Config) -> str:
    flow = _confidential_app(config).initiate_auth_code_flow(
        scopes=list(config.msal_scopes),
        redirect_uri=_redirect_uri(config),
    )
    session[_FLOW_KEY] = flow
    return flow["auth_uri"]


def complete_login(config: Config) -> dict:
    """Finish the redirect. Returns {'email','name'} on success or {'error': ...}."""
    flow = session.pop(_FLOW_KEY, None)
    if not flow:
        return {"error": "Sign-in session expired. Please start again."}
    try:
        result = _confidential_app(config).acquire_token_by_auth_code_flow(
            flow, request.values.to_dict()
        )
    except Exception as exc:  # noqa: BLE001 - log detail, return a safe message
        log.exception("MSAL token acquisition failed")
        return {"error": f"Sign-in failed: {exc}"}
    if "error" in result:
        return {"error": result.get("error_description") or result["error"]}
    claims = result.get("id_token_claims") or {}
    email = (claims.get("preferred_username") or claims.get("email") or claims.get("upn") or "").strip().lower()
    if not email:
        return {"error": "Microsoft did not return an email address."}
    return {"email": email, "name": claims.get("name") or email}
