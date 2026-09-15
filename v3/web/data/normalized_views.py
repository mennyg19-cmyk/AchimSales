"""Old JSON views/schedules → normalized tables, and back to dicts.

Step 1 only: projector + assemble. Live read path still uses the JSON blobs.
"""

from __future__ import annotations

import json
import re
import sqlite3

from web.data.connection import Database
from web.delivery.email import split_recipients
from web.scheduling.delivery_keys import MASTER_DELIVERY_PARAM_KEYS, without_delivery_keys

_SLUG_MAX = 40
_ID_MAX = 120
_SCALAR_KEYS = ("period", "start_date", "end_date", "year", "mode")
_LIST_KEYS = ("salesman", "status", "customers")


def slug(text: str, max_len: int = _SLUG_MAX) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s or "x")[:max_len]


def suggest_handle(display_name: str, email: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z]+", display_name or "") if p]
    if len(parts) >= 2:
        base = (parts[0][0] + parts[-1]).lower()
    elif len(parts) == 1:
        base = parts[0].lower()
    else:
        base = re.sub(r"[^a-z0-9]", "", (email or "").split("@")[0].lower())
    if not base or not re.match(r"^[a-z]", base):
        base = "u" + (base or "ser")
    return base[:_SLUG_MAX]


def allocate_handle(conn: sqlite3.Connection, display_name: str, email: str,
                    taken: set[str]) -> str:
    base = suggest_handle(display_name, email)
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def assign_handles(conn: sqlite3.Connection) -> dict[int, str]:
    """Fill users.handle. Keep existing values. Returns {user_id: handle}."""
    rows = conn.execute(
        "SELECT id, email, display_name, handle FROM users ORDER BY id"
    ).fetchall()
    taken = {r["handle"] for r in rows if r["handle"]}
    out: dict[int, str] = {}
    for r in rows:
        if r["handle"]:
            out[r["id"]] = r["handle"]
            continue
        handle = allocate_handle(conn, r["display_name"] or "", r["email"] or "", taken)
        taken.add(handle)
        conn.execute("UPDATE users SET handle=? WHERE id=?", (handle, r["id"]))
        out[r["id"]] = handle
    return out


def _clip(value: str) -> str:
    return value[:_ID_MAX]


def default_view_id(report_key: str) -> str:
    return _clip(f"df-{slug(report_key)}")


def company_view_id(report_key: str, name: str) -> str:
    return _clip(f"co-{slug(report_key)}-{slug(name)}")


def personal_view_id(handle: str, report_key: str, name: str) -> str:
    return _clip(f"pe-{handle}-{slug(report_key)}-{slug(name)}")


def tab_id(view_id: str, tab_key: str) -> str:
    return _clip(f"{view_id}__{slug(tab_key, 60)}")


def _loads(raw: str | None) -> dict:
    try:
        obj = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _as_str_list(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(x).strip() for x in raw if str(x).strip()]
    s = str(raw).strip()
    if not s:
        return []
    if "," in s:
        return [p.strip() for p in s.split(",") if p.strip()]
    return [p for p in s.split() if p]


def _as_bool(raw) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def canonicalize_params(params: dict | None) -> dict:
    src = without_delivery_keys(params or {}, MASTER_DELIVERY_PARAM_KEYS)
    out: dict = {}
    start = str(src.get("start_date") or src.get("from") or "").strip()
    end = str(src.get("end_date") or src.get("to") or "").strip()
    for key in _SCALAR_KEYS:
        if key == "start_date":
            val = start
        elif key == "end_date":
            val = end
        else:
            val = str(src.get(key) or "").strip()
        if val:
            out[key] = val
    for key in _LIST_KEYS:
        items = _as_str_list(src.get(key))
        if items:
            out[key] = items
    return out


def canonicalize_layout(layout: dict | None) -> dict:
    src = layout if isinstance(layout, dict) else {}
    out: dict = {}
    active = src.get("active")
    if active:
        out["active"] = str(active)
    order = src.get("order")
    if isinstance(order, list) and order:
        out["order"] = [str(x) for x in order if str(x).strip()]
    clones = src.get("clones")
    if isinstance(clones, list) and clones:
        clean = []
        for c in clones:
            if not isinstance(c, dict):
                continue
            key, base = str(c.get("key") or "").strip(), str(c.get("baseKey") or "").strip()
            if key and base:
                item = {"key": key, "baseKey": base}
                if c.get("name"):
                    item["name"] = str(c["name"])
                clean.append(item)
        if clean:
            out["clones"] = clean
    views_in = src.get("views") if isinstance(src.get("views"), dict) else {}
    views_out: dict = {}
    for tab_key, raw in views_in.items():
        views_out[str(tab_key)] = _canonicalize_tab(raw if isinstance(raw, dict) else {})
    if views_out:
        out["views"] = views_out
    return out


