"""Views as columns + child tables. No params_json / layout_json blobs."""

from __future__ import annotations

import json


def hydrate(row, conn) -> dict:
    view = dict(row)
    view_id = view["id"]
    salesmen = [
        r["salesman"]
        for r in conn.execute(
            "SELECT salesman FROM view_salesmen WHERE view_id = ? ORDER BY salesman",
            (view_id,),
        ).fetchall()
    ]
    statuses = [
        r["status"]
        for r in conn.execute(
            "SELECT status FROM view_statuses WHERE view_id = ? ORDER BY status",
            (view_id,),
        ).fetchall()
    ]
    customers = [
        r["customer_account"]
        for r in conn.execute(
            "SELECT customer_account FROM view_customers WHERE view_id = ? ORDER BY customer_account",
            (view_id,),
        ).fetchall()
    ]
    tabs = conn.execute(
        """SELECT id, tab_key, position, clone_of_tab_key, tab_name, has_view, groups_explicit
           FROM layout_tabs WHERE view_id = ? ORDER BY position, id""",
        (view_id,),
    ).fetchall()
    params: dict = {}
    if view.get("period"):
        params["period"] = view["period"]
    if view.get("start_date"):
        params["from_date"] = view["start_date"]
    if view.get("end_date"):
        params["to_date"] = view["end_date"]
    if view.get("year"):
        params["year"] = view["year"]
    if view.get("mode"):
        params["n4_mode"] = view["mode"]
    if salesmen:
        params["salesman"] = salesmen[0] if len(salesmen) == 1 else ""
        params["salesmen"] = salesmen
    if statuses:
        params["status"] = statuses[0]
    if customers:
        params["customers"] = customers
    layout_views: dict = {}
    order: list[str] = []
    clones: list[dict] = []
    for tab in tabs:
        tab_id = tab["id"]
        key = tab["tab_key"]
        if tab["position"] is not None:
            order.append(key)
        if tab["clone_of_tab_key"]:
            clones.append(
                {"key": key, "baseKey": tab["clone_of_tab_key"], "name": tab["tab_name"] or key}
            )
        groups = [
            r["column_name"]
            for r in conn.execute(
                "SELECT column_name FROM layout_tab_groups WHERE tab_id = ? ORDER BY position",
                (tab_id,),
            ).fetchall()
        ]
        sorters = [
            {"column": r["column_name"], "dir": r["dir"]}
            for r in conn.execute(
                "SELECT column_name, dir FROM layout_tab_sorters WHERE tab_id = ? ORDER BY position",
                (tab_id,),
            ).fetchall()
        ]
        cols = conn.execute(
            """SELECT field, position, hidden, frozen, width
               FROM layout_columns WHERE tab_id = ? ORDER BY position, field""",
            (tab_id,),
        ).fetchall()
        filters = conn.execute(
            "SELECT field, op, v, v2 FROM layout_column_filters WHERE tab_id = ?",
            (tab_id,),
        ).fetchall()
        col_order = [c["field"] for c in cols if c["position"] is not None]
        hidden = [c["field"] for c in cols if c["hidden"]]
        frozen = [c["field"] for c in cols if c["frozen"]]
        widths = {c["field"]: c["width"] for c in cols if c["width"] is not None}
        column_filters = {
            f["field"]: {"op": f["op"], "v": f["v"] or "", "v2": f["v2"] or ""}
            for f in filters
        }
        if tab["has_view"] or groups or sorters or cols or filters:
            layout_views[key] = {
                "hidden": hidden,
                "frozen": frozen,
                "order": col_order or None,
                "sorters": sorters or None,
                "columnFilters": column_filters,
                "group": groups,
                "groups_explicit": bool(tab["groups_explicit"]),
                "widths": widths,
            }
    view["params"] = params
    view["layout"] = {
        "active": view.get("active_tab_key"),
        "order": order,
        "clones": clones,
        "views": layout_views,
    }
    return view


