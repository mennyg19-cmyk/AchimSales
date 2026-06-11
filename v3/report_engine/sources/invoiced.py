"""Adapter: invoiced_order_charges SP rows -> InvoiceChargeFact.

The SP returns a flat per-invoice dump with separate charge columns. Field
names vary slightly across SP revisions, so we try documented variants in
order. Notably tariff is at the sales-LINE level (`SL_TariffCharges`); the
header-level `SH_TariffCharges` has been observed null, so SL is tried first.
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping

from report_engine.facts import InvoiceChargeFact
from report_engine.lib import first_of, iso_date, num, text

# Credit notes carry CRD / CM / FC anywhere in the invoice number (no row-type
# flag comes back from the SP). This is a SUBSTRING match, case-insensitive,
# matching LIVE exactly (reports/invoiced/aggregator.py:
# `InvoiceNumber.str.upper().str.contains("CRD|CM|FC")`) - NOT a prefix.
_CREDIT_RE = re.compile(r"CRD|CM|FC", re.IGNORECASE)


def is_credit_number(invoice_number: str) -> bool:
    return bool(invoice_number and _CREDIT_RE.search(invoice_number))


def to_fact(raw: Mapping) -> InvoiceChargeFact:
    subtotal = round(num(first_of(raw, "Amount", "SubTotal", "SubTotalAmount")), 2)
    tariff = round(num(first_of(raw, "SL_TariffCharges", "SH_TariffCharges",
                                "TariffCharges", "Tariff Charges")), 2)
    freight = round(num(first_of(raw, "SH_FreightCharges", "SL_FreightCharges",
                                 "FreightCharges", "Freight Charges")), 2)
    cc = round(num(first_of(raw, "SH_ProcessingFeesCharges", "SL_ProcessingFeesCharges",
                            "ProcessingFeesCharges", "CCCharges", "CC Charges")), 2)
    invoice_number = text(first_of(raw, "Invoice", "InvoiceNumber", "InvoiceNo"))
    return InvoiceChargeFact(
        source="reporting_api",
        invoice_number=invoice_number,
        invoice_date=iso_date(first_of(raw, "InvoiceDate", "Invoice Date", "DocumentDate")),
        customer_account=text(first_of(raw, "InvoiceAccount", "CustomerAccount",
                                       "customeraccount", "AccountNum")),
        customer_name=text(first_of(raw, "CustomerName", "customername", "Name")),
        sales_order_number=text(first_of(raw, "SalesOrder", "SalesOrderNumber", "SalesId")),
        subtotal=subtotal,
        tariff=tariff,
        freight=freight,
        cc=cc,
        total=round(subtotal + tariff + freight + cc, 2),
        sales_group=text(first_of(raw, "SalesGroup", "salesgroup", "Salesman")),
        is_credit=is_credit_number(invoice_number),
    )


def to_facts(rows: Iterable[Mapping]) -> list[InvoiceChargeFact]:
    return [to_fact(r) for r in rows]
