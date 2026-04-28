"""
Developer-only database explorer.

Exposes ``/dev/db-explorer`` (page) plus a small JSON API that lists
tables, returns paginated rows, and lets a developer edit a single cell
or delete a single row.

Why this exists
---------------
We were running into "I deleted a user but it came back on restart"
problems and there was no quick way to inspect the SQLite state from
the live site. Rather than SSH-ing into Kudu and running ``sqlite3``,
this gives a graphical browser that mirrors what tools like DBeaver
expose, scoped to the things a busy admin actually needs.

Safety boundaries
-----------------
* All routes require the developer role -- not even regular admins can
  reach this. That's intentional: bad UPDATEs here can corrupt user
  permissions, schedules, etc.
* The HTTP API never accepts arbitrary SQL. Table and column names are
  validated against a snapshot of the schema (``sqlite_master``) before
  being interpolated into a query, and parameter values always go
  through bound parameters.
* DDL is impossible from the API: no CREATE / DROP / ALTER / TRUNCATE
  endpoints exist. The worst a developer can do here is bulk-delete
  rows in one table at a time, one row at a time.
* Primary-key-required for UPDATE/DELETE: if a table has no primary
  key (or composite PK we can't infer), the API returns 400 instead of
  guessing.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from flask import Blueprint, jsonify, render_template, request

from webapp.db import DB_PATH, get_db
from webapp.helpers import get_current_user, require_login
from webapp.user_map import is_developer

log = logging.getLogger(__name__)

db_explorer_bp = Blueprint("db_explorer", __name__)


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def _require_developer():
    """Return None if the caller is a developer, otherwise a Flask response.

    Wrapping this in a small helper keeps every route honest without
    decorator gymnastics.
    """
    user = get_current_user()
    if not user or not is_developer(user):
        return jsonify({"error": "forbidden"}), 403
    return None


def _list_table_names() -> list[str]:
    """All user tables, sorted. Skips sqlite internals."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT name FROM sqlite_master
               WHERE type = 'table'
                 AND name NOT LIKE 'sqlite_%'
               ORDER BY name"""
        ).fetchall()
        return [r["name"] for r in rows]
    finally:
        conn.close()


def _resolve_table(name: str) -> str | None:
    """Return *name* if it exists in the DB, else None.

    This is the choke point that lets us safely interpolate the table
    name into queries. Always run user input through this before using
    it in an f-string.
    """
    if not name:
        return None
    if name in _list_table_names():
        return name
    return None


def _table_columns(table: str) -> list[dict]:
    """Column metadata for *table*: name, type, notnull, default, pk position."""
    conn = get_db()
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [
            {
                "name": r["name"],
                "type": r["type"],
                "notnull": bool(r["notnull"]),
                "default": r["dflt_value"],
                "pk": int(r["pk"] or 0),
            }
            for r in rows
        ]
    finally:
        conn.close()


def _primary_key(table: str) -> str | None:
    """Return the single-column primary key name, or None.

    Composite PKs return None on purpose: editing/deleting by composite
    key is a corner case I'd rather refuse than half-support.
    """
    cols = _table_columns(table)
    pks = [c for c in cols if c["pk"] == 1]
    other_pks = [c for c in cols if c["pk"] > 1]
    if other_pks:
        return None
    if len(pks) == 1:
        return pks[0]["name"]
    return None


def _resolve_column(table: str, column: str) -> str | None:
    """Return *column* if it belongs to *table*, else None."""
    if not column:
        return None
    names = [c["name"] for c in _table_columns(table)]
    return column if column in names else None


def _coerce_value(raw: Any, col_type: str) -> Any:
    """Coerce a JSON-string value to the target SQLite column type.

    SQLite is loose about types but we still try to be helpful: empty
    strings become NULL, INTEGER columns get parsed, REAL columns get
    floated. Anything else passes through as-is.
    """
    if raw is None:
        return None
    if isinstance(raw, str) and raw == "":
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@db_explorer_bp.route("/dev/db-explorer")
@require_login
def db_explorer_page():
    user = get_current_user()
    if not is_developer(user):
        return ("Forbidden", 403)
    return render_template("db_explorer.html",
                           tables=_list_table_names(),
                           db_path=DB_PATH)


@db_explorer_bp.route("/api/dev/db/tables")
@require_login
def api_list_tables():
    guard = _require_developer()
    if guard is not None:
        return guard

    conn = get_db()
    try:
        result = []
        for name in _list_table_names():
            try:
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {name}"
                ).fetchone()[0]
            except sqlite3.Error:
                count = None
            result.append({"name": name, "row_count": count})
        return jsonify({"tables": result})
    finally:
        conn.close()


@db_explorer_bp.route("/api/dev/db/table/<table>")
@require_login
def api_get_rows(table):
    guard = _require_developer()
    if guard is not None:
        return guard

    table = _resolve_table(table)
    if not table:
        return jsonify({"error": "Unknown table"}), 404

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    try:
        per_page = int(request.args.get("per_page", 50))
    except ValueError:
        per_page = 50
    per_page = max(1, min(per_page, 500))
    search = (request.args.get("q") or "").strip()
    sort_col = _resolve_column(table, request.args.get("sort", "")) or ""
    sort_dir = "DESC" if (request.args.get("dir", "asc").lower() == "desc") else "ASC"

    cols = _table_columns(table)
    col_names = [c["name"] for c in cols]
    pk = _primary_key(table)

    where_sql = ""
    params: list[Any] = []
    if search:
        # Free-text search: cast every column to TEXT and LIKE-compare.
        # SQLite handles this efficiently enough for our table sizes.
        clauses = [f"CAST({c} AS TEXT) LIKE ?" for c in col_names]
        where_sql = "WHERE " + " OR ".join(clauses)
        params.extend([f"%{search}%"] * len(col_names))

    order_sql = f"ORDER BY {sort_col} {sort_dir}" if sort_col else (
        f"ORDER BY {pk}" if pk else ""
    )

    offset = (page - 1) * per_page
    conn = get_db()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM {table} {where_sql}", params
        ).fetchone()[0]

        sql = f"SELECT * FROM {table} {where_sql} {order_sql} LIMIT ? OFFSET ?"
        rows = conn.execute(sql, params + [per_page, offset]).fetchall()

        return jsonify({
            "table": table,
            "columns": cols,
            "primary_key": pk,
            "rows": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "sort": sort_col or pk,
            "dir": sort_dir.lower(),
        })
    finally:
        conn.close()


@db_explorer_bp.route("/api/dev/db/table/<table>/cell", methods=["POST"])
@require_login
def api_update_cell(table):
    guard = _require_developer()
    if guard is not None:
        return guard

    table = _resolve_table(table)
    if not table:
        return jsonify({"error": "Unknown table"}), 404

    pk = _primary_key(table)
    if not pk:
        return jsonify({"error": "Table has no single-column primary key; cannot edit safely."}), 400

    data = request.get_json() or {}
    column = _resolve_column(table, data.get("column", ""))
    if not column:
        return jsonify({"error": "Unknown column"}), 400
    if column == pk:
        return jsonify({"error": "Refusing to edit the primary key column."}), 400

    pk_value = data.get("pk_value")
    if pk_value in (None, ""):
        return jsonify({"error": "Missing pk_value"}), 400

    cols = _table_columns(table)
    col_type = next((c["type"] for c in cols if c["name"] == column), "")
    new_value = _coerce_value(data.get("value"), col_type)

    conn = get_db()
    try:
        cur = conn.execute(
            f"UPDATE {table} SET {column} = ? WHERE {pk} = ?",
            (new_value, pk_value),
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Row not found"}), 404
        log.info("db_explorer: UPDATE %s SET %s WHERE %s=%s",
                 table, column, pk, pk_value)
        return jsonify({"success": True, "value": new_value})
    except sqlite3.Error as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@db_explorer_bp.route("/api/dev/db/table/<table>/row", methods=["DELETE"])
@require_login
def api_delete_row(table):
    guard = _require_developer()
    if guard is not None:
        return guard

    table = _resolve_table(table)
    if not table:
        return jsonify({"error": "Unknown table"}), 404

    pk = _primary_key(table)
    if not pk:
        return jsonify({"error": "Table has no single-column primary key; cannot delete safely."}), 400

    pk_value = request.args.get("pk_value")
    if pk_value in (None, ""):
        return jsonify({"error": "Missing pk_value"}), 400

    conn = get_db()
    try:
        cur = conn.execute(
            f"DELETE FROM {table} WHERE {pk} = ?", (pk_value,)
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Row not found"}), 404
        log.info("db_explorer: DELETE FROM %s WHERE %s=%s",
                 table, pk, pk_value)
        return jsonify({"success": True})
    except sqlite3.Error as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@db_explorer_bp.route("/api/dev/db/table/<table>/row", methods=["POST"])
@require_login
def api_insert_row(table):
    """Insert a brand-new row. Body: {column: value, ...}.

    Lets developers add quick fixture rows without leaving the browser.
    Same safety rules as everything else here: column names validated,
    values bound as parameters.
    """
    guard = _require_developer()
    if guard is not None:
        return guard

    table = _resolve_table(table)
    if not table:
        return jsonify({"error": "Unknown table"}), 404

    data = request.get_json() or {}
    if not isinstance(data, dict) or not data:
        return jsonify({"error": "Provide at least one column=value pair"}), 400

    cols = _table_columns(table)
    col_types = {c["name"]: c["type"] for c in cols}

    valid_cols = []
    valid_vals = []
    for k, v in data.items():
        col = _resolve_column(table, k)
        if not col:
            return jsonify({"error": f"Unknown column: {k}"}), 400
        valid_cols.append(col)
        valid_vals.append(_coerce_value(v, col_types.get(col, "")))

    placeholders = ",".join(["?"] * len(valid_cols))
    col_list = ",".join(valid_cols)
    conn = get_db()
    try:
        cur = conn.execute(
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
            valid_vals,
        )
        conn.commit()
        log.info("db_explorer: INSERT INTO %s (%s) rowid=%s",
                 table, col_list, cur.lastrowid)
        return jsonify({"success": True, "rowid": cur.lastrowid})
    except sqlite3.Error as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()
