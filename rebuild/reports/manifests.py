"""Maps each stored procedure's raw column names to our canonical column names."""

# === What's in this file ===
# Stored procedures don't always name a column the way the report wants to show
# it (and names drift over time). This is the contract: for each report, the
# canonical column the engine works with, every raw name the SP might send for
# it, and the type to clean it to. Adding a report means adding an entry here.
#
# FieldSpec -- one canonical column: its name, its aliases, its type
# MANIFESTS -- {report_key: [FieldSpec, ...]}
# manifest_for() -- look up a report's field list (raises if unknown)

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldSpec:
    key: str  # canonical name the engine and UI use
    aliases: tuple[str, ...]  # raw SP names that map to it (first match wins)
    type: str = "text"  # text | money | date | int | bool | rate


# Invoiced: the flat table behind the Monthly Invoiced Report. Aliases come from
# the live/test adapters; the canonical names match the LIVE export headers.
_INVOICED = [
    FieldSpec("InvoiceNumber", ("InvoiceNumber", "Invoice"), "text"),
    FieldSpec("InvoiceDate", ("InvoiceDate", "Invoice Date"), "date"),
    FieldSpec("CustomerAccount", ("CustomerAccount", "InvoiceAccount"), "text"),
    FieldSpec("CustomerName", ("CustomerName",), "text"),
    FieldSpec("SalesOrderNumber", ("SalesOrderNumber", "salesorder", "SalesOrder"), "text"),
    FieldSpec("Salesman", ("Salesman", "salesman", "SalesGroup"), "text"),
    FieldSpec("SalesmanName", ("SalesmanName",), "text"),
    FieldSpec("SubTotal Invoices", ("SubTotal Invoices", "SubTotalInvoices", "amount", "Amount"), "money"),
    FieldSpec("Tariff Charges", ("Tariff Charges", "TariffCharges", "SL_TariffCharges", "SH_TariffCharges"), "money"),
    FieldSpec("Freight Charges", ("Freight Charges", "FreightCharges", "SH_FreightCharges", "SL_FreightCharges"), "money"),
    FieldSpec("CC Charges", ("CC Charges", "CCCharges", "SH_ProcessingFeesCharges", "SL_ProcessingFeesCharges"), "money"),
    FieldSpec("Misc Charges", ("Misc Charges", "MiscCharges"), "money"),
    FieldSpec("Total Invoice", ("Total Invoice", "TotalInvoice"), "money"),
    FieldSpec("IsCredit", ("IsCredit", "is_credit", "IsCreditNote"), "bool"),
    FieldSpec("commission", ("commission", "Commission", "CommissionPct", "Commission %"), "rate"),
]

_ORDERED = [
    FieldSpec("SalesOrderNumber", ("SalesOrderNumber",), "text"),
    FieldSpec("CustomerAccount", ("CustomerAccount",), "text"),
    FieldSpec("CustomerName", ("customername", "CustomerName"), "text"),
    FieldSpec("CreatedDateTime", ("CreatedDateTime",), "date"),
    FieldSpec("LineNumber", ("LineNumber",), "int"),
    FieldSpec("Item", ("Item",), "text"),
    FieldSpec("ItemDescription", ("ItemDescription",), "text"),
    FieldSpec("SalesPrice", ("SalesPrice",), "money"),
    FieldSpec("SalesStatus", ("SalesStatus",), "text"),
    FieldSpec("QuantityOrdered", ("QuantityOrdered",), "int"),
    FieldSpec("QuantityReserved", ("QuantityReserved",), "int"),
    FieldSpec("ReleasedQuantity", ("ReleasedQuantity",), "int"),
    FieldSpec("DeliveryRemainder", ("DeliveryRemainder",), "int"),
    FieldSpec("CancelledQTY", ("CancelledQTY",), "int"),
    FieldSpec("Ordered $", ("Ordered $", "OrderedDollars"), "money"),
    FieldSpec("Shipped $", ("Shipped $", "ShippedDollars"), "money"),
    FieldSpec("Cancelled $", ("Cancelled $", "CancelledDollars"), "money"),
    FieldSpec("SalesGroup", ("SalesGroup",), "text"),
    FieldSpec("SalesmanName", ("SalesmanName",), "text"),
    FieldSpec("Commission", ("Commission",), "rate"),
]

MANIFESTS: dict[str, list[FieldSpec]] = {
    "invoiced": _INVOICED,
    "ordered": _ORDERED,
}


def manifest_for(report_key: str) -> list[FieldSpec]:
    spec = MANIFESTS.get(report_key)
    if spec is None:
        raise KeyError(f"No field manifest for report {report_key!r}")
    return spec