def save_filters_and_layout(
    conn,
    view_id: int,
    filters: dict | None,
    layout: dict | None,
    include_period: int | None = None,
) -> None:
    filters = filters or {}
    layout = layout or {}
    if isinstance(filters.get("group"), str):
        raise ValueError("views.group must stay an array")
    if isinstance(filters.get("group"), list) and not (layout.get("views") or {}):
        layout = {
            **layout,
            "views": {**(layout.get("views") or {}), "_default": {"group": filters["group"]}},
        }
    salesman = (filters.get("salesman") or "").strip()
    salesmen = [s for s in (filters.get("salesmen") or ([salesman] if salesman else [])) if s]
    customers = filters.get("customers") or []
    if isinstance(customers, str):
        customers = [part.strip() for part in customers.split(",") if part.strip()]
    status = (filters.get("status") or "").strip()
    sets = [
        "period = ?",
        "start_date = ?",
        "end_date = ?",
        "year = ?",
        "mode = ?",
        "active_tab_key = ?",
    ]
    values = [
        filters.get("period") or None,
        filters.get("from_date") or None,
        filters.get("to_date") or None,
        filters.get("year") or None,
        filters.get("n4_mode") or filters.get("mode") or None,
        layout.get("active") or None,
    ]
    if include_period is not None:
        sets.append("include_period = ?")
        values.append(include_period)
    values.append(view_id)
    conn.execute(f"UPDATE views SET {', '.join(sets)} WHERE id = ?", values)
    conn.execute("DELETE FROM view_salesmen WHERE view_id = ?", (view_id,))
    conn.execute("DELETE FROM view_statuses WHERE view_id = ?", (view_id,))
    conn.execute("DELETE FROM view_customers WHERE view_id = ?", (view_id,))
    conn.execute("DELETE FROM layout_tabs WHERE view_id = ?", (view_id,))
    for name in salesmen:
        conn.execute(
            "INSERT INTO view_salesmen (view_id, salesman) VALUES (?, ?)",
            (view_id, name),
        )
    if status:
        conn.execute(
            "INSERT INTO view_statuses (view_id, status) VALUES (?, ?)",
            (view_id, status),
        )
    for account in customers:
        conn.execute(
            "INSERT INTO view_customers (view_id, customer_account) VALUES (?, ?)",
            (view_id, str(account)),
        )
    _write_layout_tabs(conn, view_id, layout)