def _canonicalize_tab(raw: dict) -> dict:
    tab: dict = {"group": [str(x) for x in (raw.get("group") or []) if str(x).strip()]
                 if isinstance(raw.get("group"), list) else []}
    hidden = raw.get("hidden")
    if isinstance(hidden, list) and any(str(x).strip() for x in hidden):
        tab["hidden"] = [str(x) for x in hidden if str(x).strip()]
    frozen = raw.get("frozen")
    if isinstance(frozen, list) and any(str(x).strip() for x in frozen):
        tab["frozen"] = [str(x) for x in frozen if str(x).strip()]
    order = raw.get("order")
    if isinstance(order, list) and order:
        tab["order"] = [str(x) for x in order if str(x).strip()]
    sorters = raw.get("sorters")
    if isinstance(sorters, list) and sorters:
        clean = []
        for s in sorters:
            if not isinstance(s, dict):
                continue
            col = str(s.get("column") or s.get("field") or "").strip()
            if not col:
                continue
            d = str(s.get("dir") or "asc").lower()
            clean.append({"column": col, "dir": "desc" if d == "desc" else "asc"})
        if clean:
            tab["sorters"] = clean
    filters = raw.get("columnFilters")
    if not isinstance(filters, dict) and isinstance(raw.get("headerFilters"), list):
        filters = {}
        for hf in raw["headerFilters"]:
            if isinstance(hf, dict) and hf.get("field") and str(hf.get("value") or "").strip():
                filters[str(hf["field"])] = {
                    "op": "contains", "v": str(hf["value"]), "v2": "",
                }
    if isinstance(filters, dict) and filters:
        cleaned = {}
        for field, spec in filters.items():
            if not isinstance(spec, dict):
                continue
            cleaned[str(field)] = {
                "op": str(spec.get("op") or "contains"),
                "v": "" if spec.get("v") is None else str(spec.get("v")),
                "v2": "" if spec.get("v2") is None else str(spec.get("v2")),
            }
        if cleaned:
            tab["columnFilters"] = cleaned
    widths = raw.get("widths")
    if isinstance(widths, dict) and widths:
        tab["widths"] = {str(k): v for k, v in widths.items()}
    return tab


def layouts_match(a: dict | None, b: dict | None) -> bool:
    return canonicalize_layout(a) == canonicalize_layout(b)


def params_match(a: dict | None, b: dict | None, *, ignore_window: bool = False) -> bool:
    ca, cb = canonicalize_params(a), canonicalize_params(b)
    if ignore_window:
        for key in ("period", "start_date", "end_date"):
            ca.pop(key, None)
            cb.pop(key, None)
    return ca == cb


def _replace_view_children(conn: sqlite3.Connection, view_id: str) -> None:
    conn.execute("DELETE FROM layout_tabs WHERE view_id=?", (view_id,))
    conn.execute("DELETE FROM view_salesmen WHERE view_id=?", (view_id,))
    conn.execute("DELETE FROM view_statuses WHERE view_id=?", (view_id,))
    conn.execute("DELETE FROM view_customers WHERE view_id=?", (view_id,))


