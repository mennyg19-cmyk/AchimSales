"""Home-site rebuild: v3 look, FastAPI, office doorway or catalog mock."""

from __future__ import annotations

from contextlib import asynccontextmanager

from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import config
import store
from db import init_db
from deps import flash, page, require_csrf, safe_next, session_from_row, session_user
from routes_admin import router as admin_router
from routes_reports import router as reports_router
from routes_schedules import router as schedules_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    store.abandon_orphan_runs()
    store.prune_old_jobs(90)
    yield


def create_app() -> FastAPI:
    config.reporting_api_base()
    application = FastAPI(
        title="Achim Sales Reports",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.add_middleware(
        SessionMiddleware,
        secret_key=config.session_secret(),
        session_cookie="home_session",
        https_only=config.PRODUCTION,
        same_site="lax",
    )
    application.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    application.mount("/static", StaticFiles(directory=str(config.ROOT / "static")), name="static")
    application.include_router(reports_router)
    application.include_router(admin_router)
    application.include_router(schedules_router)

    @application.middleware("http")
    async def always_on_root(request: Request, call_next):
        if request.method == "GET" and request.url.path in {"", "/"}:
            if (request.headers.get("user-agent") or "") == "AlwaysOn":
                return JSONResponse({"status": "ok"})
        response = await call_next(request)
        return response

    @application.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @application.get("/beta")
    def beta_bookmark():
        return RedirectResponse("/", status_code=302)

    @application.get("/login")
    def login_page(request: Request):
        if session_user(request):
            return RedirectResponse(safe_next(request.query_params.get("next")), status_code=302)
        return page(request, "login.html", next_url=safe_next(request.query_params.get("next")))

    @application.post("/login/preview")
    def login_preview(request: Request, next: str = Form("/")):
        if config.PRODUCTION:
            return JSONResponse(
                {"error": "Preview login is disabled when APP_ENV is production."},
                status_code=403,
            )
        row = store.get_user("preview@achimonline.com")
        if row is None or not row["is_active"]:
            return JSONResponse({"error": "Preview admin is missing or disabled."}, status_code=403)
        request.session["user"] = session_from_row(row)
        request.session.pop("impersonating", None)
        return RedirectResponse(safe_next(next), status_code=303)

    @application.post("/login/magic-link")
    def magic_link_stub(request: Request, email: str = Form(""), next: str = Form("/")):
        email = email.strip().lower()
        row = store.get_user(email) if email else None
        if row and not row["is_active"]:
            return JSONResponse({"error": "This account is disabled."}, status_code=403)
        if row and row["is_active"] and row["is_external"] and not config.PRODUCTION:
            request.session["user"] = session_from_row(row)
            flash(request, "Preview shortcut: signed in as the External People row. Live mail is not sent.")
            return RedirectResponse(safe_next(next), status_code=303)
        flash(
            request,
            "Magic link is not wired in this preview. "
            "It will only send when the People row is active and marked External.",
            "warn",
        )
        dest = "/login"
        nxt = safe_next(next)
        if nxt != "/":
            dest += "?next=" + quote(nxt)
        return RedirectResponse(dest, status_code=303)

    @application.post("/logout")
    def logout(request: Request, csrf: str = Form("")):
        denied = require_csrf(request, csrf)
        if denied:
            return denied
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @application.get("/manifest.json")
    def manifest():
        return {
            "name": "Achim Sales Reports",
            "short_name": "Sales",
            "description": "Sales reports",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": config.THEME_COLOR,
            "icons": [
                {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ],
        }

    return application


app = create_app()
