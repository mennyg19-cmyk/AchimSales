"""Salesman and customer dropdowns. Live masters when keyed; last-good sqlite; else catalog."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import catalog
import doorway
import params
from db import db

TTL_S = 3600
MASTER_TIMEOUT_S = 30


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_s(updated_at: str) -> float:
    try:
        stamp = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return TTL_S + 1
    return (datetime.now(timezone.utc) - stamp).total_seconds()


def _load(cache_key: str) -> list | None:
    with db() as conn:
        row = conn.execute(
            "SELECT payload_json, updated_at FROM lookup_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if row is None:
        return None
    try:
        data = json.loads(row["payload_json"])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    return data


def _save(cache_key: str, rows: list) -> None:
    with db() as conn:
        conn.execute(
            """INSERT INTO lookup_cache (cache_key, payload_json, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(cache_key) DO UPDATE SET
                 payload_json = excluded.payload_json,
                 updated_at = excluded.updated_at""",
            (cache_key, json.dumps(rows), _now()),
        )


def _fresh(cache_key: str) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT updated_at FROM lookup_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    return bool(row) and _age_s(row["updated_at"]) <= TTL_S


def _cell(row: dict, *names) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value).strip()
    lower = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = lower.get(name.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _refresh_salesmen() -> None:
    result = doorway.run_report(params.SALESMEN_MASTER, {}, timeout=MASTER_TIMEOUT_S)
    rows = []
    for raw in result.rows:
        if not isinstance(raw, dict):
            continue
        key = _cell(raw, "Salesman", "SalesGroup", "SalesGroupId")
        if not key:
            continue
        active = _cell(raw, "IsActive", "Active").lower()
        if active in {"0", "false", "no", "n"}:
            continue
        rows.append(
            {
                "key": key,
                "name": _cell(raw, "SalesmanName", "Name") or key,
            }
        )
    if rows:
        _save("salesmen", rows)


def _refresh_customers() -> None:
    result = doorway.run_report(params.CUSTOMER_MASTER, {}, timeout=MASTER_TIMEOUT_S)
    rows = []
    for raw in result.rows:
        if not isinstance(raw, dict):
            continue
        account = _cell(raw, "CustomerAccount", "Customer Account", "account")
        if not account:
            continue
        rows.append(
            {
                "account": account,
                "name": _cell(raw, "CustomerName", "Customer Name", "name") or account,
                "salesman": _cell(raw, "SalesGroup", "Salesman", "salesman"),
            }
        )
    if rows:
        _save("customers", rows)


def refresh_if_stale() -> None:
    if not doorway.configured():
        return
    try:
        if not _fresh("salesmen"):
            _refresh_salesmen()
    except doorway.DoorwayError:
        pass
    try:
        if not _fresh("customers"):
            _refresh_customers()
    except doorway.DoorwayError:
        pass


def salesmen() -> list[dict]:
    refresh_if_stale()
    cached = _load("salesmen")
    return cached if cached else [dict(row) for row in catalog.SALESMEN]


def customers(salesman: str = "") -> list[dict]:
    refresh_if_stale()
    cached = _load("customers")
    rows = cached if cached else [dict(row) for row in catalog.CUSTOMERS]
    wanted = (salesman or "").strip()
    if wanted:
        rows = [row for row in rows if row.get("salesman") == wanted]
    return rows


def customer(account: str) -> dict | None:
    acct = (account or "").strip()
    if not acct:
        return None
    for row in customers():
        if row.get("account") == acct:
            return row
    return None