def _upsert_view(conn: sqlite3.Connection, *, view_id: str, kind: str, report_key: str,
                 name: str, owner_handle: str | None, params: dict, layout: dict,
                 updated_by_handle: str | None, legacy_source: str, legacy_id: int) -> str:
    existing = conn.execute(
        "SELECT id FROM views WHERE legacy_source=? AND legacy_id=?",
        (legacy_source, legacy_id),
    ).fetchone()
    if existing:
        view_id = existing["id"]
        conn.execute(
            "UPDATE views SET kind=?, report_key=?, name=?, owner_handle=?,"
            " period=?, start_date=?, end_date=?, year=?, mode=?, active_tab_key=?,"
            " updated_by_handle=? WHERE id=?",
            (kind, report_key, name, owner_handle,
             params.get("period"), params.get("start_date"), params.get("end_date"),
             params.get("year"), params.get("mode"),
             str(layout.get("active") or "") or None, updated_by_handle, view_id),
        )
    else:
        taken = conn.execute("SELECT 1 FROM views WHERE id=?", (view_id,)).fetchone()
        if taken:
            view_id = _clip(f"{view_id}-{legacy_id}")
        conn.execute(
            "INSERT INTO views(id, kind, report_key, name, owner_handle, period,"
            " start_date, end_date, year, mode, active_tab_key, updated_by_handle,"
            " legacy_source, legacy_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (view_id, kind, report_key, name, owner_handle,
             params.get("period"), params.get("start_date"), params.get("end_date"),
             params.get("year"), params.get("mode"),
             str(layout.get("active") or "") or None, updated_by_handle,
             legacy_source, legacy_id),
        )
    _replace_view_children(conn, view_id)
    _insert_list_filters(conn, view_id, params)
    _insert_layout(conn, view_id, layout)
    return view_id


def _insert_list_filters(conn: sqlite3.Connection, view_id: str, params: dict) -> None:
    for salesman in params.get("salesman") or []:
        conn.execute(
            "INSERT INTO view_salesmen(id, view_id, salesman) VALUES (?,?,?)",
            (f"{view_id}__sm-{slug(salesman)}", view_id, salesman),
        )
    for status in params.get("status") or []:
        conn.execute(
            "INSERT INTO view_statuses(id, view_id, status) VALUES (?,?,?)",
            (f"{view_id}__st-{slug(status)}", view_id, status),
        )
    for account in params.get("customers") or []:
        conn.execute(
            "INSERT INTO view_customers(id, view_id, customer_account) VALUES (?,?,?)",
            (f"{view_id}__cu-{slug(account)}", view_id, account),
        )


def _insert_layout(conn: sqlite3.Connection, view_id: str, layout: dict) -> None:
    canon = canonicalize_layout(layout)
    order = list(canon.get("order") or [])
    views_map = canon.get("views") if isinstance(canon.get("views"), dict) else {}
    clone_by_key = {c["key"]: c for c in (canon.get("clones") or [])}
    keys: list[str] = []
    for k in order:
        if k not in keys:
            keys.append(k)
    for k in views_map:
        if k not in keys:
            keys.append(k)
    for k in clone_by_key:
        if k not in keys:
            keys.append(k)
    active = canon.get("active")
    if active and active not in keys:
        keys.append(active)
    order_pos = {k: i + 1 for i, k in enumerate(order)}
    used_tab_ids: set[str] = set()
    for key in keys:
        tid = tab_id(view_id, key)
        if tid in used_tab_ids:
            tid = _clip(f"{tid}-{len(used_tab_ids)}")
        used_tab_ids.add(tid)
        clone = clone_by_key.get(key)
        conn.execute(
            "INSERT INTO layout_tabs(id, view_id, tab_key, position, clone_of_tab_key,"
            " tab_name, has_view) VALUES (?,?,?,?,?,?,?)",
            (tid, view_id, key, order_pos.get(key),
             clone["baseKey"] if clone else None,
             clone.get("name") if clone else None,
             1 if key in views_map else 0),
        )
        if key in views_map:
            _insert_tab_settings(conn, tid, views_map[key])


def _insert_tab_settings(conn: sqlite3.Connection, tab_id_value: str, tab: dict) -> None:
    for i, col in enumerate(tab.get("group") or [], start=1):
        conn.execute(
            "INSERT INTO layout_tab_groups(id, tab_id, position, column_name)"
            " VALUES (?,?,?,?)",
            (f"{tab_id_value}__g{i}", tab_id_value, i, col),
        )
    for i, s in enumerate(tab.get("sorters") or [], start=1):
        conn.execute(
            "INSERT INTO layout_tab_sorters(id, tab_id, position, column_name, dir)"
            " VALUES (?,?,?,?,?)",
            (f"{tab_id_value}__s{i}", tab_id_value, i, s["column"], s["dir"]),
        )
    fields: dict[str, dict] = {}
    for i, field in enumerate(tab.get("order") or [], start=1):
        fields.setdefault(field, {})["position"] = i
    for field in tab.get("hidden") or []:
        fields.setdefault(field, {})["hidden"] = 1
    for field in tab.get("frozen") or []:
        fields.setdefault(field, {})["frozen"] = 1
    for field, width in (tab.get("widths") or {}).items():
        fields.setdefault(str(field), {})["width"] = width
    used = set()
    for field, spec in fields.items():
        cid = _clip(f"{tab_id_value}__{slug(field)}")
        if cid in used:
            cid = _clip(f"{cid}-{len(used)}")
        used.add(cid)
        conn.execute(
            "INSERT INTO layout_columns(id, tab_id, field, position, hidden, frozen, width)"
            " VALUES (?,?,?,?,?,?,?)",
            (cid, tab_id_value, field, spec.get("position"),
             1 if spec.get("hidden") else 0, 1 if spec.get("frozen") else 0,
             spec.get("width")),
        )
    for field, spec in (tab.get("columnFilters") or {}).items():
        conn.execute(
            "INSERT INTO layout_column_filters(id, tab_id, field, op, v, v2)"
            " VALUES (?,?,?,?,?,?)",
            (_clip(f"{tab_id_value}__f-{slug(field)}"), tab_id_value, field,
             spec.get("op") or "contains", spec.get("v"), spec.get("v2")),
        )


