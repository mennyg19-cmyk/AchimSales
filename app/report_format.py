"""Report Formatter: tab columns from catalog mocks, layout merge into views.

Default is the company view named Company Default (the report page's
company_default save). There is no separate kind=default row.
"""

from __future__ import annotations

import catalog
import store

FILTER_OPS = (
    "contains", "equals", "starts", "ends", "empty", "notEmpty",
    "gt", "lt", "between", "on", "before", "after",
)
COMPANY_DEFAULT_NAME = "Company Default"
_NAME_MAX = 120

_PAYLOADS = {
    "invoiced": catalog.invoiced_payload,
    "ordered": catalog.ordered_payload,
    "salesman": catalog.salesman_payload,
    "number_4": catalog.number_4_payload,
    "customer_activity": catalog.customer_activity_payload,
    "item_averages": catalog.item_averages_payload,
    "sales_by_state": catalog.sales_by_state_payload,
}


def report_choices() -> list[dict]:
    return [{"key": item["key"], "title": item["title"]} for item in catalog.REPORTS]


def remember_payload(report_key: str, payload: dict | None) -> None:
    tabs = _tabs_from_payload(payload)
    if tabs:
        store.replace_catalog(report_key, tabs)


def _tabs_from_payload(payload: dict | None) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("tabs")
    if raw is None and isinstance(payload.get("data"), dict):
        raw = payload["data"].get("tabs")
    items: list[tuple[str, dict]] = []
    if isinstance(raw, dict):
        items = [(str(key), tab) for key, tab in raw.items() if isinstance(tab, dict)]
    elif isinstance(raw, list):
        for index, tab in enumerate(raw):
            if isinstance(tab, dict):
                key = str(tab.get("key") or tab.get("name") or f"tab_{index}").strip()
                if key:
                    items.append((key, tab))
    out = []
    for key, tab in items:
        out.append({
            "key": key,
            "name": str(tab.get("name") or key),
            "columns": _defined_columns(tab.get("columns")) or _columns(tab.get("rows")),
        })
    return out


def _defined_columns(columns) -> list[dict]:
    fields: list[dict] = []
    seen: set[str] = set()
    for col in columns or []:
        if isinstance(col, dict):
            field = str(col.get("field") or col.get("header") or "").strip()
            header = str(col.get("header") or field)
        else:
            field = header = str(col).strip()
        if field and field not in seen:
            seen.add(field)
            fields.append({"field": field, "header": header})
    return fields


def tabs_for(report_key: str) -> list[dict]:
    stored = store.catalog_tabs(report_key)
    if stored:
        return stored
    if catalog.spec(report_key) is None:
        return []
    if report_key == "customer_last_order":
        sample = catalog.last_order_for(catalog.CUSTOMERS[0]["account"]) or {}
        return [{
            "key": "lines",
            "name": "Lines",
            "columns": _columns(sample.get("lines")),
        }]
    build = _PAYLOADS.get(report_key)
    if build is None:
        return []
    tabs = (build().get("data") or {}).get("tabs") or {}
    out = []
    for key, tab in tabs.items():
        rows = tab.get("rows") if isinstance(tab, dict) else []
        name = tab.get("name") if isinstance(tab, dict) else key
        out.append({"key": str(key), "name": str(name or key), "columns": _columns(rows)})
    return out


def _columns(rows) -> list[dict]:
    fields: list[dict] = []
    seen: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for field in row:
            text = str(field).strip()
            if text and text not in seen:
                seen.add(text)
                fields.append({"field": text, "header": text})
    return fields


def apply_format(layout: dict | None, tabs_in: list) -> dict:
    """Merge group / sort / filter into a layout. Hidden columns and order stay."""
    base = dict(layout or {})
    views = dict(base.get("views") or {})
    for tab in tabs_in or []:
        if not isinstance(tab, dict):
            continue
        key = str(tab.get("key") or "").strip()
        if not key:
            continue
        prev = dict(views.get(key) or {})
        if tab.get("set_group"):
            prev["group"] = [
                str(col).strip() for col in (tab.get("group") or []) if str(col).strip()
            ]
            prev["groups_explicit"] = True
        else:
            prev.pop("group", None)
            prev["groups_explicit"] = False
        sorters = []
        for sorter in tab.get("sorters") or []:
            if not isinstance(sorter, dict):
                continue
            column = str(sorter.get("column") or "").strip()
            if not column:
                continue
            direction = "desc" if str(sorter.get("dir") or "").lower() == "desc" else "asc"
            sorters.append({"column": column, "dir": direction})
        if sorters:
            prev["sorters"] = sorters
        else:
            prev.pop("sorters", None)
        filters: dict = {}
        for spec in tab.get("filters") or []:
            if not isinstance(spec, dict):
                continue
            column = str(spec.get("column") or "").strip()
            op = str(spec.get("op") or "contains")
            if not column or op not in FILTER_OPS:
                continue
            filters[column] = {
                "op": op,
                "v": "" if spec.get("v") is None else str(spec.get("v")),
                "v2": "" if spec.get("v2") is None else str(spec.get("v2")),
            }
        if filters:
            prev["columnFilters"] = filters
        else:
            prev.pop("columnFilters", None)
        if "hidden" in tab:
            prev["hidden"] = [
                str(col).strip() for col in (tab.get("hidden") or []) if str(col).strip()
            ]
        if prev:
            views[key] = prev
        else:
            views.pop(key, None)
    if views:
        base["views"] = views
    elif "views" in base:
        base.pop("views")
    if any(isinstance(tab, dict) and "show_tab" in tab for tab in (tabs_in or [])):
        base["order"] = [
            str(tab.get("key")).strip()
            for tab in tabs_in
            if isinstance(tab, dict) and tab.get("show_tab") and str(tab.get("key") or "").strip()
        ]
    return base


