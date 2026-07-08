"""Seeds the report definitions into the database."""

# === What's in this file ===
# A report is defined by config rows, not code. This writes each report's
# definition: its stored procedure, its filters, its canonical columns, and its
# tabs (column layout + grouping). Re-running is safe -- it replaces the rows
# each time. Numbers are PROVISIONAL until the owner signs off.
#
# _seed_invoiced() -- the invoiced report definition
# _seed_ordered() -- the ordered report definition
# _seed_number_4() -- the Number 4 rolling-12 report definition
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


_ORD_COLUMNS = [
    {"column_key": "SalesOrderNumber", "label": "Sales Order", "data_type": _TEXT},
    {"column_key": "CustomerAccount", "label": "Customer Account", "data_type": _TEXT},
    {"column_key": "CustomerName", "label": "Customer Name", "data_type": _TEXT},
    {"column_key": "CreatedDateTime", "label": "Created Date", "data_type": _DATE},
    {"column_key": "LineNumber", "label": "Line #", "data_type": _INT},
    {"column_key": "Item", "label": "Item", "data_type": _TEXT},
    {"column_key": "ItemDescription", "label": "Description", "data_type": _TEXT},
    {"column_key": "SalesPrice", "label": "Sales Price", "data_type": _MONEY},
    {"column_key": "SalesStatus", "label": "Status", "data_type": _TEXT},
    {"column_key": "QuantityOrdered", "label": "Qty Ordered", "data_type": _INT},
    {"column_key": "QuantityReserved", "label": "Qty Reserved", "data_type": _INT},
    {"column_key": "ReleasedQuantity", "label": "Qty Released", "data_type": _INT},
    {"column_key": "DeliveryRemainder", "label": "Delivery Remainder", "data_type": _INT},
    {"column_key": "CancelledQTY", "label": "Cancelled Qty", "data_type": _INT},
    {"column_key": "Ordered $", "label": "Ordered $", "data_type": _MONEY},
    {"column_key": "Shipped $", "label": "Shipped $", "data_type": _MONEY},
    {"column_key": "Cancelled $", "label": "Cancelled $", "data_type": _MONEY},
    {"column_key": "SalesGroup", "label": "Sales Group", "data_type": _TEXT},
    {"column_key": "SalesmanName", "label": "Salesman", "data_type": _TEXT},
    {"column_key": "Commission", "label": "Commission %", "data_type": _MONEY},
]

_ORD_FULL_COLS = [
    _col("SalesOrderNumber"), _col("CustomerAccount"), _col("CustomerName"),
    _col("CreatedDateTime", _DATE), _col("LineNumber", _INT),
    _col("Item"), _col("ItemDescription"), _col("SalesPrice", _MONEY),
    _col("SalesStatus"),
    _col("QuantityOrdered", _INT), _col("QuantityReserved", _INT),
    _col("ReleasedQuantity", _INT), _col("DeliveryRemainder", _INT), _col("CancelledQTY", _INT),
    _col("Ordered $", _MONEY), _col("Shipped $", _MONEY), _col("Cancelled $", _MONEY),
    _col("SalesGroup"), _col("SalesmanName"), _col("Commission", _MONEY, "Commission %"),
]

_ORD_OPEN_COLS = [
    _col("SalesOrderNumber"), _col("CustomerAccount"), _col("CustomerName"),
    _col("CreatedDateTime", _DATE), _col("Item"), _col("ItemDescription"),
    _col("QuantityOrdered", _INT), _col("DeliveryRemainder", _INT),
    _col("Ordered $", _MONEY), _col("Shipped $", _MONEY),
    _col("SalesGroup"), _col("SalesmanName"),
]

_ORD_CUST_SUMMARY_COLS = [
    _col("CustomerAccount"), _col("CustomerName"),
    _col("OrderCount", _INT, "Orders"),
    _col("TotalOrdered", _MONEY, "Total Ordered $"),
    _col("TotalShipped", _MONEY, "Total Shipped $"),
    _col("TotalCancelled", _MONEY, "Total Cancelled $"),
]

_ORD_SALESMAN_COLS = [
    _col("SalesGroup"), _col("SalesmanName"),
    _col("OrderCount", _INT, "Orders"),
    _col("TotalOrdered", _MONEY, "Total Ordered $"),
    _col("TotalShipped", _MONEY, "Total Shipped $"),
    _col("TotalCancelled", _MONEY, "Total Cancelled $"),
]

_ORD_CUST_AGG = {
    "OrderCount": "count_distinct:SalesOrderNumber",
    "TotalOrdered": "sum:Ordered $",
    "TotalShipped": "sum:Shipped $",
    "TotalCancelled": "sum:Cancelled $",
}

_ORD_SALESMAN_AGG = {
    "OrderCount": "count_distinct:SalesOrderNumber",
    "TotalOrdered": "sum:Ordered $",
    "TotalShipped": "sum:Shipped $",
    "TotalCancelled": "sum:Cancelled $",
}

