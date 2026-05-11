"""Shared JSON fixture helpers for local/mock report data."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"
_ORDERED_FIXTURE = _FIXTURE_DIR / "ordered_dump.json"


def load_ordered_rows() -> list[dict[str, Any]] | None:
    """Load the ordered-report dump used when the reporting API is unavailable."""
    if not _ORDERED_FIXTURE.exists():
        return None
    try:
        with _ORDERED_FIXTURE.open(encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not read ordered fixture %s: %s", _ORDERED_FIXTURE, exc)
    return None


def filter_ordered_rows(rows: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply obvious filters so fixture data roughly follows the requested view."""
    out = list(rows or [])
    status = params.get("status")
    if status:
        out = [r for r in out if (r.get("SalesStatus") or "").lower() == str(status).lower()]
    customers = params.get("customers") or params.get("customer_account")
    if customers:
        if isinstance(customers, str):
            customers = [customers]
        wanted = {str(c) for c in customers}
        out = [r for r in out if str(r.get("CustomerAccount")) in wanted]
    salesman = params.get("salesman") or params.get("sales_group")
    if salesman:
        if isinstance(salesman, str):
            salesman = [salesman]
        wanted_salesmen = {str(s).lower() for s in salesman}
        out = [r for r in out if str(r.get("SalesGroup") or "").lower() in wanted_salesmen]
    return out


def ordered_fixture_path() -> str:
    return str(_ORDERED_FIXTURE)
