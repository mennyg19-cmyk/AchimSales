"""Customer Transaction Detail: original CustTrans + settlements + offset.

Source: catalog ``customertransactiondetail`` (rpt.usp_customertransactiondetail).
One original transaction can appear more than once when it has multiple
settlements. This builder does not deduplicate and does no math.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from report_engine.lib import first_of, iso_date, num, text

_COLS = [
    {"field": "Company", "header": "Company", "type": "text"},
    {"field": "AccountNum", "header": "Account", "type": "text"},
    {"field": "Invoice", "header": "Invoice", "type": "text"},
    {"field": "AmountMST", "header": "Amount", "type": "money", "sum": False},
    {"field": "RemainAmountCur", "header": "Remaining", "type": "money", "sum": False},
    {"field": "Voucher", "header": "Voucher", "type": "text"},
    {"field": "RecId", "header": "RecId", "type": "text"},
    {"field": "CreatedDateTime", "header": "Created", "type": "date"},
    {"field": "TransType", "header": "Type", "type": "text"},
    {"field": "OffsetTransVoucher", "header": "Offset voucher", "type": "text"},
    {"field": "SettleAmountCur", "header": "Settle amount", "type": "money"},
    {"field": "OffsetRecId", "header": "Offset RecId", "type": "text"},
    {"field": "OffsetAmountMST", "header": "Offset amount", "type": "money"},
    {"field": "OffsetVoucher", "header": "Offset trans voucher", "type": "text"},
    {"field": "OffsetCreatedDateTime", "header": "Offset created", "type": "date"},
    {"field": "OffsetCreatedBy", "header": "Offset created by", "type": "text"},
]


def _cell(row: dict, *names: str):
    return first_of(row, *names)


def _money(row: dict, *names: str):
    raw = _cell(row, *names)
    if raw is None or str(raw).strip() == "":
        return ""
    return round(num(raw), 2)


def clean_rows(rows: Iterable[dict]) -> list[dict]:
    """Keep every SP row. Multiple settlements against one RecId stay multiple rows."""
    out: list[dict] = []
    for row in rows:
        out.append({
            "Company": text(_cell(row, "Company")),
            "AccountNum": text(_cell(row, "AccountNum", "CustomerAccount", "Account")),
            "Invoice": text(_cell(row, "Invoice", "InvoiceNumber")),
            "AmountMST": _money(row, "AmountMST", "Amount"),
            "RemainAmountCur": _money(row, "RemainAmountCur", "RemainAmount"),
            "Voucher": text(_cell(row, "Voucher")),
            "RecId": text(_cell(row, "RecId")),
            "CreatedDateTime": iso_date(_cell(row, "CreatedDateTime")),
            "TransType": text(_cell(row, "TransType")),
            "OffsetTransVoucher": text(_cell(row, "OffsetTransVoucher")),
            "SettleAmountCur": _money(row, "SettleAmountCur"),
            "OffsetRecId": text(_cell(row, "OffsetRecId")),
            "OffsetAmountMST": _money(row, "OffsetAmountMST"),
            "OffsetVoucher": text(_cell(row, "OffsetVoucher")),
            "OffsetCreatedDateTime": iso_date(_cell(row, "OffsetCreatedDateTime")),
            "OffsetCreatedBy": text(_cell(row, "OffsetCreatedBy")),
        })
    return out


def build(rows: Sequence[dict]) -> list[dict]:
    return [{
        "key": "transactions",
        "name": "Transactions",
        "columns": _COLS,
        "rows": list(rows),
    }]
