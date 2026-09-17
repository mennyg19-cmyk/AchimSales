"""Old-site report cell types. Specs from v3 report_engine; no engine port."""

from __future__ import annotations

import re

TYPES = ("text", "money", "percent", "int", "date")

# Folded field -> type. Aliases (InvoiceDate / Invoice Date) fold to the same key.
_KNOWN: dict[str, str] = {
    "invoicenumber": "text",
    "invoice": "text",
    "customeraccount": "text",
    "customeraccountnum": "text",
    "accountnum": "text",
    "cust": "text",
    "customername": "text",
    "customer": "text",
    "salesordernumber": "text",
    "salesordername": "text",
    "salesman": "text",
    "salesmanname": "text",
    "salesmannumber": "text",
    "sortnumber": "text",
    "salesgroup": "text",
    "purchid": "text",
    "po": "text",
    "item": "text",
    "itemname": "text",
    "itemnumber": "text",
    "linedescription": "text",
    "description": "text",
    "status": "text",
    "orderstatus": "text",
    "state": "text",
    "statecode": "text",
    "postalcode": "text",
    "shippedfrom": "text",
    "sourceaddress": "text",
    "deliveryaddress": "text",
    "recid": "text",
    "offsetrecid": "text",
    "voucher": "text",
    "offsetvoucher": "text",
    "offsettransvoucher": "text",
    "transtype": "text",
    "company": "text",
    "invoicedate": "date",
    "orderdate": "date",
    "expectedarrivaldate": "date",
    "shipdate": "date",
    "lastorderdate": "date",
    "invoicecount": "int",
    "linenumber": "int",
    "qtyordered": "int",
    "qtyreserved": "int",
    "qtyreleased": "int",
    "qtycancelled": "int",
    "qtylefttoship": "int",
    "qtytoship": "int",
    "qty": "int",
    "12monthqty": "int",
    "avgmonth": "int",
    "avgweek": "int",
    "totalqty": "int",
    "subtotalinvoices": "money",
    "tariffcharges": "money",
    "freightcharges": "money",
    "cccharges": "money",
    "misccharges": "money",
    "totalinvoice": "money",
    "totalinvoices": "money",
    "totaltariffcharges": "money",
    "totalfreightcharges": "money",
    "totalcccharges": "money",
    "totalmisccharges": "money",
    "commissionbase": "money",
    "commissions": "money",
    "commission": "money",
    "commissiondollars": "money",
    "netcommission": "money",
    "ytdcommission": "money",
    "unitprice": "money",
    "netprice": "money",
    "ordered": "money",
    "cancelled": "money",
    "released": "money",
    "shipping": "money",
    "open": "money",
    "extendedpriceordered": "money",
    "extendedpricecancelled": "money",
    "extendedpriceremainder": "money",
    "salesamount": "money",
    "newyorkcitysalesamount": "money",
    "amount": "money",
    "sales": "money",
    "price": "money",
    "total": "money",
    "ytd": "money",
    "avgprice": "money",
    "bookprice": "money",
    "percent": "percent",
    "commissionpct": "percent",
    "fulfillment": "percent",
}

_SALESMAN_TEXT = {
    "sortnumber",
    "salesman",
    "salesmanname",
    "salesmannumber",
    "cust",
    "customername",
    "customeraccount",
}

_MONEY_NAME = re.compile(
    r"total|amount|invoice|commission|charge|sales|price|open|ordered|released|cancelled|freight|tariff|ytd",
    re.I,
)
_COUNT_NAME = re.compile(r"count", re.I)
_MONTH_QTY = re.compile(r"(qty|quantity)\s*$", re.I)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def fold(name: str) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _sample_type(sample) -> str | None:
    if sample is None or sample == "":
        return None
    if isinstance(sample, bool):
        return "text"
    if isinstance(sample, (int, float)) and not isinstance(sample, bool):
        return "number"
    text = str(sample).strip()
    if _ISO_DATE.match(text):
        return "date"
    return "text"


