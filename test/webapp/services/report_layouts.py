"""Shared report layout helpers.

Used by viewer exports, email-now, and schedule runs so tab handling is
consistent across delivery paths.
"""

from __future__ import annotations

from copy import deepcopy


def normalise_layouts(raw) -> tuple[dict, set[str]]:
    """Normalize client layout payload and extract hidden tabs."""
    out: dict[str, dict] = {}
    dropped: set[str] = set()
    if not isinstance(raw, dict):
        return out, dropped
    for tab_key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        k = str(tab_key)
        if entry.get("tab_hidden"):
            dropped.add(k)
            continue
        out[k] = {
            "order": list(entry.get("field_order") or entry.get("order") or []),
            "hidden": list(entry.get("hidden_fields") or entry.get("hidden") or []),
            "duplicate_of": entry.get("duplicate_of") or entry.get("source_tab_key"),
            "tab_name": (entry.get("tab_name") or "").strip() or None,
        }
    return out, dropped


def expand_duplicate_tabs(payload: dict, layouts: dict) -> tuple[dict, dict]:
    """Expand duplicate tabs described in layouts into the payload tabs list."""
    tabs = list((payload or {}).get("tabs") or [])
    if not tabs:
        return payload, layouts

    by_key = {str(t.get("key")): t for t in tabs}
    appended: list[dict] = []
    for key, entry in (layouts or {}).items():
        src = (entry or {}).get("duplicate_of")
        if not src or key in by_key:
            continue
        source_tab = by_key.get(str(src))
        if not source_tab:
            continue
        cloned = deepcopy(source_tab)
        cloned["key"] = str(key)
        if entry.get("tab_name"):
            cloned["name"] = entry["tab_name"]
        cloned["duplicate_of"] = str(src)
        by_key[str(key)] = cloned
        appended.append(cloned)

    if not appended:
        return payload, layouts

    out_payload = dict(payload or {})
    out_payload["tabs"] = tabs + appended
    return out_payload, layouts
