"""Entra ID auth-code login. People row required — no self-register upsert."""

from __future__ import annotations

import logging

from fastapi import Request

import config

log = logging.getLogger(__name__)

_FLOW_KEY = "entra_auth_flow"


def _msal_app():
    import msal

    return msal.ConfidentialClientApplication(
        config.graph_client_id(),
        authority=f"https://login.microsoftonline.com/{config.graph_tenant()}",
        client_credential=config.graph_client_secret(),
    )


def redirect_uri(request: Request) -> str:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    host = (
        request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    ).split(",")[0].strip()
    path = config.entra_redirect_path()
    return f"{proto}://{host}{path}"


def public_origin(request: Request) -> str:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    host = (
        request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    ).split(",")[0].strip()
    return f"{proto}://{host}"


def build_login_url(request: Request) -> str:
    flow = _msal_app().initiate_auth_code_flow(
        scopes=["User.Read"],
        redirect_uri=redirect_uri(request),
    )
    request.session[_FLOW_KEY] = flow
    return flow["auth_uri"]


def complete_login(request: Request) -> dict:
    flow = request.session.pop(_FLOW_KEY, None)
    if not flow:
        return {"error": "No auth flow in session. Start login again."}
    params = dict(request.query_params)
    try:
        result = _msal_app().acquire_token_by_auth_code_flow(flow, params)
    except Exception as exc:
        log.exception("MSAL token acquisition failed")
        return {"error": f"Sign-in failed: {exc}"}
    if "error" in result:
        return {"error": result.get("error_description") or result["error"]}
    claims = result.get("id_token_claims") or {}
    email = (
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("upn")
        or claims.get("unique_name")
        or ""
    ).strip().lower()
    if not email:
        return {"error": "Microsoft did not return an email claim."}
    return {"email": email, "name": claims.get("name") or email}
