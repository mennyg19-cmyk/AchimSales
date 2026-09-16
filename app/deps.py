"""Request helpers shared by routes. Templates live here so routers stay thin."""

from __future__ import annotations

import secrets

from urllib.parse import quote

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import catalog
import config
import doorway
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
        "theme_names": ",".join(THEME_BODY_CLASS),
        "theme_color": config.THEME_COLOR,
        "asset_v": "home6",
        "flash": flash,
        "flash_kind": flash_kind,
        "csrf": csrf_token(request),
        "is_privileged": is_privileged(user),
        "is_developer": is_privileged(user) and user.get("role") == "developer",
        "impersonating": request.session.get("impersonating"),
        "data_source": "reporting_api" if doorway.configured() else "mock",
        "graph_configured": config.graph_mail_configured(),
        "entra_configured": config.entra_configured(),
        "production": config.PRODUCTION,
        **extra,
    }


def page(request: Request, name: str, **extra):
    return templates.TemplateResponse(request, name, ctx(request, **extra))


def login_redirect():
    return RedirectResponse("/login", status_code=302)


def need_login(request: Request):
    if session_user(request):
        return None
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "Sign in required"}, status_code=401)
    nxt = request.url.path
    if request.url.query:
        nxt += "?" + request.url.query
    target = safe_next(nxt)
    if target == "/":
        return login_redirect()
    return RedirectResponse("/login?next=" + quote(target), status_code=302)


def safe_next(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value.startswith("/") or value.startswith("//") or "\\" in value or "://" in value:
        return "/"
    return value


def require_csrf(request: Request, form_token: str = ""):
    expected = csrf_token(request)
    got = (
        request.headers.get("x-csrf-token")
        or request.headers.get("x-csrf")
        or form_token
        or ""
    )
    if got and got == expected:
        return None
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {
                "error": "CSRF token missing or wrong. Expected X-CSRF-Token matching the session."
            },
            status_code=403,
        )
    flash(request, "That form expired. Reload the page and try again.", "error")
    return RedirectResponse(str(request.url.path), status_code=303)


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
        "dashboard_enabled": bool(row.get("dashboard_enabled")),
        "test_access": bool(row.get("test_access")),
        "sharepoint_access": bool(row.get("sharepoint_access")),
    }


def can_see_report(user: dict, key: str) -> bool:
    spec = catalog.spec(key)
    if spec is None:
        return False
    if spec["privileged_only"] and not is_privileged(user):
        return False
    override = store.report_access_map(user.get("id") or 0).get(key)
    if override is not None:
        return override
    vis = store.visibility_map()
    if key in vis and not vis[key]:
        return False
    if is_privileged(user) or user.get("role") == "manager":
        return True
    return bool(spec.get("salesman_default", True))


def visible_reports(user: dict) -> list[dict]:
    return [report for report in catalog.REPORTS if can_see_report(user, report["key"])]


def salesman_scope(user: dict) -> str:
    if is_privileged(user) or user.get("role") == "manager":
        return ""
    return user.get("sales_group") or ""


def salesman_keys(user: dict) -> set[str] | None:
    if is_privileged(user) or user.get("role") == "manager":
        return None
    keys: set[str] = set()
    primary = user.get("sales_group") or ""
    if primary:
        keys.add(primary)
    uid = user.get("id")
    if uid:
        keys.update(store.list_user_groups(int(uid)))
    return keys


def _schedule_is_company(row: dict) -> bool:
    return (row.get("view_kind") or row.get("kind") or "") == "company"


def can_read_schedule(user: dict, row: dict) -> bool:
    if is_privileged(user):
        return True
    if row.get("owner_email") == user.get("email"):
        return True
    if user.get("role") == "manager":
        return _schedule_is_company(row)
    return False


def can_read_job(user: dict, job: dict) -> bool:
    if is_privileged(user):
        return True
    return (job.get("owner_email") or "") == user.get("email")


def can_use_view_for_schedule(user: dict, view: dict) -> bool:
    if is_privileged(user):
        return True
    if view.get("kind") == "company":
        return False
    return view.get("owner_email") == user.get("email")