def assemble_params(conn: sqlite3.Connection, view_id: str) -> dict:
    row = conn.execute("SELECT * FROM views WHERE id=?", (view_id,)).fetchone()
    if row is None:
        return {}
    out: dict = {}
    for key in _SCALAR_KEYS:
        val = row[key]
        if val:
            out[key] = val
    salesmen = [r["salesman"] for r in conn.execute(
        "SELECT salesman FROM view_salesmen WHERE view_id=? ORDER BY rowid", (view_id,))]
    if salesmen:
        out["salesman"] = salesmen
    statuses = [r["status"] for r in conn.execute(
        "SELECT status FROM view_statuses WHERE view_id=? ORDER BY rowid", (view_id,))]
    if statuses:
        out["status"] = statuses
    customers = [r["customer_account"] for r in conn.execute(
        "SELECT customer_account FROM view_customers WHERE view_id=? ORDER BY rowid",
        (view_id,))]
    if customers:
        out["customers"] = customers
    return out


def assemble_layout(conn: sqlite3.Connection, view_id: str) -> dict:
    row = conn.execute("SELECT active_tab_key FROM views WHERE id=?", (view_id,)).fetchone()
    if row is None:
        return {}
    tabs = conn.execute(
        "SELECT * FROM layout_tabs WHERE view_id=? ORDER BY"
        " CASE WHEN position IS NULL THEN 1 ELSE 0 END, position, tab_key",
        (view_id,),
    ).fetchall()
    out: dict = {}
    if row["active_tab_key"]:
        out["active"] = row["active_tab_key"]
    order = [t["tab_key"] for t in tabs if t["position"] is not None]
    if order:
        out["order"] = order
    clones = []
    views_out: dict = {}
    for t in tabs:
        if t["clone_of_tab_key"]:
            item = {"key": t["tab_key"], "baseKey": t["clone_of_tab_key"]}
            if t["tab_name"]:
                item["name"] = t["tab_name"]
            clones.append(item)
        if t["has_view"]:
            views_out[t["tab_key"]] = _assemble_tab(conn, t["id"])
    if clones:
        out["clones"] = clones
    if views_out:
        out["views"] = views_out
    return out


def _assemble_tab(conn: sqlite3.Connection, tab_pk: str) -> dict:
    groups = conn.execute(
        "SELECT column_name FROM layout_tab_groups WHERE tab_id=? ORDER BY position",
        (tab_pk,),
    ).fetchall()
    tab: dict = {"group": [r["column_name"] for r in groups]}
    sorters = conn.execute(
        "SELECT column_name, dir FROM layout_tab_sorters WHERE tab_id=? ORDER BY position",
        (tab_pk,),
    ).fetchall()
    if sorters:
        tab["sorters"] = [{"column": r["column_name"], "dir": r["dir"]} for r in sorters]
    cols = conn.execute(
        "SELECT field, position, hidden, frozen, width FROM layout_columns"
        " WHERE tab_id=? ORDER BY CASE WHEN position IS NULL THEN 1 ELSE 0 END, position, field",
        (tab_pk,),
    ).fetchall()
    order = [r["field"] for r in cols if r["position"] is not None]
    hidden = [r["field"] for r in cols if r["hidden"]]
    frozen = [r["field"] for r in cols if r["frozen"]]
    widths = {r["field"]: r["width"] for r in cols if r["width"] is not None}
    if order:
        tab["order"] = order
    if hidden:
        tab["hidden"] = hidden
    if frozen:
        tab["frozen"] = frozen
    if widths:
        tab["widths"] = widths
    filters = conn.execute(
        "SELECT field, op, v, v2 FROM layout_column_filters WHERE tab_id=? ORDER BY field",
        (tab_pk,),
    ).fetchall()
    if filters:
        tab["columnFilters"] = {
            r["field"]: {"op": r["op"], "v": r["v"] or "", "v2": r["v2"] or ""}
            for r in filters
        }
    return tab