def type_for(field: str, sample=None, report_key: str = "") -> str:
    header = str(field or "")
    folded = fold(header)
    known = _KNOWN.get(folded)
    if known:
        return known
    if "%" in header or "percent" in folded or folded.endswith("pct"):
        return "percent"
    if header.endswith("$"):
        return "money"
    if folded.endswith("qty") or folded.startswith("qty") or _MONTH_QTY.search(header):
        return "int"
    if _COUNT_NAME.search(header):
        return "int"
    if "date" in folded:
        return "date"
    if report_key == "salesman" and folded not in _SALESMAN_TEXT:
        return "percent" if "%" in header else "money"
    if re.search(r"this year|last year|year to date|jan thru|full year", header, re.I):
        return "percent" if "%" in header else "money"
    sample_kind = _sample_type(sample)
    if sample_kind == "date":
        return "date"
    if _MONEY_NAME.search(header) and not _COUNT_NAME.search(header):
        return "money"
    if sample_kind == "number":
        if isinstance(sample, float) and not float(sample).is_integer():
            return "money"
        return "int"
    return "text"


def salesman_band(field: str, col_index: int = -1, report_key: str = "") -> int | None:
    if report_key != "salesman":
        return None
    header = str(field or "")
    if fold(header) in _SALESMAN_TEXT:
        return None
    if re.search(r"full year|year to date", header, re.I) and "jan thru" not in header.lower():
        return 2
    if re.search(r"ytd|jan thru", header, re.I):
        return 1
    if re.search(r"this year|last year|sales ", header, re.I):
        return 0
    if col_index >= 4:
        return min((col_index - 4) // 4, 2)
    return None


def can_sum(field: str, col_type: str, report_key: str = "") -> bool:
    if col_type not in {"money", "int"}:
        return False
    folded = fold(field)
    if folded == "netprice":
        return False
    if report_key == "customer_transaction_detail" and folded in {"amountmst", "remainamountcur"}:
        return False
    return True


def _incoming_list(incoming) -> list[dict]:
    out = []
    for index, col in enumerate(incoming or []):
        if isinstance(col, str):
            out.append({"field": col, "header": col})
            continue
        if not isinstance(col, dict):
            continue
        field = col.get("field") or col.get("name") or col.get("Name") or col.get("header")
        if not field:
            field = f"col_{index}"
        rec = {
            "field": str(field),
            "header": str(col.get("header") or col.get("name") or field),
        }
        kind = col.get("type")
        if kind in TYPES:
            rec["type"] = kind
        if isinstance(col.get("band"), int):
            rec["band"] = col["band"]
        if col.get("sum") is False:
            rec["sum"] = False
        out.append(rec)
    return out


def _first_sample(rows: list, field: str):
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def columns_for(
    fields: list[str],
    *,
    incoming=None,
    rows: list | None = None,
    report_key: str = "",
) -> list[dict]:
    """Typed column specs for the grid and Excel writer."""
    by_field = {}
    order = []
    for col in _incoming_list(incoming):
        field = col["field"]
        if field not in by_field:
            order.append(field)
        by_field[field] = col
    for field in fields or []:
        if field not in by_field:
            order.append(field)
            by_field[field] = {"field": field, "header": field}
    out = []
    for index, field in enumerate(order):
        col = dict(by_field[field])
        kind = col.get("type") if col.get("type") in TYPES else type_for(
            field, _first_sample(rows or [], field), report_key
        )
        col["type"] = kind
        col.setdefault("header", field)
        if col.get("sum") is not False and not can_sum(field, kind, report_key):
            col["sum"] = False
        band = col.get("band")
        if not isinstance(band, int):
            inferred = salesman_band(field, index, report_key)
            if inferred is not None:
                col["band"] = inferred
        out.append(col)
    return out
