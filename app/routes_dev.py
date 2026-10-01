"""Developer tools: explorer, diagnostics, office doorway proxy."""

from __future__ import annotations

import json
import re
import sqlite3

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

import catalog
import config
import doorway
import report_format
import store
from db import db
from deps import is_privileged, need_login, page, require_csrf, session_user
from routes_admin import _guard_developer

router = APIRouter()


def _json_privileged(request: Request):
    denied = need_login(request)
    if denied:
        return denied
    if not is_privileged(session_user(request)):
        return JSONResponse({"error": "Admin or developer only"}, status_code=403)
    return None


@router.get("/dev/report-formatter")
def report_formatter(request: Request):
    blocked = _guard_developer(request)
    if blocked:
        return blocked
    return page(request, "report_formatter.html", active_tab="settings")


@router.get("/api/dev/report-format")
def api_report_format(request: Request):
    blocked = _json_privileged(request)
    if blocked:
        return blocked
    report_key = (request.query_params.get("report_key") or "ordered").strip()
    known = {item["key"] for item in report_format.report_choices()}
    tabs = report_format.tabs_for(report_key)
    if report_key not in known:
        return JSONResponse({"error": "Unknown report"}, status_code=404)
    kind, key = report_format.parse_format(request.query_params.get("format"))
    layout, format_id, error = report_format.layout_for(report_key, kind, key)
    if error:
        return JSONResponse({"error": error}, status_code=404)
    return {
        "reports": report_format.report_choices(),
        "report_key": report_key,
        "formats": report_format.format_choices(report_key),
        "format_name": format_id,
        "tabs": tabs,
        "layout": layout or {},
    }


@router.post("/api/dev/report-format")
async def api_save_report_format(request: Request):
    blocked = _json_privileged(request)
    if blocked:
        return blocked
    denied = require_csrf(request)
    if denied:
        return denied
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Body must be a JSON object."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "Body must be a JSON object."}, status_code=400)
    report_key = str(body.get("report_key") or "").strip()
    if report_key not in {item["key"] for item in report_format.report_choices()}:
        return JSONResponse({"error": "Unknown report"}, status_code=400)
    raw_name = body.get("format_name")
    if raw_name is not None and not str(raw_name).strip():
        return JSONResponse({"error": "Type a name for the new format."}, status_code=400)
    kind, key = report_format.parse_format(str(raw_name) if raw_name is not None else "")
    saved_id, layout_out, error, status = report_format.save_format(
        report_key, kind, key, body.get("tabs") or [],
    )
    if error:
        return JSONResponse({"error": error}, status_code=status)
    return {"ok": True, "report_key": report_key, "format_name": saved_id, "layout": layout_out}


@router.get("/dev/db-explorer")
def db_explorer(request: Request):
    blocked = _guard_developer(request)
    if blocked:
        return blocked
    return page(request, "db_explorer.html", active_tab="settings", rows=None, error=None, sql="")


@router.post("/dev/db-explorer")
def db_explorer_run(
    request: Request,
    sql: str = Form(""),
    csrf: str = Form(""),
    confirm_write: str = Form(""),
):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request, csrf)
    if denied:
        return denied
    blocked = _guard_developer(request)
    if blocked:
        return blocked
    stripped = sql.strip().rstrip(";")
    upper = stripped.upper()
    blocked_words = ("DROP ", "ALTER ", "ATTACH ", "CREATE ", "DETACH ")
    if any(word in upper for word in blocked_words):
        return page(
            request,
            "db_explorer.html",
            active_tab="settings",
            rows=None,
            error="DROP/ALTER/ATTACH/CREATE are blocked.",
            sql=sql,
        )
    is_read = upper.startswith("SELECT") or upper.startswith("PRAGMA")
    if upper.startswith("WITH") and not re.search(r"\b(INSERT|UPDATE|DELETE|REPLACE)\b", upper):
        is_read = True
    if not is_read and confirm_write != "1":
        return page(
            request,
            "db_explorer.html",
            active_tab="settings",
            rows=None,
            error="Writes need the Confirm write box checked. Expected a read, or confirm=1.",
            sql=sql,
        )
    try:
        with db() as conn:
            cur = conn.execute(stripped)
            if is_read:
                fetched = [dict(row) for row in cur.fetchall()]
                return page(
                    request,
                    "db_explorer.html",
                    active_tab="settings",
                    rows=fetched[:200],
                    error=None,
                    sql=sql,
                )
            return page(
                request,
                "db_explorer.html",
                active_tab="settings",
                rows=[{"changes": cur.rowcount}],
                error=None,
                sql=sql,
            )
    except sqlite3.Error as err:
        return page(
            request,
            "db_explorer.html",
            active_tab="settings",
            rows=None,
            error=str(err),
            sql=sql,
        )


@router.get("/dev/notif-diagnostic")
def notif_diagnostic(request: Request):
    blocked = _guard_developer(request)
    if blocked:
        return blocked
    return page(request, "notif_diagnostic.html", active_tab="settings", outbox=store.list_outbox())


@router.get("/dev/diagnostics")
def diagnostics(request: Request):
    blocked = _guard_developer(request)
    if blocked:
        return blocked
    salesman = catalog.mock_report("salesman")
    number4 = catalog.mock_report("number_4")
    return page(
        request,
        "diagnostics.html",
        active_tab="settings",
        salesman_tabs=list((salesman["data"]["tabs"] or {}).keys()),
        number4_tabs=list((number4["data"]["tabs"] or {}).keys()),
        doorway_on=doorway.configured(),
        blocked="P4.I8 salesman vs SalesGroup is BLOCKED. Testers stay admin until Menny maps live rows.",
    )


@router.post("/api/dev/reporting/{report_id}/run")
async def reporting_api_run(request: Request, report_id: str):
    denied = need_login(request)
    if denied:
        return denied
    denied = require_csrf(request)
    if denied:
        return denied
    user = session_user(request)
    if not is_privileged(user):
        return JSONResponse({"error": "Developer only"}, status_code=403)
    if not config.reporting_api_key():
        return JSONResponse(
            {
                "error": "REPORTING_API_KEY is not set. This preview uses catalog mock JSON instead of the office doorway.",
                "mock": True,
                "report_id": report_id,
            },
            status_code=501,
        )
    raw = await request.body()
    if not raw:
        body = {}
    else:
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return JSONResponse(
                {"error": "Body must be a JSON object. Got invalid JSON."},
                status_code=400,
            )
    if not isinstance(body, dict):
        return JSONResponse({"error": "Body must be a JSON object."}, status_code=400)
    sp_params = {key: value for key, value in request.query_params.items() if value not in (None, "")}
    sp_params.update({key: value for key, value in body.items() if value not in (None, "")})
    try:
        result = doorway.run_report(report_id, sp_params)
    except doorway.DoorwayError as err:
        return JSONResponse({"error": str(err), "report_id": report_id}, status_code=502)
    return {
        "report_id": result.report_id,
        "row_count": len(result.rows),
        "rows": result.rows,
        "body": result.body,
    }