_ORD_TABS = [
    {
        "tab_key": "full_data", "label": "Full Details",
        "column_keys": _ORD_FULL_COLS,
        "sorters": [{"field": "CreatedDateTime", "dir": "desc"}, {"field": "SalesOrderNumber", "dir": "asc"}, {"field": "LineNumber", "dir": "asc"}],
    },
    {
        "tab_key": "summary_by_customer", "label": "Summary by Customer",
        "group_by": ["CustomerAccount", "CustomerName"],
        "aggregations": _ORD_CUST_AGG, "column_keys": _ORD_CUST_SUMMARY_COLS,
        "sorters": [{"field": "CustomerAccount", "dir": "asc"}],
    },
    {
        "tab_key": "open_orders", "label": "Open Orders",
        "filter_expr": '{"op":"eq","field":"SalesStatus","value":"Open order"}',
        "column_keys": _ORD_OPEN_COLS,
        "sorters": [{"field": "CreatedDateTime", "dir": "desc"}, {"field": "SalesOrderNumber", "dir": "asc"}],
    },
    {
        "tab_key": "totals_by_salesman", "label": "Totals by Salesman",
        "condition": "has_multiple_sales_groups",
        "group_by": ["SalesGroup", "SalesmanName"],
        "aggregations": _ORD_SALESMAN_AGG, "column_keys": _ORD_SALESMAN_COLS,
        "sorters": [{"field": "SalesGroup", "dir": "asc"}],
    },
]

_ORD_FILTERS = [
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
    {"filter_key": "SalesOrderNumber", "label": "Sales order number", "kind": "text"},
    {"filter_key": "CustomerAccount", "label": "Customer account", "kind": "text"},
    {"filter_key": "Item", "label": "Item", "kind": "text"},
    {"filter_key": "SalesStatus", "label": "Sales status", "kind": "text"},
    {"filter_key": "salesman", "label": "Sales group", "kind": "text"},
]


# Number 4: one report, one question -- By Customer, By Item, or Both. Each
# view is its own stored procedure; "Both" runs both and shows two tabs. Month
# columns are dynamic (they move with today's date), so no fixed column list or
# tab recipes here: reports/rolling12.py builds the snapshot, and the columns
# below are only the fixed leading/trailing ones, kept as documentation for the
# admin screens.
_N4_FILTERS = [
    {
        "filter_key": "mode", "label": "View", "kind": "select", "default_value": "both",
        "options": [
            {"value": "both", "label": "Both"},
            {"value": "by_customer", "label": "By Customer"},
            {"value": "by_item", "label": "By Item"},
        ],
    },
]

_N4_COLUMNS = [
    {"column_key": "Customer #", "label": "Customer #", "data_type": _TEXT},
    {"column_key": "Customer Name", "label": "Customer Name", "data_type": _TEXT},
    {"column_key": "Item #", "label": "Item #", "data_type": _TEXT},
    {"column_key": "Item Name", "label": "Item Name", "data_type": _TEXT},
    {"column_key": "Total Qty", "label": "Total Qty", "data_type": _INT},
    {"column_key": "Total $", "label": "Total $", "data_type": _MONEY},
    {"column_key": "Avg Price", "label": "Avg Price", "data_type": _MONEY},
    {"column_key": "Salesman", "label": "Salesman", "data_type": _TEXT},
    {"column_key": "Book Price", "label": "Book Price", "data_type": _MONEY},
]


def _seed_invoiced(repo: ReportConfigRepository) -> None:
    repo.upsert_config("invoiced", title="Invoiced", sp_name="invoiced_report", default_params={"period": "ytd"})
    repo.set_filters("invoiced", _FILTERS)
    repo.set_columns("invoiced", _COLUMNS)
    repo.set_tabs("invoiced", _TABS)


def _seed_ordered(repo: ReportConfigRepository) -> None:
    repo.upsert_config("ordered", title="Ordered", sp_name="ordered_report", default_params={"period": "ytd"})
    repo.set_filters("ordered", _ORD_FILTERS)
    repo.set_columns("ordered", _ORD_COLUMNS)
    repo.set_tabs("ordered", _ORD_TABS)


def _seed_number_4(repo: ReportConfigRepository) -> None:
    # sp_name is the By Customer SP for reference; reports/rolling12.py picks
    # the actual SP(s) from the mode filter.
    repo.upsert_config(
        "number_4", title="Number 4 (Rolling 12 Months)",
        sp_name="customer_item_sales_rolling_12", default_params={"mode": "both"},
    )
    repo.set_filters("number_4", _N4_FILTERS)
    repo.set_columns("number_4", _N4_COLUMNS)
    repo.set_tabs("number_4", [])


def seed_all(db: Database) -> None:
    repo = ReportConfigRepository(db)
    _seed_invoiced(repo)
    _seed_ordered(repo)
    _seed_number_4(repo)