def editor_layout(layout: dict | None) -> dict:
    """Drop group when it was not set, so an empty list means Flat list."""
    base = dict(layout or {})
    views = {}
    for key, spec in (base.get("views") or {}).items():
        if not isinstance(spec, dict):
            continue
        cleaned = dict(spec)
        if not cleaned.get("groups_explicit"):
            cleaned.pop("group", None)
        views[key] = cleaned
    base["views"] = views
    return base


def format_choices(report_key: str) -> list[dict]:
    owners = {
        user["email"]: (user.get("display_name") or user["email"])
        for user in store.list_users()
    }
    choices = [{"id": "default", "label": "Default"}]
    personal = []
    for view in store.list_views_for_report("", report_key, True):
        if view["kind"] == "company":
            if view["name"] == COMPANY_DEFAULT_NAME:
                continue
            choices.append({"id": f"company:{view['id']}", "label": view["name"]})
            continue
        personal.append(view)
    personal.sort(key=lambda view: (
        owners.get(view.get("owner_email") or "", "").lower(),
        (view.get("name") or "").lower(),
    ))
    for view in personal:
        owner = owners.get(view.get("owner_email") or "") or view.get("owner_email") or "Unknown"
        choices.append({
            "id": f"user:{view['id']}",
            "label": f"{owner} — {view['name']}",
        })
    return choices


def parse_format(raw: str | None) -> tuple[str, object]:
    text = (raw or "").strip()
    if not text or text.lower() in {"default", "company default"}:
        return "default", ""
    if text.startswith("company:"):
        ident = text.split(":", 1)[1]
        if ident.isdigit():
            return "company", int(ident)
        return "bad", text
    if text.startswith("user:"):
        ident = text.split(":", 1)[1]
        if ident.isdigit():
            return "user", int(ident)
        return "bad", text
    name = text[:_NAME_MAX]
    if name.lower() in {"default", "company default"}:
        return "default", ""
    return "company_name", name


def _views(report_key: str) -> list[dict]:
    return store.list_views_for_report("", report_key, True)


def layout_for(report_key: str, kind: str, key) -> tuple[dict, str, str | None]:
    if kind == "bad":
        return {}, "", "Unknown format."
    views = _views(report_key)
    if kind == "default":
        row = _company_default(views)
        return editor_layout(row["layout"] if row else {}), "default", None
    if kind == "company":
        row = next((view for view in views if view["id"] == key and view["kind"] == "company"), None)
        if row is None:
            return {}, "", "No company format with that id."
        return editor_layout(row["layout"]), f"company:{row['id']}", None
    if kind == "company_name":
        row = next(
            (view for view in views if view["kind"] == "company" and view["name"] == key),
            None,
        )
        if row is None:
            return {}, "", f"No company format named {key}."
        ident = "default" if row["name"] == COMPANY_DEFAULT_NAME else f"company:{row['id']}"
        return editor_layout(row["layout"]), ident, None
    row = next((view for view in views if view["id"] == key and view["kind"] != "company"), None)
    if row is None:
        return {}, "", "That saved view was not found."
    return editor_layout(row["layout"]), f"user:{row['id']}", None


def _company_default(views: list[dict]) -> dict | None:
    matches = [
        view for view in views
        if view["kind"] == "company" and view["name"] == COMPANY_DEFAULT_NAME
    ]
    if not matches:
        return None
    return min(matches, key=lambda view: view["id"])


def save_format(report_key: str, kind: str, key, tabs) -> tuple[str, dict, str | None, int]:
    if kind == "bad":
        return "", {}, "Unknown format.", 400
    views = _views(report_key)
    if kind == "default":
        row = _company_default(views)
        layout = apply_format(row["layout"] if row else {}, tabs)
        if row is None:
            view_id = store.add_view(None, report_key, COMPANY_DEFAULT_NAME, "company", {}, 0, layout)
            saved = store.get_view(view_id)
        else:
            saved = store.replace_view_layout(row["id"], layout)
        return "default", editor_layout(saved["layout"] if saved else layout), None, 200
    if kind == "user":
        row = next((view for view in views if view["id"] == key and view["kind"] != "company"), None)
        if row is None:
            return "", {}, "That saved view was not found.", 404
        layout = apply_format(row["layout"], tabs)
        saved = store.replace_view_layout(row["id"], layout)
        return f"user:{row['id']}", editor_layout(saved["layout"] if saved else layout), None, 200
    if kind == "company":
        row = next((view for view in views if view["id"] == key and view["kind"] == "company"), None)
        if row is None:
            return "", {}, "No company format with that id.", 404
        return _write_company(row, apply_format(row["layout"], tabs))
    name = str(key)
    row = next(
        (view for view in views if view["kind"] == "company" and view["name"] == name),
        None,
    )
    layout = apply_format(row["layout"] if row else {}, tabs)
    if row is None:
        view_id = store.add_view(None, report_key, name, "company", {}, 0, layout)
        saved = store.get_view(view_id)
        return f"company:{view_id}", editor_layout(saved["layout"] if saved else layout), None, 200
    return _write_company(row, layout)


def _write_company(row: dict, layout: dict) -> tuple[str, dict, str | None, int]:
    saved = store.replace_view_layout(row["id"], layout)
    ident = "default" if row["name"] == COMPANY_DEFAULT_NAME else f"company:{row['id']}"
    return ident, editor_layout(saved["layout"] if saved else layout), None, 200
