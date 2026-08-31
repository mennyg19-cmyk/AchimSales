"""Developer tools: database explorer (precious + cache) and notification diagnostic."""

from __future__ import annotations

import sqlite3
from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request

from web.auth.decorators import require_login
from web.auth.principal import ROLE_DEVELOPER
from web.auth.session import current_principal
from web.dashboard.notifications import diagnose_overdue, generate_overdue_notifications
from web.data.repositories.users import UserRepository

devtools_bp = Blueprint("devtools", __name__)


def _require_developer():
    p = current_principal()
    if p is None or p.role != ROLE_DEVELOPER:
        return jsonify({"error": "Forbidden"}), 403
    return None


def _conn(which: str):
    db = current_app.config["DB"]
    if which == "cache":
        return db.cache()
    return db.precious()


def _list_tables(conn) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def _resolve_table(conn, name: str) -> str | None:
    return name if name and name in _list_tables(conn) else None


def _table_columns(conn, table: str) -> list[dict]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [
        {"name": r["name"], "type": r["type"], "notnull": bool(r["notnull"]),
         "default": r["dflt_value"], "pk": int(r["pk"] or 0)}
        for r in rows
    ]


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _pk_columns(cols: list[dict]) -> list[str]:
    return [c["name"] for c in sorted((c for c in cols if c["pk"] > 0), key=lambda c: c["pk"])]


def _primary_key(cols: list[dict]) -> str | None:
    pks = _pk_columns(cols)
    return pks[0] if len(pks) == 1 else None


def _has_rowid(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,),
    ).fetchone()
    sql = (row["sql"] or "") if row else ""
    return "WITHOUT ROWID" not in sql.upper()


def _row_locator(conn, table: str, body: dict) -> tuple[str, list[Any]] | None:
    """WHERE clause that pinpoints one row. Prefers SQLite rowid, then PK."""
    oid = body.get("oid")
    if oid not in (None, "") and _has_rowid(conn, table):
        return "rowid = ?", [oid]
    cols = _table_columns(conn, table)
    pks = _pk_columns(cols)
    pk_vals = body.get("pk")
    if pks and isinstance(pk_vals, dict) and all(k in pk_vals for k in pks):
        sql = " AND ".join(f"{_ident(k)}=?" for k in pks)
        return sql, [pk_vals[k] for k in pks]
    if len(pks) == 1 and pk_vals not in (None, "") and not isinstance(pk_vals, dict):
        return f"{_ident(pks[0])}=?", [pk_vals]
    return None


def _prepared_values(cols: list[dict], raw: Any, *, skip_empty: bool) -> tuple[list[str], list[Any]] | str:
    """Column list + bound values, or an error string."""
    if not isinstance(raw, dict):
        return "values must be an object"
    names = {c["name"] for c in cols}
    types = {c["name"]: c["type"] for c in cols}
    unknown = [k for k in raw if k not in names]
    if unknown:
        return f"Unknown column: {unknown[0]}"
    out_cols: list[str] = []
    out_vals: list[Any] = []
    for k, v in raw.items():
        if skip_empty and (v is None or v == ""):
            continue
        out_cols.append(k)
        out_vals.append(_coerce(v, types[k]))
    return out_cols, out_vals


def _resolve_column(cols: list[dict], column: str) -> str | None:
    names = [c["name"] for c in cols]
    return column if column and column in names else None


def _coerce(raw: Any, col_type: str) -> Any:
    if raw is None or raw == "":
        return None
    t = (col_type or "").upper()
    if "INT" in t:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return raw
    if "REAL" in t or "FLOAT" in t or "DOUBLE" in t or "NUMERIC" in t:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return raw
    return raw


@devtools_bp.get("/dev/db-explorer")
@require_login
def db_explorer_page():
    blocked = _require_developer()
    if blocked:
        return blocked
    db = current_app.config["DB"]
    return render_template(
        "db_explorer.html", active_tab="settings",
        precious_path=str(db.precious_path), cache_path=str(db.cache_path),
    )


@devtools_bp.get("/api/dev/db/tables")
@require_login
def api_list_tables():
    blocked = _require_developer()
    if blocked:
        return blocked
    which = (request.args.get("db") or "precious").strip()
    if which not in ("precious", "cache"):
        return jsonify({"error": "db must be precious or cache"}), 400
    with _conn(which) as conn:
        tables = []
        for name in _list_tables(conn):
            try:
                n = conn.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"]
            except sqlite3.Error:
                n = None
            tables.append({"name": name, "row_count": n})
        return jsonify({"db": which, "tables": tables})


