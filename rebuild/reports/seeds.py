"""Seeds the report definitions into the database (currently just invoiced)."""

# === What's in this file ===
# A report is defined by config rows, not code. This writes the invoiced
# report's definition: its stored procedure, its filters, its canonical columns,
# and its seven tabs (column layout + grouping match the LIVE export). Re-running
# it is safe -- it replaces the rows each time. Numbers are PROVISIONAL until the
# owner signs off (see run-state notes).
#
# seed_all() -- write every report's definition

from __future__ import annotations

from ..data.connection import Database
from ..data.repositories.report_configs import ReportConfigRepository

_TEXT = "text"
_MONEY = "money"
_DATE = "date"
_INT = "int"


def _col(field: str, type_: str = _TEXT, label: str | None = None) -> dict:
    return {"field": field, "label": label or field, "type": type_}


# The canonical column dictionary (LIVE export headers + types).
_COLUMNS = [
    {"column_key": "InvoiceNumber", "label": "InvoiceNumber", "data_type": _TEXT},
    {"column_key": "CustomerAccount", "label": "CustomerAccount", "data_type": _TEXT},
    {"column_key": "CustomerName", "label": "CustomerName", "data_type": _TEXT},
    {"column_key": "InvoiceDate", "label": "InvoiceDate", "data_type": _DATE},
    {"column_key": "SalesOrderNumber", "label": "SalesOrderNumber", "data_type": _TEXT},
    {"column_key": "Salesman", "label": "Salesman", "data_type": _TEXT},
    {"column_key": "SalesmanName", "label": "SalesmanName", "data_type": _TEXT},
    {"column_key": "SubTotal Invoices", "label": "SubTotal Invoices", "data_type": _MONEY},
    {"column_key": "Tariff Charges", "label": "Tariff Charges", "data_type": _MONEY},
    {"column_key": "Freight Charges", "label": "Freight Charges", "data_type": _MONEY},
    {"column_key": "CC Charges", "label": "CC Charges", "data_type": _MONEY},
    {"column_key": "Misc Charges", "label": "Misc Charges", "data_type": _MONEY},
    {"column_key": "Total Invoice", "label": "Total Invoice", "data_type": _MONEY},
]

# Column layouts per tab, in LIVE order.
_FULL_DETAILS_COLS = [
    _col("InvoiceNumber"), _col("CustomerAccount"), _col("CustomerName"), _col("InvoiceDate", _DATE),
    _col("SalesOrderNumber"), _col("Salesman"), _col("SalesmanName"),
    _col("SubTotal Invoices", _MONEY), _col("Tariff Charges", _MONEY), _col("Freight Charges", _MONEY),
    _col("CC Charges", _MONEY), _col("Misc Charges", _MONEY), _col("Total Invoice", _MONEY),
]

_INVOICE_COLS = [
    _col("CustomerAccount"), _col("CustomerName"), _col("InvoiceDate", _DATE), _col("InvoiceNumber"),
    _col("SalesOrderNumber"),
    _col("SubTotal Invoices", _MONEY), _col("Tariff Charges", _MONEY), _col("Freight Charges", _MONEY),
    _col("CC Charges", _MONEY), _col("Misc Charges", _MONEY), _col("Total Invoice", _MONEY),
    _col("Salesman"), _col("SalesmanName"),
]

_SUMMARY_COLS = [
    _col("CustomerAccount"), _col("CustomerName"), _col("Salesman"), _col("SalesmanName"),
    _col("InvoiceCount", _INT), _col("SubTotal Invoices", _MONEY),
    _col("Total Tariff Charges", _MONEY), _col("Total Freight Charges", _MONEY),
    _col("Total CC Charges", _MONEY), _col("Total Misc Charges", _MONEY), _col("Total Invoices", _MONEY),
]

_SALESMAN_TOTALS_COLS = [
    _col("Salesman"), _col("SalesmanName"), _col("InvoiceCount", _INT),
    _col("SubTotal Invoices", _MONEY), _col("Tariff Charges", _MONEY), _col("Freight Charges", _MONEY),
    _col("CC Charges", _MONEY), _col("Misc Charges", _MONEY), _col("Total Invoice", _MONEY),
]

