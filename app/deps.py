"""Request helpers shared by routes. Templates live here so routers stay thin."""

from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import catalog
import config
import store

templates = Jinja2Templates(directory=str(config.ROOT / "templates"))

THEME_BODY_CLASS = {
    "light": "",
    "dark": "dark-theme",
    "monochrome": "monochrome-theme",
    "monochrome_dark": "monochrome-dark-theme",
}


def theme(request: Request) -> str:
    value = request.session.get("theme") or "light"
    return value if value in THEME_BODY_CLASS else "light"


def session_user(request: Request) -> dict | None:
    return request.session.get("user")


def is_privileged(user: dict | None) -> bool:
    return bool(user) and user.get("role") in config.PRIVILEGED_ROLES


def is_admin(user: dict | None) -> bool:
    return bool(user) and user.get("role") in {"admin", "developer"}


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(16)
        request.session["csrf"] = token
    return token


def ctx(request: Request, **extra):
    user = session_user(request)
    current = theme(request)
    flash = request.session.pop("flash", None)
    flash_kind = request.session.pop("flash_kind", "success")
    return {
        "request": request,
        "user": user,
        "theme": current,
        "theme_class": THEME_BODY_CLASS[current],
        "asset_v": "home1",
        "flash": flash,
        "flash_kind": flash_kind,
        "csrf": csrf_token(request),
        "is_privileged": is_privileged(user),
        "is_admin": is_admin(user),
        "is_developer": bool(user) and user.get("role") == "developer",
        "impersonating": request.session.get("impersonating"),
        **extra,
    }


def page(request: Request, name: str, **extra):
    return templates.TemplateResponse(request, name, ctx(request, **extra))


def login_redirect():
    return RedirectResponse("/login", status_code=302)


def require_user(request: Request):
    user = session_user(request)
    if user:
        return user
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "Sign in required"}, status_code=401)
    return login_redirect()


def require_admin(request: Request):
    user = session_user(request)
    if user and is_admin(user):
        return user
    if not user:
        return require_user(request)
    return JSONResponse({"error": "Admin only"}, status_code=403)


def flash(request: Request, message: str, kind: str = "success") -> None:
    request.session["flash"] = message
    request.session["flash_kind"] = kind


def session_from_row(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["display_name"],
        "email": row["email"],
        "role": row["role"],
        "sales_group": row.get("sales_group") or "",
        "is_external": bool(row.get("is_external")),
        "can_see_company_views": bool(row.get("can_see_company_views")),
    }


def can_see_report(user: dict, key: str) -> bool:
    spec = catalog.spec(key)
    if spec is None:
        return False
    vis = store.visibility_map()
    if key in vis and not vis[key]:
        return False
    if spec["privileged_only"] and not is_privileged(user):
        return False
    return True


def visible_reports(user: dict) -> list[dict]:
    return [item for item in catalog.REPORTS if can_see_report(user, item["key"])]


def salesman_scope(user: dict) -> str:
    if is_privileged(user) or user.get("role") == "manager":
        return ""
    return user.get("sales_group") or ""