@devtools_bp.get("/api/dev/db/table/<table>")
@require_login
def api_get_rows(table: str):
    blocked = _require_developer()
    if blocked:
        return blocked
    which = (request.args.get("db") or "precious").strip()
    if which not in ("precious", "cache"):
        return jsonify({"error": "db must be precious or cache"}), 400
    with _conn(which) as conn:
        table = _resolve_table(conn, table)
        if not table:
            return jsonify({"error": "Unknown table"}), 404
        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        try:
            per_page = max(1, min(int(request.args.get("per_page", 50)), 200))
        except ValueError:
            per_page = 50
        cols = _table_columns(conn, table)
        col_names = [c["name"] for c in cols]
        pk = _primary_key(cols)
        search = (request.args.get("q") or "").strip()
        where_sql = ""
        params: list[Any] = []
        if search:
            where_sql = "WHERE " + " OR ".join(
                f"CAST({_ident(c)} AS TEXT) LIKE ?" for c in col_names
            )
            params.extend([f"%{search}%"] * len(col_names))
        sort_col = _resolve_column(cols, request.args.get("sort", "") or "") or pk
        order_sql = f"ORDER BY {_ident(sort_col)}" if sort_col else ""
        offset = (page - 1) * per_page
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM {_ident(table)} {where_sql}", params,
        ).fetchone()["n"]
        has_oid = _has_rowid(conn, table)
        select = f"SELECT rowid AS _oid, * FROM {_ident(table)}" if has_oid else f"SELECT * FROM {_ident(table)}"
        rows = conn.execute(
            f"{select} {where_sql} {order_sql} LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()
        return jsonify({
            "table": table, "columns": cols, "primary_key": pk,
            "primary_keys": _pk_columns(cols), "has_rowid": has_oid,
            "rows": [dict(r) for r in rows], "total": total, "page": page,
            "per_page": per_page,
        })


@devtools_bp.post("/api/dev/db/table/<table>/cell")
@require_login
def api_update_cell(table: str):
    blocked = _require_developer()
    if blocked:
        return blocked
    body = request.get_json(silent=True) or {}
    which = (body.get("db") or "precious").strip()
    if which not in ("precious", "cache"):
        return jsonify({"error": "db must be precious or cache"}), 400
    with _conn(which) as conn:
        table = _resolve_table(conn, table)
        if not table:
            return jsonify({"error": "Unknown table"}), 404
        cols = _table_columns(conn, table)
        pk = _primary_key(cols)
        col = _resolve_column(cols, body.get("column") or "")
        if not pk or not col:
            return jsonify({"error": "Need a single-column primary key and a known column"}), 400
        col_type = next(c["type"] for c in cols if c["name"] == col)
        value = _coerce(body.get("value"), col_type)
        pk_value = body.get("pk")
        try:
            cur = conn.execute(
                f"UPDATE {_ident(table)} SET {_ident(col)}=? WHERE {_ident(pk)}=?",
                (value, pk_value),
            )
        except sqlite3.Error as exc:
            return jsonify({"error": str(exc)}), 400
        if cur.rowcount != 1:
            return jsonify({"error": "Row not found"}), 404
        return jsonify({"ok": True})


@devtools_bp.delete("/api/dev/db/table/<table>/row")
@require_login
def api_delete_row(table: str):
    blocked = _require_developer()
    if blocked:
        return blocked
    body = request.get_json(silent=True) or {}
    which = (body.get("db") or request.args.get("db") or "precious").strip()
    if which not in ("precious", "cache"):
        return jsonify({"error": "db must be precious or cache"}), 400
    with _conn(which) as conn:
        table = _resolve_table(conn, table)
        if not table:
            return jsonify({"error": "Unknown table"}), 404
        loc = _row_locator(conn, table, body)
        if loc is None:
            return jsonify({"error": "Need oid or primary key to delete a row"}), 400
        where_sql, where_vals = loc
        try:
            cur = conn.execute(f"DELETE FROM {_ident(table)} WHERE {where_sql}", where_vals)
        except sqlite3.Error as exc:
            return jsonify({"error": str(exc)}), 400
        if cur.rowcount != 1:
            return jsonify({"error": "Row not found"}), 404
        return jsonify({"ok": True})


@devtools_bp.post("/api/dev/db/table/<table>/row")
@require_login
def api_insert_row(table: str):
    blocked = _require_developer()
    if blocked:
        return blocked
    body = request.get_json(silent=True) or {}
    which = (body.get("db") or "precious").strip()
    if which not in ("precious", "cache"):
        return jsonify({"error": "db must be precious or cache"}), 400
    with _conn(which) as conn:
        table = _resolve_table(conn, table)
        if not table:
            return jsonify({"error": "Unknown table"}), 404
        cols = _table_columns(conn, table)
        prepared = _prepared_values(cols, body.get("values"), skip_empty=True)
        if isinstance(prepared, str):
            return jsonify({"error": prepared}), 400
        col_names, values = prepared
        if not col_names:
            return jsonify({"error": "Provide at least one column"}), 400
        placeholders = ",".join("?" * len(col_names))
        col_sql = ",".join(_ident(c) for c in col_names)
        try:
            cur = conn.execute(
                f"INSERT INTO {_ident(table)} ({col_sql}) VALUES ({placeholders})",
                values,
            )
        except sqlite3.Error as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "oid": cur.lastrowid})


