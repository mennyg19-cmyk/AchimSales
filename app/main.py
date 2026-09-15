"""Slice 1 home-site rebuild: v3 look, mock Invoiced JSON, Tabulator."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

ROOT = Path(__file__).resolve().parent
SAMPLE_JSON = ROOT / "fixtures" / "sample-invoiced-response.json"

APP_ENV = os.environ.get("APP_ENV", "preview").strip().lower()
PRODUCTION = APP_ENV in {"prod", "production"}

REPORT_CARDS = (
    ("ordered", "Ordered", False),
    ("invoiced", "Invoiced", False),
    ("salesman", "Salesman", False),
    ("number_4", "Number 4", False),
    ("customer_activity", "Customer Activity", False),
    ("customer_last_order", "Customer's Last Order", True),
    ("item_averages", "Item Averages", False),
    ("sales_by_state", "Sales by State", False),
)

PERIOD_OPTIONS = (
    ("all_time", "All Time"),
    ("mtd", "Month to Date"),
    ("last_month", "Last Month"),
    ("ytd", "Year to Date"),
    ("this_week", "This Week"),
    ("last_7_days", "Last 7 Days"),
    ("daily", "Yesterday"),
    ("custom", "Custom Range"),
)

THEME_BODY_CLASS = {
    "light": "",
    "dark": "dark-theme",
    "monochrome": "monochrome-theme",
    "monochrome_dark": "monochrome-dark-theme",
}


def _session_secret() -> str:
    env_secret = os.environ.get("SESSION_SECRET", "").strip()
    if PRODUCTION:
        if not env_secret or env_secret == "preview-only-not-for-production":
            raise RuntimeError(
                "APP_ENV is production but SESSION_SECRET is missing. "
                "Refusing to boot (no preview default in production)."
            )
        return env_secret
    return env_secret or "preview-only-not-for-production"


def _load_invoiced_sample() -> dict:
    with SAMPLE_JSON.open(encoding="utf-8") as fh:
        return json.load(fh)


app = FastAPI(title="Achim Sales Reports", docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret(),
    session_cookie="home_session",
    https_only=PRODUCTION,
    same_site="lax",
)
# Azure terminates HTTPS in front of the app. Trust X-Forwarded-* so
# redirects and Secure cookies see https, not the inner http:PORT.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
templates = Jinja2Templates(directory=str(ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def _theme(request: Request) -> str:
    theme = request.session.get("theme") or "light"
    return theme if theme in THEME_BODY_CLASS else "light"


def _user(request: Request) -> dict | None:
    return request.session.get("user")


def _ctx(request: Request, **extra):
    user = _user(request)
    theme = _theme(request)
    flash = request.session.pop("flash", None)
    flash_kind = request.session.pop("flash_kind", "success")
    return {
        "request": request,
        "user": user,
        "theme": theme,
        "theme_class": THEME_BODY_CLASS[theme],
        "asset_v": "slice1",
        "flash": flash,
        "flash_kind": flash_kind,
        **extra,
    }


def _page(request: Request, name: str, **extra):
    return templates.TemplateResponse(request, name, _ctx(request, **extra))


@app.middleware("http")
async def always_on_and_login_gate(request: Request, call_next):
    if request.method == "GET" and request.url.path in {"", "/"}:
        if (request.headers.get("user-agent") or "") == "AlwaysOn":
            return JSONResponse({"status": "ok"})
    response = await call_next(request)
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/beta")
def beta_bookmark():
    return RedirectResponse("/", status_code=302)


@app.get("/login")
def login_page(request: Request):
    if _user(request):
        return RedirectResponse("/", status_code=302)
    return _page(request, "login.html")


@app.post("/login/preview")
def login_preview(request: Request):
    if PRODUCTION:
        return JSONResponse(
            {"error": "Preview login is disabled when APP_ENV is production."},
            status_code=403,
        )
    request.session["user"] = {
        "name": "Preview Admin",
        "email": "preview@achimonline.com",
        "role": "admin",
    }
    return RedirectResponse("/", status_code=303)


@app.post("/login/magic-link")
def magic_link_stub(request: Request, email: str = Form("")):
    request.session["flash"] = (
        "Magic link is not wired in this preview. "
        "It will only send when the People row is active and marked External."
    )
    request.session["flash_kind"] = "warn"
    return RedirectResponse("/login", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.post("/api/settings/theme")
async def set_theme(request: Request):
    if not _user(request):
        return JSONResponse({"error": "Sign in required"}, status_code=401)
    body = await request.json()
    theme = (body or {}).get("theme")
    if theme not in THEME_BODY_CLASS:
        return JSONResponse({"error": "Unknown theme"}, status_code=400)
    request.session["theme"] = theme
    return {"ok": True, "theme": theme}


@app.get("/")
def reports_home(request: Request):
    if not _user(request):
        return RedirectResponse("/login", status_code=302)
    return _page(request, "reports_list.html", active_tab="reports", report_cards=REPORT_CARDS)


@app.get("/reports/invoiced")
def invoiced_page(request: Request):
    if not _user(request):
        return RedirectResponse("/login", status_code=302)
    return _page(
        request,
        "report_view.html",
        active_tab="reports",
        report_key="invoiced",
        report_title="Invoiced",
        period_options=PERIOD_OPTIONS,
    )


@app.get("/api/reports/invoiced/mock")
def invoiced_mock(request: Request):
    if not _user(request):
        return JSONResponse({"error": "Sign in required"}, status_code=401)
    return _load_invoiced_sample()


@app.get("/settings")
def settings_page(request: Request):
    if not _user(request):
        return RedirectResponse("/login", status_code=302)
    return _page(request, "settings.html", active_tab="settings")


@app.get("/schedules")
def schedules_page(request: Request):
    if not _user(request):
        return RedirectResponse("/login", status_code=302)
    return _page(
        request,
        "later.html",
        active_tab="schedules",
        page_title="Schedules",
        page_subtitle="Recurring deliveries from a named saved view. This preview shows the chrome only.",
        later_note="Schedules, Shabbos hold, and Send now land in a later slice. Nothing is scheduled from this preview.",
    )


@app.get("/later/{report_key}")
def later_report(request: Request, report_key: str):
    if not _user(request):
        return RedirectResponse("/login", status_code=302)
    titles = {key: title for key, title, _in_app in REPORT_CARDS}
    title = titles.get(report_key, report_key)
    return _page(
        request,
        "later.html",
        active_tab="reports",
        page_title=title,
        page_subtitle="This report is on the home site today. It is not loaded in slice 1.",
        later_note="Slice 1 is Invoiced mock data only, so you can check the look. Other reports keep their cards and come next.",
    )


@app.get("/manifest.json")
def manifest():
    return {
        "name": "Achim Sales Reports",
        "short_name": "Sales",
        "description": "Sales reports",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#2563eb",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