def _write_layout_tabs(conn, view_id: int, layout: dict) -> None:
    views = layout.get("views") if isinstance(layout.get("views"), dict) else {}
    order = layout.get("order") if isinstance(layout.get("order"), list) else []
    clones = layout.get("clones") if isinstance(layout.get("clones"), list) else []
    clone_of = {}
    clone_name = {}
    for clone in clones:
        if isinstance(clone, dict) and clone.get("key"):
            clone_of[clone["key"]] = clone.get("baseKey") or ""
            clone_name[clone["key"]] = clone.get("name") or ""
    keys: list[str] = []
    for key in order:
        if key not in keys:
            keys.append(key)
    for key in views:
        if key not in keys:
            keys.append(key)
    for pos, key in enumerate(keys, start=1):
        tab_view = views.get(key) if isinstance(views.get(key), dict) else {}
        has_view = 1 if key in views else 0
        groups = tab_view.get("group") if isinstance(tab_view.get("group"), list) else []
        groups_explicit = 1 if has_view else 0
        if "groups_explicit" in tab_view:
            groups_explicit = 1 if tab_view.get("groups_explicit") else 0
        in_order = key in order
        cur = conn.execute(
            """INSERT INTO layout_tabs (
                   view_id, tab_key, position, clone_of_tab_key, tab_name, has_view, groups_explicit
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                view_id,
                key,
                pos if in_order else (pos if not order else None),
                clone_of.get(key) or None,
                clone_name.get(key) or None,
                has_view,
                groups_explicit,
            ),
        )
        tab_id = int(cur.lastrowid)
        for gpos, col in enumerate(groups, start=1):
            conn.execute(
                "INSERT INTO layout_tab_groups (tab_id, position, column_name) VALUES (?, ?, ?)",
                (tab_id, gpos, str(col)),
            )
        sorters = tab_view.get("sorters") if isinstance(tab_view.get("sorters"), list) else []
        for spos, sorter in enumerate(sorters, start=1):
            if not isinstance(sorter, dict) or not sorter.get("column"):
                continue
            direction = sorter.get("dir") if sorter.get("dir") in ("asc", "desc") else "asc"
            conn.execute(
                """INSERT INTO layout_tab_sorters (tab_id, position, column_name, dir)
                   VALUES (?, ?, ?, ?)""",
                (tab_id, spos, str(sorter["column"]), direction),
            )
        hidden = set(tab_view.get("hidden") or [])
        frozen = set(tab_view.get("frozen") or [])
        col_order = [f for f in (tab_view.get("order") or []) if f]
        widths = tab_view.get("widths") if isinstance(tab_view.get("widths"), dict) else {}
        fields: list[str] = []
        for field in col_order:
            if field not in fields:
                fields.append(field)
        for field in list(hidden) + list(frozen) + list(widths):
            if field not in fields:
                fields.append(field)
        for cpos, field in enumerate(fields, start=1):
            width = widths.get(field)
            conn.execute(
                """INSERT INTO layout_columns (tab_id, field, position, hidden, frozen, width)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    tab_id,
                    str(field),
                    cpos if field in col_order else None,
                    1 if field in hidden else 0,
                    1 if field in frozen else 0,
                    float(width) if width not in (None, "") else None,
                ),
            )
        col_filters = tab_view.get("columnFilters") if isinstance(tab_view.get("columnFilters"), dict) else {}
        for field, spec in col_filters.items():
            if not isinstance(spec, dict):
                continue
            conn.execute(
                """INSERT INTO layout_column_filters (tab_id, field, op, v, v2)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    tab_id,
                    str(field),
                    str(spec.get("op") or "contains"),
                    str(spec.get("v") or ""),
                    str(spec.get("v2") or ""),
                ),
            )


def migrate_params_json(conn) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(views)").fetchall()}
    for name, ddl in (
        ("period", "TEXT"),
        ("start_date", "TEXT"),
        ("end_date", "TEXT"),
        ("year", "TEXT"),
        ("mode", "TEXT"),
        ("active_tab_key", "TEXT"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE views ADD COLUMN {name} {ddl}")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS view_salesmen (
            view_id INTEGER NOT NULL REFERENCES views(id) ON DELETE CASCADE,
            salesman TEXT NOT NULL,
            PRIMARY KEY (view_id, salesman)
        );
        CREATE TABLE IF NOT EXISTS view_statuses (
            view_id INTEGER NOT NULL REFERENCES views(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            PRIMARY KEY (view_id, status)
        );
        CREATE TABLE IF NOT EXISTS view_customers (
            view_id INTEGER NOT NULL REFERENCES views(id) ON DELETE CASCADE,
            customer_account TEXT NOT NULL,
            PRIMARY KEY (view_id, customer_account)
        );
        CREATE TABLE IF NOT EXISTS layout_tabs (
            id INTEGER PRIMARY KEY,
            view_id INTEGER NOT NULL REFERENCES views(id) ON DELETE CASCADE,
            tab_key TEXT NOT NULL,
            position INTEGER,
            clone_of_tab_key TEXT,
            tab_name TEXT,
            has_view INTEGER NOT NULL DEFAULT 0,
            groups_explicit INTEGER NOT NULL DEFAULT 1,
            UNIQUE (view_id, tab_key)
        );
        CREATE TABLE IF NOT EXISTS layout_tab_groups (
            tab_id INTEGER NOT NULL REFERENCES layout_tabs(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            column_name TEXT NOT NULL,
            PRIMARY KEY (tab_id, position)
        );
        CREATE TABLE IF NOT EXISTS layout_tab_sorters (
            tab_id INTEGER NOT NULL REFERENCES layout_tabs(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            column_name TEXT NOT NULL,
            dir TEXT NOT NULL,
            PRIMARY KEY (tab_id, position)
        );
        CREATE TABLE IF NOT EXISTS layout_columns (
            tab_id INTEGER NOT NULL REFERENCES layout_tabs(id) ON DELETE CASCADE,
            field TEXT NOT NULL,
            position INTEGER,
            hidden INTEGER NOT NULL DEFAULT 0,
            frozen INTEGER NOT NULL DEFAULT 0,
            width REAL,
            PRIMARY KEY (tab_id, field)
        );
        CREATE TABLE IF NOT EXISTS layout_column_filters (
            tab_id INTEGER NOT NULL REFERENCES layout_tabs(id) ON DELETE CASCADE,
            field TEXT NOT NULL,
            op TEXT NOT NULL DEFAULT 'contains',
            v TEXT,
            v2 TEXT,
            PRIMARY KEY (tab_id, field)
        );
        """
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(views)").fetchall()}
    if "params_json" not in cols:
        return
    rows = conn.execute("SELECT id, params_json FROM views").fetchall()
    for row in rows:
        raw = row["params_json"] or "{}"
        try:
            params = json.loads(raw)
        except json.JSONDecodeError:
            params = {}
        if not isinstance(params, dict):
            params = {}
        layout = {}
        if isinstance(params.get("group"), list):
            layout = {"views": {"_default": {"group": params["group"]}}}
        save_filters_and_layout(conn, row["id"], params, layout)
    conn.execute("ALTER TABLE views DROP COLUMN params_json")