def _handle_map(conn: sqlite3.Connection) -> dict[int, str]:
    return {r["id"]: r["handle"] for r in conn.execute(
        "SELECT id, handle FROM users WHERE handle IS NOT NULL AND handle <> ''"
    )}


def project_from_legacy(db: Database) -> None:
    """Copy old JSON rows into the new tables. Idempotent. Does not drop old tables."""
    with db.precious() as conn:
        if "views" not in {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }:
            return
        handles = assign_handles(conn)
        _project_defaults(conn, handles)
        _project_company_views(conn, handles)
        _project_saved_reports(conn, handles)
        _project_personal_schedules(conn, handles)
        _project_master_schedules(conn, handles)


def _updated_by(handles: dict[int, str], user_id) -> str | None:
    if user_id is None:
        return None
    return handles.get(int(user_id))


def _project_defaults(conn: sqlite3.Connection, handles: dict[int, str]) -> None:
    if not _table_exists(conn, "report_defaults"):
        return
    for r in conn.execute("SELECT * FROM report_defaults"):
        params = canonicalize_params(_loads(r["params_json"]))
        layout = canonicalize_layout(_loads(r["layout_json"]))
        _upsert_view(
            conn, view_id=default_view_id(r["report_key"]), kind="default",
            report_key=r["report_key"], name="Default", owner_handle=None,
            params=params, layout=layout,
            updated_by_handle=_updated_by(handles, r["updated_by"] if "updated_by" in r.keys() else None),
            legacy_source="report_defaults", legacy_id=_legacy_int(r["report_key"]),
        )


def _legacy_int(text: str) -> int:
    """Stable positive int for TEXT-keyed legacy rows (report_defaults)."""
    n = 0
    for ch in text:
        n = (n * 33 + ord(ch)) & 0x7FFFFFFF
    return n or 1


def _project_company_views(conn: sqlite3.Connection, handles: dict[int, str]) -> None:
    if not _table_exists(conn, "company_views"):
        return
    for r in conn.execute("SELECT * FROM company_views"):
        params = canonicalize_params(_loads(r["params_json"]))
        layout = canonicalize_layout(_loads(r["layout_json"]))
        _upsert_view(
            conn, view_id=company_view_id(r["report_key"], r["name"]), kind="company",
            report_key=r["report_key"], name=r["name"], owner_handle=None,
            params=params, layout=layout,
            updated_by_handle=_updated_by(handles, r["updated_by"] if "updated_by" in r.keys() else None),
            legacy_source="company_views", legacy_id=r["id"],
        )


def _project_saved_reports(conn: sqlite3.Connection, handles: dict[int, str]) -> None:
    if not _table_exists(conn, "saved_reports"):
        return
    for r in conn.execute("SELECT * FROM saved_reports"):
        handle = handles.get(r["user_id"])
        if not handle:
            continue
        params = canonicalize_params(_loads(r["params_json"]))
        layout = canonicalize_layout(_loads(r["layout_json"]))
        _upsert_view(
            conn, view_id=personal_view_id(handle, r["report_key"], r["name"]),
            kind="personal", report_key=r["report_key"], name=r["name"],
            owner_handle=handle, params=params, layout=layout,
            updated_by_handle=handle,
            legacy_source="saved_reports", legacy_id=r["id"],
        )