_SUMMARY_AGG = {
    "InvoiceCount": "count_distinct:InvoiceNumber",
    "SubTotal Invoices": "sum:SubTotal Invoices",
    "Total Tariff Charges": "sum:Tariff Charges",
    "Total Freight Charges": "sum:Freight Charges",
    "Total CC Charges": "sum:CC Charges",
    "Total Misc Charges": "sum:Misc Charges",
    "Total Invoices": "sum:Total Invoice",
}

_SALESMAN_AGG = {
    "InvoiceCount": "count_distinct:InvoiceNumber",
    "SubTotal Invoices": "sum:SubTotal Invoices",
    "Tariff Charges": "sum:Tariff Charges",
    "Freight Charges": "sum:Freight Charges",
    "CC Charges": "sum:CC Charges",
    "Misc Charges": "sum:Misc Charges",
    "Total Invoice": "sum:Total Invoice",
}

_TABS = [
    {
        "tab_key": "summary_by_customer", "label": "Summary by Customer",
        "group_by": ["CustomerAccount", "CustomerName", "Salesman", "SalesmanName"],
        "aggregations": _SUMMARY_AGG, "column_keys": _SUMMARY_COLS,
        "sorters": [{"field": "CustomerAccount", "dir": "asc"}],
    },
    {
        "tab_key": "commissions", "label": "Commissions",
        "transform": "commission_monthly_pivot", "layout": "commission",
    },
    {
        "tab_key": "commissions_cards", "label": "Commissions (Cards)",
        "transform": "commission_cards", "layout": "commission_cards",
    },
    {
        "tab_key": "full_data", "label": "Full Details",
        "column_keys": _FULL_DETAILS_COLS,
        "sorters": [{"field": "CustomerAccount", "dir": "asc"}, {"field": "InvoiceNumber", "dir": "asc"}],
    },
    {
        "tab_key": "credits", "label": "Credits",
        "filter_expr": '{"op":"truthy","field":"IsCredit"}', "column_keys": _INVOICE_COLS,
        "sorters": [{"field": "CustomerAccount", "dir": "asc"}, {"field": "InvoiceNumber", "dir": "asc"}],
    },
    {
        "tab_key": "invoices", "label": "Invoices",
        "filter_expr": '{"op":"falsy","field":"IsCredit"}', "column_keys": _INVOICE_COLS,
        "sorters": [{"field": "CustomerAccount", "dir": "asc"}, {"field": "InvoiceNumber", "dir": "asc"}],
    },
    {
        "tab_key": "audit_reversals", "label": "Audit - Reversals",
        "condition": "has_reversals", "filter_expr": '{"op":"reversal"}', "column_keys": _INVOICE_COLS,
        "sorters": [{"field": "InvoiceNumber", "dir": "asc"}, {"field": "InvoiceDate", "dir": "asc"}],
    },
    {
        "tab_key": "totals_by_salesman", "label": "Totals by Salesman",
        "condition": "has_multiple_salesmen",
        "group_by": ["Salesman", "SalesmanName"], "aggregations": _SALESMAN_AGG,
        "column_keys": _SALESMAN_TOTALS_COLS,
        "sorters": [{"field": "Salesman", "dir": "asc"}],
    },
]

_FILTERS = [
    {
        "filter_key": "period", "label": "Period", "kind": "select", "default_value": "ytd",
        "options": [
            {"value": "ytd", "label": "Year to date"},
            {"value": "this_month", "label": "This month"},
            {"value": "last_month", "label": "Last month"},
            {"value": "this_year", "label": "This year"},
            {"value": "last_year", "label": "Last year"},
            {"value": "custom", "label": "Custom range"},
            {"value": "all_time", "label": "All time"},
        ],
    },
    {"filter_key": "start_date", "label": "Start date", "kind": "date"},
    {"filter_key": "end_date", "label": "End date", "kind": "date"},
    {"filter_key": "customers", "label": "Customer account", "kind": "text"},
    {"filter_key": "salesman", "label": "Salesman", "kind": "text"},
]


def seed_all(db: Database) -> None:
    repo = ReportConfigRepository(db)
    repo.upsert_config("invoiced", title="Invoiced", sp_name="invoiced_report", default_params={"period": "ytd"})
    repo.set_filters("invoiced", _FILTERS)
    repo.set_columns("invoiced", _COLUMNS)
    repo.set_tabs("invoiced", _TABS)
