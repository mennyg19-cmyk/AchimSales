"""Check explorer edits so a bad layout_json cannot be saved.

Excel uses a missing ``group`` key as “never set” and fills the builder default
grouping. An empty array is the saved ungroup. The GUI accepts either, but
export does not — so deleting ``group`` looks like ungroup on screen and then
the emailed file groups every row again.
"""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_ASSIGN = re.compile(
    r"(?i)\b((?:[A-Za-z_]\w*_json))\s*=\s*'((?:[^']|'')*)'",
)


def validate_column_value(column: str, value: Any) -> str | None:
    """Return an error message, or None if the value can be stored."""
    name = (column or "").strip()
    if not name.lower().endswith("_json"):
        return None
    raw = "" if value is None else str(value)
    if not raw.strip():
        parsed: Any = {}
    else:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return f"{name} is not valid JSON ({exc.msg} at char {exc.pos})."
    low = name.lower()
    if low == "layout_json":
        errs = layout_errors(parsed)
        return errs[0] if errs else None
    if low == "params_json":
        if parsed is None:
            return None
        if not isinstance(parsed, dict):
            return "params_json must be a JSON object, e.g. {\"period\": \"ytd\"}."
        return None
    if not isinstance(parsed, (dict, list)):
        return f"{name} must be a JSON object or array."
    return None


def layout_errors(obj: Any) -> list[str]:
    if obj is None:
        return []
    if not isinstance(obj, dict):
        return ["layout_json must be a JSON object, e.g. {\"views\": {\"by_order\": {\"group\": []}}}."]
    errs: list[str] = []
    if "groups" in obj:
        errs.append(
            "layout_json.groups is not used. Grouping is views.<tab>.group — "
            "an array of column names. Use [] to ungroup."
        )
    if "views" in obj and obj["views"] is not None and not isinstance(obj["views"], dict):
        errs.append("layout_json.views must be an object of tab keys.")
        return errs
    views = obj.get("views")
    if isinstance(views, dict):
        for key, view in views.items():
            errs.extend(_view_errors(str(key), view))
    if "order" in obj and obj["order"] is not None and not _string_list(obj["order"]):
        errs.append("layout_json.order must be an array of tab-key strings.")
    if "clones" in obj and obj["clones"] is not None:
        if not isinstance(obj["clones"], list):
            errs.append("layout_json.clones must be an array.")
        else:
            for i, clone in enumerate(obj["clones"]):
                if not isinstance(clone, dict) or not str(clone.get("key") or "").strip() \
                        or not str(clone.get("baseKey") or "").strip():
                    errs.append(f"layout_json.clones[{i}] needs key and baseKey strings.")
    return errs


def _view_errors(tab: str, view: Any) -> list[str]:
    path = f"views.{tab}"
    if not isinstance(view, dict):
        return [f"{path} must be an object."]
    errs: list[str] = []
    if "groups" in view:
        errs.append(
            f"{path}.groups is not used. Grouping is {path}.group — "
            f"an array of column names. To ungroup use {path}.group: []."
        )
    if "group" not in view:
        errs.append(
            f"{path} is missing group. Omitting it uses the report’s default grouping "
            f"(By Order can group every row). To ungroup set {path}.group to []. "
            f"To group set it to [\"ColumnName\"]."
        )
    else:
        g = view["group"]
        if g is None:
            errs.append(f"{path}.group is null. Use [] to ungroup.")
        elif not isinstance(g, list) or not all(isinstance(x, str) for x in g):
            errs.append(
                f"{path}.group must be an array of column-name strings, "
                f"e.g. [\"Salesman\"] or [] to ungroup."
            )
    if "hidden" in view and view["hidden"] is not None and not _string_list(view["hidden"]):
        errs.append(f"{path}.hidden must be an array of column-name strings.")
    if "frozen" in view and view["frozen"] is not None and not _string_list(view["frozen"]):
        errs.append(f"{path}.frozen must be an array of column-name strings.")
    if "columnFilters" in view and view["columnFilters"] is not None \
            and not isinstance(view["columnFilters"], dict):
        errs.append(f"{path}.columnFilters must be an object.")
    if "widths" in view and view["widths"] is not None and not isinstance(view["widths"], dict):
        errs.append(f"{path}.widths must be an object.")
    if "sorters" in view and view["sorters"] is not None and not isinstance(view["sorters"], list):
        errs.append(f"{path}.sorters must be an array.")
    return errs


def _string_list(val: Any) -> bool:
    return isinstance(val, list) and all(isinstance(x, str) for x in val)


def json_assignments_in_sql(sql: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _JSON_ASSIGN.finditer(sql or ""):
        out.append((m.group(1), m.group(2).replace("''", "'")))
    return out
