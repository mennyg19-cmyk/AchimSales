# === What's in this file ===
# Adapter: `invoiced_report` SP rows -> InvoiceChargeFact.
#
# to_fact() -- Maps one API row to a fact; trusts SQL totals and salesman labels.
# is_credit_number() -- Regex fallback when the SP does not send IsCredit.
# _commission_fraction() -- Reads the SP `commission` rate as a fraction (0.06).
# to_facts() -- Maps a list of raw rows.

"""Adapter: invoiced report SP rows -> InvoiceChargeFact."""

from __future__ import annotations

import re
from typing import Iterable, Mapping

from report_engine.facts import InvoiceChargeFact
from report_engine.lib import first_of, iso_date, map_release, num, text

# Credit notes carry CRD / CM / FC anywhere in the invoice number when SQL
# does not send IsCredit. Substring match, case-insensitive (matches LIVE).
_CREDIT_RE = re.compile(r"CRD|CM|FC", re.IGNORECASE)


def is_credit_number(invoice_number: str) -> bool:
    return bool(invoice_number and _CREDIT_RE.search(invoice_number))


def _is_credit(raw: Mapping, invoice_number: str) -> bool:
    flag = first_of(raw, "IsCredit", "is_credit", "IsCreditNote")
    if flag is not None and str(flag).strip() != "":
        return str(flag).strip().lower() in ("1", "true", "yes", "y")
    return is_credit_number(invoice_number)


def _sales_group_label(raw: Mapping) -> str:
    """SalesGroup from the invoiced endpoint; salesman / SalesmanName if that is blank."""
    group = text(first_of(raw, "SalesGroup"))
    if group:
        return group
    return text(first_of(raw, "salesman", "Salesman")) or text(first_of(raw, "SalesmanName"))


def _commission_fraction(raw: Mapping) -> float | None:
    """The salesman's commission rate from the SP, normalized to a fraction.

    The master stores rates as fractions (0.06 = 6%) and the live math does
    net * rate, so we keep that convention. A real rate is well under 100%, so
    if the SP ever sends a whole percent (6 instead of 0.06) we divide by 100 -
    that guard only fires above 1.0, so a genuine fraction passes through
    untouched. (See REVIEW-LOG: unit confirmed once a live call is captured.)
    """
    raw_pct = first_of(raw, "commission", "Commission", "CommissionPct", "Commission %")
    if raw_pct is None:
        return None
    pct = num(raw_pct)
    return pct / 100 if pct > 1 else pct


def to_fact(raw: Mapping) -> InvoiceChargeFact:
    invoice_number = text(first_of(raw, "InvoiceNumber", "Invoice"))
    subtotal = round(num(first_of(raw, "amount", "Amount")), 2)
    tariff = round(num(first_of(raw, "Tariff Charges", "TariffCharges",
                                "SL_TariffCharges", "SH_TariffCharges")), 2)
    freight = round(num(first_of(raw, "Freight Charges", "FreightCharges",
                                 "SH_FreightCharges", "SL_FreightCharges")), 2)
    cc = round(num(first_of(raw, "CC Charges", "CCCharges",
                            "SH_ProcessingFeesCharges", "SL_ProcessingFeesCharges")), 2)
    misc = round(num(first_of(raw, "Misc Charges", "MiscCharges")), 2)
    total_raw = first_of(raw, "Total Invoice", "TotalInvoice")
    if total_raw is not None and str(total_raw).strip() != "":
        total = round(num(total_raw), 2)
    else:
        total = round(subtotal + tariff + freight + cc + misc, 2)
    return InvoiceChargeFact(
        invoice_number=invoice_number,
        invoice_date=iso_date(first_of(raw, "InvoiceDate", "Invoice Date")),
        customer_account=text(first_of(raw, "CustomerAccount", "InvoiceAccount")),
        customer_name=text(first_of(raw, "CustomerName")),
        sales_order_number=text(first_of(raw, "salesorder", "SalesOrder")),
        subtotal=subtotal,
        tariff=tariff,
        freight=freight,
        cc=cc,
        misc=misc,
        total=total,
        sales_group=_sales_group_label(raw),
        salesman_name=text(first_of(raw, "SalesmanName")),
        is_credit=_is_credit(raw, invoice_number),
        commission_pct=_commission_fraction(raw),
    )


def to_facts(rows: Iterable[Mapping]) -> list[InvoiceChargeFact]:
    return map_release(rows, to_fact)