@devtools_bp.put("/api/dev/db/table/<table>/row")
@require_login
def api_update_row(table: str):
    blocked = _require_developer()
    if blocked:
        return blocked
    body = request.get_json(silent=True) or {}
    which = (body.get("db") or "precious").strip()
    if which not in ("precious", "cache"):
        return jsonify({"error": "db must be precious or cache"}), 400
    with _conn(which) as conn:
        table = _resolve_table(conn, table)
        if not table:
            return jsonify({"error": "Unknown table"}), 404
        loc = _row_locator(conn, table, body)
        if loc is None:
            return jsonify({"error": "Need oid or primary key to save a row"}), 400
        where_sql, where_vals = loc
        prepared = _prepared_values(_table_columns(conn, table), body.get("values"), skip_empty=False)
        if isinstance(prepared, str):
            return jsonify({"error": prepared}), 400
        col_names, values = prepared
        if not col_names:
            return jsonify({"error": "Provide at least one column"}), 400
        set_sql = ", ".join(f"{_ident(c)}=?" for c in col_names)
        try:
            cur = conn.execute(
                f"UPDATE {_ident(table)} SET {set_sql} WHERE {where_sql}",
                values + where_vals,
            )
        except sqlite3.Error as exc:
            return jsonify({"error": str(exc)}), 400
        if cur.rowcount != 1:
            return jsonify({"error": "Row not found"}), 404
        return jsonify({"ok": True})


@devtools_bp.get("/dev/notif-diagnostic")
@require_login
def notif_diagnostic_page():
    blocked = _require_developer()
    if blocked:
        return blocked
    users = UserRepository(current_app.config["DB"]).list_all()
    return render_template("notif_diagnostic.html", active_tab="settings", users=users)


@devtools_bp.get("/api/dev/notif-diagnostic/<path:email>")
@require_login
def api_notif_diagnostic(email: str):
    blocked = _require_developer()
    if blocked:
        return blocked
    user = UserRepository(current_app.config["DB"]).get_by_email(email.lower().strip())
    if user is None:
        return jsonify({"error": "User not found"}), 404
    data = diagnose_overdue(current_app.config["DB"], user)
    data["user"] = {
        "email": user.email, "role": user.role, "display_name": user.display_name,
        "is_active": user.is_active, "dashboard_enabled": user.dashboard_enabled,
    }
    return jsonify(data)


@devtools_bp.post("/api/dev/notif-diagnostic/<path:email>/run")
@require_login
def api_notif_diagnostic_run(email: str):
    blocked = _require_developer()
    if blocked:
        return blocked
    user = UserRepository(current_app.config["DB"]).get_by_email(email.lower().strip())
    if user is None:
        return jsonify({"error": "User not found"}), 404
    created = generate_overdue_notifications(current_app.config["DB"])
    data = diagnose_overdue(current_app.config["DB"], user)
    data["generated"] = created
    return jsonify(data)
