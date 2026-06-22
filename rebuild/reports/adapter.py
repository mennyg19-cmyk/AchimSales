"""Cleans raw stored-procedure rows into canonical, typed report rows."""

# === What's in this file ===
# The bridge between "whatever the SP sent" and "the clean rows the engine
# groups and totals". It renames each column to its canonical name and cleans
# the value to the right type, using the per-report manifest. It also fills the
# two values LIVE derives when the SP leaves them blank: whether a row is a
# credit, and the invoice total. These two derivations mirror the live app and
# are the ONLY logic here -- everything else is a rename/clean.
#
# normalize() -- raw SP rows -> list of canonical, typed dict rows

from __future__ import annotations

from typing import Iterable, Mapping

from .lib import first_present, iso_date, is_credit_number, money, num, parse_bool, text
from .manifests import FieldSpec, manifest_for

_MONEY_PARTS = ("SubTotal Invoices", "Tariff Charges", "Freight Charges", "CC Charges", "Misc Charges")


def _clean(value, spec: FieldSpec):
    if spec.type == "money":
        return money(value)
    if spec.type == "int":
        return int(num(value))
    if spec.type == "date":
        return iso_date(value)
    if spec.type == "rate":
        rate = num(value)
        if rate <= 0:
            return 0.0
        # The master stores rates as fractions (0.06 = 6%); if the SP ever sends
        # a whole percent (6) we divide by 100. Only fires above 1.0.
        return rate / 100 if rate > 1 else rate
    if spec.type == "bool":
        return parse_bool(value)
    return text(value)


def normalize(report_key: str, raw_rows: Iterable[Mapping]) -> list[dict]:
    specs = manifest_for(report_key)
    out: list[dict] = []
    for raw in raw_rows:
        row = {spec.key: _clean(first_present(raw, spec.aliases), spec) for spec in specs}

        # LIVE fallback 1: derive the credit flag from the invoice number when
        # the SP didn't send IsCredit.
        if row.get("IsCredit") is None:
            row["IsCredit"] = is_credit_number(row.get("InvoiceNumber", ""))

        # LIVE fallback 2: if Total Invoice came back blank, sum the parts.
        if not row.get("Total Invoice"):
            row["Total Invoice"] = round(sum(num(row.get(p)) for p in _MONEY_PARTS), 2)

        out.append(row)
    return out
