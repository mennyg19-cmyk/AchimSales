"""Shapes a stored report snapshot into what the screen asks for."""

# === What's in this file ===
# The worker stores a finished report as one snapshot (all its tabs) in cache.db.
# The screen doesn't need all of it at once: first it asks "what tabs are there
# and which is active", then it asks for one tab's rows at a time. This serves
# both from the snapshot, so a big report doesn't ship every tab's rows on the
# first request.
#
# result_summary() -- the tab list, which tab to open first, and run info
# result_tab() -- one tab's columns + rows + totals (or None if no such tab)

from __future__ import annotations

from typing import Any, Optional


def result_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    tabs = snapshot.get("tabs", [])
    return {
        "report_key": snapshot.get("report_key"),
        "title": snapshot.get("title"),
        "generated_at": snapshot.get("generated_at"),
        "cached_at": snapshot.get("_cached_at"),
        "provisional": snapshot.get("provisional", True),
        "stale": snapshot.get("stale", False),
        "stale_reason": snapshot.get("stale_reason"),
        "row_count": snapshot.get("row_count"),
        "params": snapshot.get("params"),
        "tabs": [
            {
                "key": tab["key"],
                "label": tab["label"],
                "layout": tab.get("layout"),
                "row_count": len(tab.get("rows", [])),
            }
            for tab in tabs
        ],
        "active_tab": tabs[0]["key"] if tabs else None,
    }


def result_tab(snapshot: dict[str, Any], tab_key: str) -> Optional[dict[str, Any]]:
    for tab in snapshot.get("tabs", []):
        if tab["key"] == tab_key:
            # Return the whole tab payload (incl. any layout-specific extras such
            # as the commission cards' per-salesman blocks). It's already built
            # JSON-safe by the engine.
            return dict(tab)
    return None
