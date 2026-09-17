"""Thin tabs from doorway rows. Do not port v3/report_engine."""

from __future__ import annotations

from collections import defaultdict

import catalog
import column_types
import dates
from doorway import ReportResult, rows_from_body


def _slug(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_") or "tab"


def _tab(name: str, rows: list, columns=None) -> dict:
    out = {"name": name, "rows": list(rows)}
    if columns:
        out["columns"] = list(columns)
    return out


def _is_credit(row: dict) -> bool:
    flag = catalog.cell(row, "IsCredit", "is_credit")
    if flag in (True, 1, "1", "true", "True", "Y", "yes"):
        return True
    if flag in (False, 0, "0", "false", "False", "N", "no", ""):
        amount = catalog.cell(row, "Total Invoice", "amount", "Sales", default=0)
        try:
            return float(amount) < 0
        except (TypeError, ValueError):
            return False
    return bool(flag)


def _amount(row: dict):
    raw = catalog.cell(row, "Total Invoice", "Open$", "Ordered$", "Sales", "amount", "YTD", default=0)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _group(rows: list[dict], *key_names: str, name_field: str = "") -> list[dict]:
    buckets: dict[str, dict] = {}
    for row in rows:
        key = str(catalog.cell(row, *key_names) or "")
        if not key:
            continue
        bucket = buckets.setdefault(
            key,
            {
                key_names[0]: key,
                "Count": 0,
                "Total": 0.0,
            },
        )
        label = catalog.cell(row, name_field) if name_field else ""
        if label and name_field not in bucket:
            bucket[name_field] = label
        bucket["Count"] += 1
        bucket["Total"] += _amount(row)
    return list(buckets.values())


def _tab_rows(tab) -> list:
    if isinstance(tab, list):
        return [row for row in tab if isinstance(row, dict)]
    if isinstance(tab, dict):
        found = rows_from_body(tab)
        if found:
            return found
        rows = tab.get("rows")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _tab_columns(tab) -> list:
    if not isinstance(tab, dict):
        return []
    columns = tab.get("columns")
    if isinstance(columns, list):
        return columns
    return []


def _tabs_dict(raw) -> dict:
    if isinstance(raw, dict):
        out = {}
        for key, tab in raw.items():
            if isinstance(tab, dict):
                rec = {"name": tab.get("name") or str(key), "rows": _tab_rows(tab)}
                columns = _tab_columns(tab)
                if columns:
                    rec["columns"] = columns
                out[str(key)] = rec
            elif isinstance(tab, list):
                out[str(key)] = {"name": str(key), "rows": _tab_rows(tab)}
        return out
    if isinstance(raw, list):
        out = {}
        for index, tab in enumerate(raw):
            if not isinstance(tab, dict):
                continue
            key = str(tab.get("key") or _slug(tab.get("name") or f"tab_{index}"))
            rec = {"name": tab.get("name") or key, "rows": _tab_rows(tab)}
            columns = _tab_columns(tab)
            if columns:
                rec["columns"] = columns
            out[key] = rec
        return out
    return {}


def _mock_field_map(key: str) -> tuple[list[str], dict[str, list[str]]]:
    builder = catalog._BUILDERS.get(key)
    if builder is None:
        return [], {}
    payload = builder()
    data = payload.get("data") if isinstance(payload, dict) else {}
    raw_keys = _keys_in_order(data.get("raw") or [])
    tab_keys = {}
    for tab_key, tab in (data.get("tabs") or {}).items():
        if isinstance(tab, dict):
            tab_keys[str(tab_key)] = _keys_in_order(tab.get("rows") or [])
    return raw_keys, tab_keys


def _keys_in_order(rows, extra: list[str] | None = None) -> list[str]:
    seen: list[str] = []
    for key in extra or []:
        if key not in seen:
            seen.append(key)
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for key in row:
            if key not in seen:
                seen.append(key)
    return seen


def _pad_row(row: dict, keys: list[str]) -> dict:
    out = {}
    for key in keys:
        if key in row and row[key] is not None:
            out[key] = row[key]
        else:
            out[key] = ""
    return out


def _pad_rows(rows, keys: list[str]) -> list[dict]:
    return [_pad_row(row, keys) for row in rows or [] if isinstance(row, dict)]


def _pad_tabs(key: str, tabs: dict, raw: list) -> tuple[dict, list]:
    raw_schema, tab_schema = _mock_field_map(key)
    padded_tabs = {}
    for tab_key, tab in (tabs or {}).items():
        rows = tab.get("rows") if isinstance(tab, dict) else []
        if not isinstance(rows, list):
            rows = []
        keys = _keys_in_order(rows, extra=tab_schema.get(str(tab_key)) or [])
        rec = {
            "name": (tab.get("name") if isinstance(tab, dict) else None) or str(tab_key),
            "rows": _pad_rows(rows, keys),
        }
        columns = _tab_columns(tab) if isinstance(tab, dict) else []
        if columns:
            rec["columns"] = columns
        padded_tabs[str(tab_key)] = rec
    raw_list = [row for row in raw or [] if isinstance(row, dict)]
    if not raw_list:
        for tab in padded_tabs.values():
            raw_list.extend(tab.get("rows") or [])
    raw_keys = _keys_in_order(raw_list, extra=raw_schema)
    return padded_tabs, _pad_rows(raw_list, raw_keys)


def stamp_columns(payload: dict) -> dict:
    """Attach typed columns to each tab. Grid + Excel both read this."""
    if not isinstance(payload, dict):
        return payload
    data = payload.get("data")
    if not isinstance(data, dict):
        return payload
    key = str(data.get("report_key") or "")
    tabs = data.get("tabs")
    if not isinstance(tabs, dict):
        return payload
    for tab in tabs.values():
        if not isinstance(tab, dict):
            continue
        rows = tab.get("rows") if isinstance(tab.get("rows"), list) else []
        incoming = tab.get("columns") if isinstance(tab.get("columns"), list) else []
        fields = _keys_in_order(rows)
        if not fields and incoming:
            fields = [
                str(col.get("field") or col.get("name") or col)
                if isinstance(col, dict)
                else str(col)
                for col in incoming
            ]
        tab["columns"] = column_types.columns_for(
            fields, incoming=incoming, rows=rows, report_key=key
        )
        date_fields = [col["field"] for col in tab["columns"] if col.get("type") == "date"]
        if date_fields:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for field in date_fields:
                    if field in row:
                        row[field] = dates.iso_date(row[field])
        if key == "customer_transaction_detail":
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for field in ("CreatedDateTime", "OffsetCreatedDateTime"):
                    if field in row:
                        row[field] = dates.eastern_datetime(row[field])
    return payload


def wrap(key: str, tabs: dict, raw: list, *, source: str = "reporting_api") -> dict:
    spec = catalog.spec(key)
    title = spec["title"] if spec else key
    tabs, raw = _pad_tabs(key, tabs, raw)
    return stamp_columns(
        {
            "data": {
                "report_key": key,
                "title": title,
                "raw": raw,
                "tabs": tabs,
                "source": source,
            }
        }
    )


def from_result(key: str, result: ReportResult) -> dict:
    body = result.body if isinstance(result.body, dict) else {}
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    tabs = _tabs_dict(data.get("tabs") or body.get("tabs"))
    raw = result.rows if isinstance(result.rows, list) else []
    if not raw:
        raw = rows_from_body(body)
    if not tabs:
        tabs = thin_tabs(key, raw)
    return wrap(key, tabs, raw)


def thin_tabs(key: str, rows: list[dict]) -> dict:
    rows = [row for row in rows if isinstance(row, dict)]
    builders = {
        "invoiced": _invoiced,
        "ordered": _ordered,
        "salesman": _salesman,
        "number_4": _number_4_customer,
        "item_averages": _item_averages,
        "customer_activity": _customer_activity,
        "sales_by_state": _sales_by_state_summary,
        "customer_last_order": lambda data: {"lines": _tab("Lines", data)},
        "customer_transaction_detail": _customer_transaction_detail,
    }
    builder = builders.get(key)
    if builder is None:
        return {"rows": _tab("Rows", rows)}
    return builder(rows)


def _invoiced(rows: list[dict]) -> dict:
    credits = [row for row in rows if _is_credit(row)]
    invoices = [row for row in rows if not _is_credit(row)]
    tabs = {
        "summary_by_customer": _tab(
            "Summary by Customer",
            _group(rows, "CustomerAccount", "Customer Account", name_field="CustomerName"),
        ),
        "full_details": _tab("Full Details", rows),
        "credits": _tab("Credits", credits),
        "invoices": _tab("Invoices", invoices),
        "audit_reversals": _tab("Audit - Reversals", credits),
        "totals_by_salesman": _tab(
            "Totals by Salesman",
            _group(rows, "Salesman", "SalesGroup", name_field="SalesmanName"),
        ),
    }
    commission_rows = [
        row
        for row in rows
        if catalog.cell(row, "CommissionDollars", "NetCommission", "Commission") not in ("", None)
    ]
    if commission_rows:
        tabs["commissions"] = _tab("Commissions", commission_rows)
    return tabs


def _ordered(rows: list[dict]) -> dict:
    tabs = {
        "summary": _tab(
            "Summary",
            _group(rows, "CustomerAccount", "Customer Account", name_field="CustomerName"),
        ),
        "by_customer": _tab("By Customer", rows),
        "by_order": _tab("By Order", rows),
        "by_salesman": _tab("By Salesman", _group(rows, "Salesman", "SalesGroup")),
        "full_data": _tab("Full Data", rows),
    }
    if any(catalog.cell(row, "Item #", "Item", "ItemId") for row in rows):
        tabs["by_item"] = _tab(
            "By Item",
            _group(rows, "Item #", "Item", "ItemId", name_field="Item Name"),
        )
    return tabs


def _salesman(rows: list[dict]) -> dict:
    return {
        "yoy": _tab("Year over Year", rows),
        "ytd": _tab("YTD", rows),
    }


def _number_4_customer(rows: list[dict]) -> dict:
    return {
        "by_customer": _tab("By Customer", rows),
        "by_customer_ytd": _tab("By Customer YTD", rows),
    }


def _number_4_item(rows: list[dict]) -> dict:
    return {
        "by_item": _tab("By Item", rows),
        "by_item_ytd": _tab("By Item YTD", rows),
    }


def _item_averages(rows: list[dict]) -> dict:
    return {"items": _tab("Item Averages", rows)}


def _customer_activity(rows: list[dict]) -> dict:
    tabs = {"all": _tab("All", rows)}
    grouped: dict[str, list] = defaultdict(list)
    unassigned = []
    for row in rows:
        salesman = str(catalog.cell(row, "Salesman", "SalesGroup") or "")
        if not salesman:
            unassigned.append(row)
            continue
        grouped[salesman].append(row)
    for salesman, bucket in grouped.items():
        tabs[_slug(salesman)] = _tab(salesman, bucket)
    if unassigned:
        tabs["unassigned"] = _tab("Unassigned", unassigned)
    return tabs


def _sales_by_state_summary(rows: list[dict]) -> dict:
    return {"summary": _tab("Summary", rows)}


def _ctd_text(row: dict, *names: str) -> str:
    value = catalog.cell(row, *names, default="")
    return "" if value in (None, "") else str(value)


def _ctd_money(row: dict, *names: str):
    raw = catalog.cell(row, *names, default="")
    if raw in (None, ""):
        return ""
    try:
        return round(float(raw), 2)
    except (TypeError, ValueError):
        return ""


def _customer_transaction_detail(rows: list[dict]) -> dict:
    cleaned = []
    for row in rows:
        cleaned.append(
            {
                "Company": _ctd_text(row, "Company"),
                "AccountNum": _ctd_text(row, "AccountNum", "CustomerAccount", "Account"),
                "Invoice": _ctd_text(row, "Invoice", "InvoiceNumber"),
                "AmountMST": _ctd_money(row, "AmountMST", "Amount"),
                "RemainAmountCur": _ctd_money(row, "RemainAmountCur", "RemainAmount"),
                "Voucher": _ctd_text(row, "Voucher"),
                "RecId": _ctd_text(row, "RecId"),
                "CreatedDateTime": dates.eastern_datetime(_ctd_text(row, "CreatedDateTime")),
                "TransType": _ctd_text(row, "TransType"),
                "OffsetTransVoucher": _ctd_text(row, "OffsetTransVoucher"),
                "SettleAmountCur": _ctd_money(row, "SettleAmountCur"),
                "OffsetRecId": _ctd_text(row, "OffsetRecId"),
                "OffsetAmountMST": _ctd_money(row, "OffsetAmountMST"),
                "OffsetVoucher": _ctd_text(row, "OffsetVoucher"),
                "OffsetCreatedDateTime": dates.eastern_datetime(_ctd_text(row, "OffsetCreatedDateTime")),
                "OffsetCreatedBy": _ctd_text(row, "OffsetCreatedBy"),
            }
        )
    return {
        "transactions": _tab("Transactions", cleaned, catalog.CTD_COLUMNS),
    }


def number_4_tabs(customer_rows: list[dict], item_rows: list[dict]) -> dict:
    tabs = {}
    if customer_rows:
        tabs.update(_number_4_customer(customer_rows))
    if item_rows:
        tabs.update(_number_4_item(item_rows))
    return tabs or {"by_customer": _tab("By Customer", [])}


def sales_by_state_tabs(summary: list[dict], nyc: list[dict], detail: list[dict]) -> dict:
    return {
        "summary": _tab("Summary", summary),
        "new_york_city": _tab("New York City", nyc),
        "detail": _tab("Detail", detail),
    }


def customer_from_rows(account: str, rows: list[dict]) -> dict:
    salesman = ""
    name = ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not salesman:
            salesman = str(catalog.cell(row, "Salesman", "SalesGroup") or "")
        if not name:
            name = str(catalog.cell(row, "Customer Name", "CustomerName", "Customer") or "")
        if salesman and name:
            break
    return {"account": account, "name": name or account, "salesman": salesman}


def last_order_view(
    account: str,
    rows: list[dict],
    customer: dict,
    recent_invoices: list[dict],
    recent_error: str = "",
) -> dict:
    """Newest Order Rank (or first order number) plus its lines. No ADDON rollup."""
    rows = [row for row in rows if isinstance(row, dict)]
    by_rank: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        raw_rank = catalog.cell(row, "Order Rank", "OrderRank", default=1)
        try:
            rank = int(float(raw_rank))
        except (TypeError, ValueError):
            rank = 1
        by_rank[rank].append(row)
    chosen = by_rank[min(by_rank)] if by_rank else []
    first = chosen[0] if chosen else {}
    lines = []
    for row in chosen:
        qty = catalog.cell(row, "Qty Ordered", "QtyOrdered", "Qty", default=0)
        price = catalog.cell(row, "Sales Price", "SalesPrice", "Price", default=0)
        amount = catalog.cell(row, "Total", "Amount", default="")
        if amount in ("", None):
            try:
                amount = round(float(qty or 0) * float(price or 0), 2)
            except (TypeError, ValueError):
                amount = 0
        lines.append(
            {
                "Item #": catalog.cell(row, "Item #", "Item", "ItemId"),
                "Description": catalog.cell(row, "Description", "Item Name", "ItemName"),
                "Qty": qty,
                "Price": price,
                "Amount": amount,
            }
        )
    return {
        "customer": customer,
        "primary": {
            "order_number": catalog.cell(
                first, "Sales Order Number", "SalesOrderNumber", "order_number"
            ),
            "order_date": str(
                catalog.cell(first, "Order Date", "OrderDate", "order_date")
            )[:10],
            "salesman": customer.get("salesman")
            or catalog.cell(first, "Salesman", "SalesGroup"),
            "po": catalog.cell(first, "PO #", "PO#", "CustomerRequisition"),
        },
        "lines": lines,
        "recent_invoices": recent_invoices,
        "recent_error": recent_error,
        "source": "reporting_api",
        "account": account,
    }
