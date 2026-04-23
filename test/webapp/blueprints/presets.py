"""Saved reports (a.k.a. "presets") API.

A preset is a named shortcut to run one specific report with one specific
set of filter params. It's per-user (keyed by email) and shows up on the
home page under the "My Presets" tab.

All endpoints are JSON. Mounted at ``/api/saved-reports`` by app.py.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from flask import Blueprint, abort, jsonify, request

from test.config.reports import REPORTS, get_report
from test.webapp.auth import current_user, require_login
from test.webapp.db import connect

presets_bp = Blueprint("presets", __name__, url_prefix="/api/saved-reports")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_email() -> str:
    u = current_user()
    if not u:
        abort(401)
    return (u.get("email") or "").lower()


def _row_to_dict(row: sqlite3.Row) -> dict:
    try:
        params = json.loads(row["params_json"] or "{}")
    except json.JSONDecodeError:
        params = {}
    return {
        "id":          row["id"],
        "name":        row["name"],
        "report_key":  row["report_key"],
        "report_name": row["report_name"],
        "params":      params,
        "created_utc": row["created_utc"],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@presets_bp.get("")
@require_login
def list_presets():
    email = _user_email()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, report_key, report_name, params_json, created_utc
              FROM saved_reports
             WHERE user_email = ?
             ORDER BY created_utc DESC
            """,
            (email,),
        ).fetchall()
    return jsonify([_row_to_dict(r) for r in rows])


@presets_bp.post("")
@require_login
def create_preset():
    email = _user_email()
    body = request.get_json(silent=True) or {}

    name = (body.get("name") or "").strip()
    report_key = (body.get("report_key") or "").strip()
    params = body.get("params") if isinstance(body.get("params"), dict) else {}

    if not name:
        return jsonify({"error": "Name is required."}), 400
    if len(name) > 80:
        return jsonify({"error": "Name must be 80 characters or less."}), 400
    if report_key not in REPORTS:
        return jsonify({"error": f"Unknown report '{report_key}'."}), 400

    # Strip empty entries so the saved blob is small and predictable.
    clean_params = {k: v for k, v in params.items() if v not in (None, "", [])}

    report = get_report(report_key)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        with connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO saved_reports
                    (user_email, name, report_key, report_name, params_json, created_utc)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (email, name, report_key, report.name, json.dumps(clean_params), now),
            )
            new_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return jsonify({"error": "You already have a preset with that name."}), 409

    return jsonify({
        "id":          new_id,
        "name":        name,
        "report_key":  report_key,
        "report_name": report.name,
        "params":      clean_params,
        "created_utc": now,
    }), 201


@presets_bp.delete("/<int:preset_id>")
@require_login
def delete_preset(preset_id: int):
    email = _user_email()
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM saved_reports WHERE id = ? AND user_email = ?",
            (preset_id, email),
        )
        if cur.rowcount == 0:
            return jsonify({"error": "Preset not found."}), 404
    return jsonify({"ok": True})
