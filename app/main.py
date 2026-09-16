"""Home-site rebuild: v3 look, FastAPI, office doorway or catalog mock."""

from __future__ import annotations

from contextlib import asynccontextmanager

from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import clock
import config
import entra
import magic_link
import store
from db import init_db
from deliver import send_or_outbox
from deps import flash, page, require_csrf, safe_next, session_from_row, session_user
from mail import GraphMailError
from routes_admin import router as admin_router
from routes_dev import router as dev_router
from routes_reports import router as reports_router
from routes_schedules import router as schedules_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    store.abandon_orphan_runs()
    store.prune_old_jobs(90)
    clock.start()
    try:
        yield
    finally:
        clock.stop()


def create_app() -> FastAPI:
    config.reporting_api_base()
    config.validate_boot()
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
    application.include_router(dev_router)
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

    @application.get("/login/entra")
    def login_entra(request: Request, next: str = "/"):
        if not config.entra_configured():
            flash(
                request,
                "Microsoft sign-in is not configured. Set GRAPH_TENANT_ID, GRAPH_CLIENT_ID, and GRAPH_CLIENT_SECRET.",
                "error",
            )
            return RedirectResponse("/login", status_code=302)
        request.session["login_next"] = safe_next(next)
        try:
            url = entra.build_login_url(request)
        except Exception:
            flash(request, "Microsoft sign-in could not start. Check the Entra app registration.", "error")
            return RedirectResponse("/login", status_code=302)
        return RedirectResponse(url, status_code=302)

    @application.get("/auth/callback")
    def auth_callback(request: Request):
        result = entra.complete_login(request)
        if "error" in result:
            flash(request, result["error"], "error")
            return RedirectResponse("/login", status_code=302)
        row = store.get_user(result["email"])
        if row is None:
            return JSONResponse(
                {"error": "No People row for that Microsoft account. An admin must add you first."},
                status_code=403,
            )
        if not row["is_active"]:
            return JSONResponse({"error": "This account is disabled."}, status_code=403)
        request.session["user"] = session_from_row(row)
        request.session["theme"] = row.get("theme") or "light"
        request.session.pop("impersonating", None)
        dest = request.session.pop("login_next", None) or "/"
        return RedirectResponse(safe_next(dest), status_code=302)

    @application.post("/login/preview")
    def login_preview(request: Request, next: str = Form("/")):
        if config.PRODUCTION:
            return JSONResponse(
                {"error": "Preview login is disabled when APP_ENV is production."},
                status_code=403,
            )
        row = store.preview_login_row()
        if row is None:
            return JSONResponse({"error": "Preview admin is missing or disabled."}, status_code=403)
        request.session["user"] = session_from_row(row)
        request.session["theme"] = row.get("theme") or "light"
        request.session.pop("impersonating", None)
        return RedirectResponse(safe_next(next), status_code=303)

    @application.post("/login/magic-link")
    def magic_link_start(request: Request, email: str = Form(""), next: str = Form("/")):
        email = email.strip().lower()
        row = store.get_user(email) if email else None
        if row and not row["is_active"]:
            return JSONResponse({"error": "This account is disabled."}, status_code=403)
        dest = "/login"
        nxt = safe_next(next)
        if nxt != "/":
            dest += "?next=" + quote(nxt)
        if not (row and row["is_active"] and row["is_external"]):
            flash(
                request,
                "Magic link only sends when the People row is active and marked External.",
                "warn",
            )
            return RedirectResponse(dest, status_code=303)
        if config.graph_mail_configured():
            token = magic_link.issue_token(email)
            consume = entra.public_origin(request) + "/login/magic?token=" + quote(token)
            if nxt != "/":
                consume += "&next=" + quote(nxt)
            body = (
                "Sign in to Achim Sales Reports. This link expires in 15 minutes.\n\n" + consume
            )
            try:
                send_or_outbox(
                    recipients=email,
                    subject="Your Achim Sales Reports sign-in link",
                    body=body,
                )
            except GraphMailError as err:
                flash(request, str(err), "error")
                return RedirectResponse(dest, status_code=303)
            flash(request, "Check your email for a 15-minute sign-in link.")
            return RedirectResponse(dest, status_code=303)
        if config.PRODUCTION:
            flash(
                request,
                "Magic link cannot send: Graph mail secrets are not set on this app.",
                "error",
            )
            return RedirectResponse(dest, status_code=303)
        request.session["user"] = session_from_row(row)
        request.session["theme"] = row.get("theme") or "light"
        flash(request, "Preview shortcut: signed in as the External People row. Live mail is not sent.")
        return RedirectResponse(safe_next(next), status_code=303)

    @application.get("/login/magic")
    def magic_link_consume(request: Request, token: str = "", next: str = "/"):
        email = magic_link.read_token(token)
        if not email:
            flash(request, "That sign-in link is invalid or expired.", "error")
            return RedirectResponse("/login", status_code=302)
        row = store.get_user(email)
        if row is None or not row["is_external"]:
            return JSONResponse(
                {"error": "No External People row for that address."},
                status_code=403,
            )
        if not row["is_active"]:
            return JSONResponse({"error": "This account is disabled."}, status_code=403)
        request.session["user"] = session_from_row(row)
        request.session["theme"] = row.get("theme") or "light"
        request.session.pop("impersonating", None)
        return RedirectResponse(safe_next(next), status_code=302)

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