def _find_named_view(conn: sqlite3.Connection, *, kind: str, report_key: str, name: str,
                     owner_handle: str | None) -> str | None:
    if kind == "company":
        row = conn.execute(
            "SELECT id FROM views WHERE kind='company' AND report_key=? AND name=?",
            (report_key, name),
        ).fetchone()
    elif kind == "default":
        row = conn.execute(
            "SELECT id FROM views WHERE kind='default' AND report_key=?",
            (report_key,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM views WHERE kind='personal' AND owner_handle=? AND report_key=? AND name=?",
            (owner_handle, report_key, name),
        ).fetchone()
    return row["id"] if row else None


def _window_from_params(params: dict) -> tuple[str | None, str | None, str | None]:
    return (
        str(params.get("period") or "").strip() or None,
        str(params.get("start_date") or params.get("from") or "").strip() or None,
        str(params.get("end_date") or params.get("to") or "").strip() or None,
    )


def _resolve_schedule_view(
    conn: sqlite3.Connection, *, report_key: str, view_name: str, owner_handle: str | None,
    params: dict, layout: dict, kind: str, legacy_kind: str, legacy_id: int, name: str,
    prefer_company: bool,
) -> str:
    named = (view_name or "Default").strip() or "Default"
    is_default = named.lower() == "default"
    is_custom = named.lower() == "custom"
    live_id = None
    if prefer_company and not is_default and not is_custom:
        live_id = _find_named_view(conn, kind="company", report_key=report_key, name=named,
                                   owner_handle=None)
    if live_id is None and not is_default and not is_custom and owner_handle:
        live_id = _find_named_view(conn, kind="personal", report_key=report_key, name=named,
                                   owner_handle=owner_handle)
    if live_id is None and not is_default and not is_custom:
        live_id = _find_named_view(conn, kind="company", report_key=report_key, name=named,
                                   owner_handle=None)
    if live_id is None:
        live_id = _find_named_view(conn, kind="default", report_key=report_key, name="Default",
                                   owner_handle=None)
    ignore_window = kind == "company"
    empty_layout = not canonicalize_layout(layout)
    if live_id and not is_custom:
        live_params = assemble_params(conn, live_id)
        live_layout = assemble_layout(conn, live_id)
        if params_match(params, live_params, ignore_window=ignore_window) and layouts_match(layout, live_layout):
            return live_id
        if is_default and empty_layout:
            return live_id
    if live_id is None:
        live_id = _ensure_default_view(conn, report_key)
        if is_default and empty_layout:
            return live_id
    snap_name = f"Schedule {name}".strip() if name else f"Schedule {legacy_id}"
    if owner_handle:
        snap_id = personal_view_id(owner_handle, report_key, snap_name)
        snap_kind = "personal"
        snap_owner = owner_handle
    else:
        snap_id = company_view_id(report_key, snap_name)
        snap_kind = "company"
        snap_owner = None
    return _upsert_view(
        conn, view_id=snap_id, kind=snap_kind, report_key=report_key, name=snap_name,
        owner_handle=snap_owner, params=canonicalize_params(params),
        layout=canonicalize_layout(layout), updated_by_handle=owner_handle,
        legacy_source=f"snapshot:{legacy_kind}", legacy_id=legacy_id,
    )


def _ensure_default_view(conn: sqlite3.Connection, report_key: str) -> str:
    existing = _find_named_view(conn, kind="default", report_key=report_key, name="Default",
                                owner_handle=None)
    if existing:
        return existing
    return _upsert_view(
        conn, view_id=default_view_id(report_key), kind="default",
        report_key=report_key, name="Default", owner_handle=None,
        params={}, layout={}, updated_by_handle=None,
        legacy_source="report_defaults", legacy_id=_legacy_int(report_key),
    )


def _project_personal_schedules(conn: sqlite3.Connection, handles: dict[int, str]) -> None:
    if not _table_exists(conn, "schedules"):
        return
    for r in conn.execute("SELECT * FROM schedules"):
        handle = handles.get(r["owner_user_id"])
        if not handle:
            continue
        params = _loads(r["params_json"])
        layout = _loads(r["layout_json"])
        view_name = r["view_name"] if "view_name" in r.keys() else "Default"
        prefer = str((params or {}).get("view_source") or "").strip().lower() == "company"
        view_id = _resolve_schedule_view(
            conn, report_key=r["report_key"], view_name=view_name, owner_handle=handle,
            params=params, layout=layout, kind="personal", legacy_kind="personal",
            legacy_id=r["id"], name="", prefer_company=prefer,
        )
        if view_id is None:
            view_id = _ensure_default_view(conn, r["report_key"])
        _upsert_schedule(
            conn, kind="personal", view_id=view_id, owner_handle=handle,
            name=view_name or "", cadence=_loads(r["cadence"]), params=params,
            recipients=r["recipients"] or "", sharepoint_path=r["sharepoint_path"] or "",
            filename_template=(r["filename_template"] if "filename_template" in r.keys() else "") or "",
            is_shared=0, is_active=bool(r["is_active"]),
            run_as_handle=None,
            active_from=r["start_date"], active_until=r["end_date"],
            catch_up_pending=bool(r["catch_up_pending"]) if "catch_up_pending" in r.keys() else False,
            catch_up_for_date=r["catch_up_for_date"] if "catch_up_for_date" in r.keys() else None,
            last_claimed_at=r["last_claimed_at"] if "last_claimed_at" in r.keys() else None,
            created_at=r["created_at"], legacy_kind="personal", legacy_id=r["id"],
        )


def _project_master_schedules(conn: sqlite3.Connection, handles: dict[int, str]) -> None:
    if not _table_exists(conn, "master_schedules"):
        return
    for r in conn.execute("SELECT * FROM master_schedules"):
        owner = None
        if "owner_user_id" in r.keys() and r["owner_user_id"] is not None:
            owner = handles.get(int(r["owner_user_id"]))
        run_as = None
        if "run_as_user_id" in r.keys() and r["run_as_user_id"] is not None:
            run_as = handles.get(int(r["run_as_user_id"]))
        params = _loads(r["params_json"])
        layout = _loads(r["layout_json"])
        view_name = r["view_name"] if "view_name" in r.keys() else "Default"
        view_id = _resolve_schedule_view(
            conn, report_key=r["report_key"], view_name=view_name, owner_handle=owner,
            params=params, layout=layout, kind="company", legacy_kind="master",
            legacy_id=r["id"], name=r["name"], prefer_company=True,
        )
        if view_id is None:
            view_id = _ensure_default_view(conn, r["report_key"])
        _upsert_schedule(
            conn, kind="company", view_id=view_id, owner_handle=owner, name=r["name"],
            cadence=_loads(r["cadence"]), params=params,
            recipients=r["recipients"] or "", sharepoint_path=r["sharepoint_path"] or "",
            filename_template=(r["filename_template"] if "filename_template" in r.keys() else "") or "",
            is_shared=bool(r["is_shared"]) if "is_shared" in r.keys() else True,
            is_active=bool(r["is_active"]),
            run_as_handle=run_as,
            active_from=None, active_until=None,
            catch_up_pending=bool(r["catch_up_pending"]) if "catch_up_pending" in r.keys() else False,
            catch_up_for_date=r["catch_up_for_date"] if "catch_up_for_date" in r.keys() else None,
            last_claimed_at=r["last_claimed_at"] if "last_claimed_at" in r.keys() else None,
            created_at=r["created_at"], legacy_kind="master", legacy_id=r["id"],
        )


def _upsert_schedule(conn: sqlite3.Connection, **row) -> None:
    cadence = row["cadence"] if isinstance(row["cadence"], dict) else {}
    freq = str(cadence.get("freq") or "daily").lower()
    if freq not in ("daily", "weekly", "monthly"):
        freq = "daily"
    time = str(cadence.get("time") or "08:00")
    params = row["params"] if isinstance(row["params"], dict) else {}
    period, start, end = _window_from_params(params)
    folder = str(params.get("folder_kind") or "").strip()
    if folder not in ("onedrive", "sharepoint"):
        folder = "onedrive"
    existing = conn.execute(
        "SELECT id FROM report_schedules WHERE legacy_kind=? AND legacy_id=?",
        (row["legacy_kind"], row["legacy_id"]),
    ).fetchone()
    sid = existing["id"] if existing else _unique_schedule_id(
        conn, row["kind"], row["owner_handle"], row["view_id"], freq, time, row["name"],
        row["legacy_id"],
    )
    values = dict(
        id=sid, kind=row["kind"], view_id=row["view_id"], owner_handle=row["owner_handle"],
        name=row["name"] or "", freq=freq, time=time,
        window_period=period, window_start=start, window_end=end,
        sharepoint_path=row["sharepoint_path"], filename_template=row["filename_template"],
        folder_kind=folder,
        email_subject=str(params.get("email_subject") or ""),
        email_html=str(params.get("email_html") or ""),
        email_on_no_data=1 if _as_bool(params.get("email_on_no_data")) else 0,
        email_on_no_data_me_only=1 if _as_bool(params.get("email_on_no_data_me_only")) else 0,
        split_by_salesman=1 if _as_bool(params.get("split_by_salesman")) else 0,
        email_to_salesmen=1 if _as_bool(params.get("email_to_salesmen")) else 0,
        skip_sabbath=0 if params.get("skip_sabbath") in (0, False, "0", "false") else 1,
        run_as_handle=row["run_as_handle"],
        is_shared=1 if row["is_shared"] else 0,
        is_active=1 if row["is_active"] else 0,
        active_from=row["active_from"], active_until=row["active_until"],
        catch_up_pending=1 if row["catch_up_pending"] else 0,
        catch_up_for_date=row["catch_up_for_date"],
        last_claimed_at=row["last_claimed_at"],
        legacy_kind=row["legacy_kind"], legacy_id=row["legacy_id"],
    )
    if row["created_at"]:
        values["created_at"] = row["created_at"]
    cols = ", ".join(values.keys())
    placeholders = ", ".join("?" for _ in values)
    if existing:
        sets = [f"{k}=?" for k in values if k not in ("id", "legacy_kind", "legacy_id")]
        conn.execute(
            f"UPDATE report_schedules SET {', '.join(sets)} WHERE id=?",
            [values[k] for k in values if k not in ("id", "legacy_kind", "legacy_id")] + [sid],
        )
        conn.execute("DELETE FROM schedule_weekdays WHERE schedule_id=?", (sid,))
        conn.execute("DELETE FROM schedule_monthdays WHERE schedule_id=?", (sid,))
        conn.execute("DELETE FROM schedule_recipients WHERE schedule_id=?", (sid,))
        conn.execute("DELETE FROM schedule_email_salesmen WHERE schedule_id=?", (sid,))
    else:
        conn.execute(
            f"INSERT INTO report_schedules({cols}) VALUES ({placeholders})",
            list(values.values()),
        )
    for d in cadence.get("weekdays") or []:
        conn.execute(
            "INSERT OR IGNORE INTO schedule_weekdays(schedule_id, weekday) VALUES (?,?)",
            (sid, int(d)),
        )
    monthdays = cadence.get("monthdays") or (
        [cadence["monthday"]] if cadence.get("monthday") is not None else []
    )
    for d in monthdays:
        conn.execute(
            "INSERT OR IGNORE INTO schedule_monthdays(schedule_id, monthday) VALUES (?,?)",
            (sid, int(d)),
        )
    for email in split_recipients(row["recipients"]):
        conn.execute(
            "INSERT OR IGNORE INTO schedule_recipients(id, schedule_id, email, role)"
            " VALUES (?,?,?,?)",
            (f"{sid}__to-{slug(email, 60)}", sid, email.lower(), "to"),
        )
    for email in _as_str_list(params.get("email_cc")):
        if "@" in email:
            conn.execute(
                "INSERT OR IGNORE INTO schedule_recipients(id, schedule_id, email, role)"
                " VALUES (?,?,?,?)",
                (f"{sid}__cc-{slug(email, 60)}", sid, email.lower(), "cc"),
            )
    for email in _as_str_list(params.get("email_bcc")):
        if "@" in email:
            conn.execute(
                "INSERT OR IGNORE INTO schedule_recipients(id, schedule_id, email, role)"
                " VALUES (?,?,?,?)",
                (f"{sid}__bcc-{slug(email, 60)}", sid, email.lower(), "bcc"),
            )
    for salesman in _as_str_list(params.get("email_salesman_keys")):
        conn.execute(
            "INSERT OR IGNORE INTO schedule_email_salesmen(schedule_id, salesman) VALUES (?,?)",
            (sid, salesman),
        )


def _unique_schedule_id(conn, kind, owner_handle, view_id, freq, time, name, legacy_id) -> str:
    report = conn.execute("SELECT report_key FROM views WHERE id=?", (view_id,)).fetchone()
    report_key = report["report_key"] if report else "report"
    prefix = owner_handle or "co"
    time_key = (time or "08:00").replace(":", "")
    candidates = []
    if name:
        candidates.append(_clip(f"{prefix}-{slug(report_key)}-{slug(name)}"))
    candidates.append(_clip(f"{prefix}-{slug(report_key)}-{freq}-{time_key}"))
    candidates.append(_clip(f"{prefix}-{slug(report_key)}-{freq}-{time_key}-{legacy_id}"))
    for cand in candidates:
        hit = conn.execute("SELECT 1 FROM report_schedules WHERE id=?", (cand,)).fetchone()
        if not hit:
            return cand
    return _clip(f"{prefix}-{slug(report_key)}-{legacy_id}")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,),
    ).fetchone()
    return row is not None
