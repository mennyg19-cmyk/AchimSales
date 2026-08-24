"""Sales by State builder (pure).

Source: three Reporting API catalog keys from the DBA handoff:

  sales_by_state_summary
  sales_by_state_new_york_city
  sales_by_state_detail

Tabs match the sample workbook: Summary, New York City, Detail. The SP does
the classification; this module only renames columns, formats dates/money,
and sorts Summary by sales amount (largest first).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

from report_engine.lib import first_of, iso_date, num, text

SUMMARY_SP = "sales_by_state_summary"
NYC_SP = "sales_by_state_new_york_city"
DETAIL_SP = "sales_by_state_detail"

_SUMMARY_COLS = [
    {"field": "State", "header": "State", "type": "text"},
    {"field": "Sales amount", "header": "Sales amount", "type": "money"},
    {"field": "New York City Sales amount", "header": "New York City Sales amount", "type": "money"},
]
_NYC_COLS = [
    {"field": "Invoice", "header": "Invoice", "type": "text"},
    {"field": "Amount", "header": "Amount", "type": "money"},
    {"field": "Shipped_From", "header": "Shipped_From", "type": "text"},
    {"field": "Source_Address", "header": "Source_Address", "type": "text"},
    {"field": "Customer_Name", "header": "Customer_Name", "type": "text"},
    {"field": "State Code", "header": "State Code", "type": "text"},
    {"field": "State", "header": "State", "type": "text"},
    {"field": "Postal Code", "header": "Postal Code", "type": "text"},
]
_DETAIL_COLS = [
    {"field": "Invoice", "header": "Invoice", "type": "text"},
    {"field": "Invoice Date", "header": "Invoice Date", "type": "date"},
    {"field": "Customer Account", "header": "Customer Account", "type": "text"},
    {"field": "Customer Name", "header": "Customer Name", "type": "text"},
    {"field": "Amount", "header": "Amount", "type": "money"},
    {"field": "Shipped_From", "header": "Shipped_From", "type": "text"},
    {"field": "Source_Address", "header": "Source_Address", "type": "text"},
    {"field": "State Code", "header": "State Code", "type": "text"},
    {"field": "State", "header": "State", "type": "text"},
    {"field": "Postal Code", "header": "Postal Code", "type": "text"},
    {"field": "Delivery Address", "header": "Delivery Address", "type": "text"},
]


def _cell(row: Mapping, *names: str) -> Any:
    return first_of(row, *names)


def _money(row: Mapping, *names: str) -> float:
    return round(num(_cell(row, *names)), 2)


def _money_or_blank(row: Mapping, *names: str):
    raw = _cell(row, *names)
    if raw is None or str(raw).strip() == "":
        return ""
    return round(num(raw), 2)


def _invoice_date(value: Any) -> str:
    """SP datetime, ISO date, or Excel serial (the sample workbook used serials)."""
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)) and 20000 < float(value) < 80000:
        return (date(1899, 12, 30) + timedelta(days=int(value))).isoformat()
    s = str(value).strip()
    if s.replace(".", "", 1).isdigit():
        n = float(s)
        if 20000 < n < 80000:
            return (date(1899, 12, 30) + timedelta(days=int(n))).isoformat()
    return iso_date(value)


def clean_summary(rows: Iterable[Mapping]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        state = text(_cell(row, "State", "StateName", "state"))
        if not state:
            continue
        out.append({
            "State": state,
            "Sales amount": _money(row, "Sales amount", "SalesAmount", "Amount"),
            "New York City Sales amount": _money_or_blank(
                row, "New York City Sales amount", "NewYorkCitySalesAmount",
                "NYCSalesAmount", "NycSalesAmount"),
        })
    out.sort(key=lambda r: (-float(r["Sales amount"] or 0), r["State"]))
    return out


def clean_nyc(rows: Iterable[Mapping]) -> list[dict]:
    return [{
        "Invoice": text(_cell(row, "Invoice", "InvoiceNumber", "InvoiceId")),
        "Amount": _money(row, "Amount", "Sales amount", "SalesAmount"),
        "Shipped_From": text(_cell(row, "Shipped_From", "ShippedFrom")),
        "Source_Address": text(_cell(row, "Source_Address", "SourceAddress")),
        "Customer_Name": text(_cell(row, "Customer_Name", "CustomerName", "Customer Name")),
        "State Code": text(_cell(row, "State Code", "StateCode")),
        "State": text(_cell(row, "State", "StateName")),
        "Postal Code": text(_cell(row, "Postal Code", "PostalCode", "Zip", "ZipCode")),
    } for row in rows]


def clean_detail(rows: Iterable[Mapping]) -> list[dict]:
    return [{
        "Invoice": text(_cell(row, "Invoice", "InvoiceNumber", "InvoiceId")),
        "Invoice Date": _invoice_date(_cell(row, "Invoice Date", "InvoiceDate")),
        "Customer Account": text(_cell(
            row, "Customer Account", "CustomerAccount", "InvoiceAccount")),
        "Customer Name": text(_cell(row, "Customer Name", "CustomerName", "Customer_Name")),
        "Amount": _money(row, "Amount", "Sales amount", "SalesAmount"),
        "Shipped_From": text(_cell(row, "Shipped_From", "ShippedFrom")),
        "Source_Address": text(_cell(row, "Source_Address", "SourceAddress")),
        "State Code": text(_cell(row, "State Code", "StateCode")),
        "State": text(_cell(row, "State", "StateName")),
        "Postal Code": text(_cell(row, "Postal Code", "PostalCode", "Zip", "ZipCode")),
        "Delivery Address": text(_cell(
            row, "Delivery Address", "DeliveryAddress", "ShipToAddress")),
    } for row in rows]


def build(*, summary: Sequence[Mapping], nyc: Sequence[Mapping],
          detail: Sequence[Mapping]) -> list[dict]:
    return [
        {"key": "summary", "name": "Summary", "columns": _SUMMARY_COLS,
         "rows": clean_summary(summary)},
        {"key": "new_york_city", "name": "New York City", "columns": _NYC_COLS,
         "rows": clean_nyc(nyc)},
        {"key": "detail", "name": "Detail", "columns": _DETAIL_COLS,
         "rows": clean_detail(detail)},
    ]
