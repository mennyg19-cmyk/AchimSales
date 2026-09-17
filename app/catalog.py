"""Report cards, filters, and dummy {data: {raw, tabs}} payloads.

Live doorway is not called unless REPORTING_API_KEY is set. Tests never set it.
"""

from __future__ import annotations

from copy import deepcopy


def cell(row, *names, default="", strip=False):
    if not isinstance(row, dict):
        return default
    value = None
    found = False
    for name in names:
        if name in row and row[name] not in (None, ""):
            value = row[name]
            found = True
            break
    if not found:
        lower = {str(key).lower(): item for key, item in row.items()}
        for name in names:
            value = lower.get(name.lower())
            if value not in (None, ""):
                found = True
                break
    if not found:
        return default
    return str(value).strip() if strip else value


PERIOD_OPTIONS = (
    ("all_time", "All Time"),
    ("mtd", "Month to Date"),
    ("last_month", "Last Month"),
    ("ytd", "Year to Date"),
    ("this_week", "This Week"),
    ("last_7_days", "Last 7 Days"),
    ("daily", "Yesterday"),
    ("custom", "Custom Range"),
)
STATUS_OPTIONS = (
    ("", "All Statuses"),
    ("Open order", "Open"),
    ("Delivered", "Delivered"),
    ("Invoiced", "Invoiced"),
    ("Cancelled", "Cancelled"),
)
N4_MODE_OPTIONS = (
    ("both", "Both"),
    ("by_customer", "By Customer"),
    ("by_item", "By Item"),
)
YEAR_OPTIONS = ("2026", "2025", "2024")

SALESMEN = (
    {"key": "DDweck", "name": "Dweck, David"},
    {"key": "HKaufman", "name": "Kaufman, Herschel"},
)
CUSTOMERS = (
    {"account": "C-1001", "name": "HD SUPPLY", "salesman": "DDweck"},
    {"account": "C-1002", "name": "MAZER WHOLESALE", "salesman": "DDweck"},
    {"account": "C-2001", "name": "AMAZON.COM DEDC, LLC", "salesman": "HKaufman"},
)

REPORTS = (
    {
        "key": "ordered",
        "title": "Ordered",
        "in_app": False,
        "filters": ("period", "status", "customers", "salesman"),
        "privileged_only": False,
        "salesman_default": True,
    },
    {
        "key": "invoiced",
        "title": "Invoiced",
        "in_app": False,
        "filters": ("period", "customers", "salesman"),
        "privileged_only": False,
        "salesman_default": True,
    },
    {
        "key": "salesman",
        "title": "Salesman",
        "in_app": False,
        "filters": ("year", "salesman"),
        "privileged_only": False,
        "salesman_default": True,
    },
    {
        "key": "number_4",
        "title": "Number 4",
        "in_app": False,
        "filters": ("n4_mode",),
        "privileged_only": False,
        "salesman_default": True,
    },
    {
        "key": "customer_activity",
        "title": "Customer Activity",
        "in_app": False,
        "filters": ("salesman",),
        "privileged_only": False,
        "salesman_default": True,
    },
    {
        "key": "customer_last_order",
        "title": "Customer's Last Order",
        "in_app": True,
        "filters": (),
        "privileged_only": False,
        "salesman_default": True,
    },
    {
        "key": "item_averages",
        "title": "Item Averages",
        "in_app": False,
        "filters": (),
        "privileged_only": True,
        "salesman_default": False,
    },
    {
        "key": "sales_by_state",
        "title": "Sales by State",
        "in_app": False,
        "filters": ("year",),
        "privileged_only": False,
        "salesman_default": True,
    },
    {
        "key": "customer_transaction_detail",
        "title": "Customer Transaction Detail",
        "in_app": False,
        "filters": ("period", "customers", "invoice", "open_balance"),
        "privileged_only": False,
        "salesman_default": False,
    },
)

BACKLOG = (("customer_aging", "Customer Aging"),)


def spec(key: str) -> dict | None:
    return next((report for report in REPORTS if report["key"] == key), None)


def _payload(key: str, title: str, tabs: dict, raw: list | None = None) -> dict:
    return {
        "data": {
            "report_key": key,
            "title": title,
            "from_date": "2026-08-31",
            "to_date": "2026-09-06",
            "raw": raw if raw is not None else [],
            "tabs": tabs,
        }
    }


def invoiced_payload() -> dict:
    raw = [
        {
            "InvoiceNumber": "IN01008282",
            "CustomerAccount": "C-1001",
            "CustomerName": "HD SUPPLY",
            "InvoiceDate": "2026-09-02",
            "salesman": "DDweck",
            "SalesmanName": "Dweck, David",
            "amount": 1000.0,
            "Total Invoice": 1035.0,
            "IsCredit": False,
        },
        {
            "InvoiceNumber": "FCRD-004181",
            "CustomerAccount": "C-1002",
            "CustomerName": "MAZER WHOLESALE",
            "InvoiceDate": "2026-09-03",
            "salesman": "DDweck",
            "SalesmanName": "Dweck, David",
            "amount": -50.0,
            "Total Invoice": -50.0,
            "IsCredit": True,
        },
        {
            "InvoiceNumber": "IN01008290",
            "CustomerAccount": "C-2001",
            "CustomerName": "AMAZON.COM DEDC, LLC",
            "InvoiceDate": "2026-09-04",
            "salesman": "HKaufman",
            "SalesmanName": "Kaufman, Herschel",
            "amount": 500.0,
            "Total Invoice": 520.0,
            "IsCredit": False,
        },
    ]
    return _payload(
        "invoiced",
        "Invoiced",
        {
            "summary_by_customer": {
                "name": "Summary by Customer",
                "rows": [
                    {"CustomerAccount": "C-1001", "CustomerName": "HD SUPPLY", "Salesman": "DDweck", "InvoiceCount": 1, "Total Invoices": 1035.0},
                    {"CustomerAccount": "C-1002", "CustomerName": "MAZER WHOLESALE", "Salesman": "DDweck", "InvoiceCount": 1, "Total Invoices": -50.0},
                    {"CustomerAccount": "C-2001", "CustomerName": "AMAZON.COM DEDC, LLC", "Salesman": "HKaufman", "InvoiceCount": 1, "Total Invoices": 520.0},
                ],
            },
            "commissions": {
                "name": "Commissions",
                "rows": [
                    {"Salesman": "DDweck", "SalesmanName": "Dweck, David", "Percent": 0.05, "NetCommission": 985.0, "CommissionDollars": 49.25},
                    {"Salesman": "HKaufman", "SalesmanName": "Kaufman, Herschel", "Percent": 0.03, "NetCommission": 500.0, "CommissionDollars": 15.0},
                ],
            },
            "full_details": {
                "name": "Full Details",
                "rows": [
                    {"InvoiceNumber": "IN01008282", "CustomerAccount": "C-1001", "CustomerName": "HD SUPPLY", "InvoiceDate": "2026-09-02", "Total Invoice": 1035.0, "Salesman": "DDweck", "SalesmanName": "Dweck, David"},
                    {"InvoiceNumber": "FCRD-004181", "CustomerAccount": "C-1002", "CustomerName": "MAZER WHOLESALE", "InvoiceDate": "2026-09-03", "Total Invoice": -50.0, "Salesman": "DDweck", "SalesmanName": "Dweck, David"},
                    {"InvoiceNumber": "IN01008290", "CustomerAccount": "C-2001", "CustomerName": "AMAZON.COM DEDC, LLC", "InvoiceDate": "2026-09-04", "Total Invoice": 520.0, "Salesman": "HKaufman", "SalesmanName": "Kaufman, Herschel"},
                ],
            },
            "credits": {
                "name": "Credits",
                "rows": [{"InvoiceNumber": "FCRD-004181", "CustomerAccount": "C-1002", "CustomerName": "MAZER WHOLESALE", "Salesman": "DDweck", "Total Invoice": -50.0}],
            },
            "invoices": {
                "name": "Invoices",
                "rows": [
                    {"InvoiceNumber": "IN01008282", "CustomerAccount": "C-1001", "Salesman": "DDweck", "Total Invoice": 1035.0},
                    {"InvoiceNumber": "IN01008290", "CustomerAccount": "C-2001", "Salesman": "HKaufman", "Total Invoice": 520.0},
                ],
            },
            "audit_reversals": {
                "name": "Audit - Reversals",
                "rows": [
                    {
                        "InvoiceNumber": "FCRD-004181",
                        "CustomerName": "MAZER WHOLESALE",
                        "Salesman": "DDweck",
                        "Total Invoice": -50.0,
                        "Note": "Credit / reversal pair",
                    }
                ],
            },
            "totals_by_salesman": {
                "name": "Totals by Salesman",
                "rows": [
                    {"Salesman": "DDweck", "InvoiceCount": 2, "Total Invoices": 985.0},
                    {"Salesman": "HKaufman", "InvoiceCount": 1, "Total Invoices": 520.0},
                ],
            },
        },
        raw,
    )


def ordered_payload() -> dict:
    rows = [
        {"CustomerAccount": "C-1001", "CustomerName": "HD SUPPLY", "Salesman": "DDweck", "SalesOrderNumber": "SO-88021", "QtyOrdered": 10, "QtyLeftToShip": 2, "Ordered$": 400.0, "Open$": 80.0, "Fulfillment%": 80.0},
        {"CustomerAccount": "C-2001", "CustomerName": "AMAZON.COM DEDC, LLC", "Salesman": "HKaufman", "SalesOrderNumber": "SO-90110", "QtyOrdered": 20, "QtyLeftToShip": 0, "Ordered$": 900.0, "Open$": 0.0, "Fulfillment%": 100.0},
    ]
    return _payload(
        "ordered",
        "Ordered",
        {
            "summary": {"name": "Summary", "rows": [{"CustomerAccount": r["CustomerAccount"], "CustomerName": r["CustomerName"], "Open$": r["Open$"], "Fulfillment%": r["Fulfillment%"]} for r in rows]},
            "by_customer": {"name": "By Customer", "rows": rows},
            "by_item": {"name": "By Item", "rows": [{"Item #": "A-100", "Item Name": "Widget", "QtyOrdered": 30, "Open$": 80.0}]},
            "by_order": {"name": "By Order", "rows": rows},
            "by_salesman": {"name": "By Salesman", "rows": [{"Salesman": "DDweck", "Open$": 80.0}, {"Salesman": "HKaufman", "Open$": 0.0}]},
            "full_data": {"name": "Full Data", "rows": rows},
        },
        rows,
    )


def salesman_payload() -> dict:
    rows = [
        {"SalesmanName": "Dweck, David", "CustomerName": "HD SUPPLY", "Jan": 1200.0, "YTD": 1200.0},
        {"SalesmanName": "Kaufman, Herschel", "CustomerName": "AMAZON.COM DEDC, LLC", "Jan": 800.0, "YTD": 800.0},
    ]
    return _payload(
        "salesman",
        "Salesman",
        {"yoy": {"name": "Year over Year", "rows": rows}, "ytd": {"name": "YTD", "rows": rows}},
        rows,
    )


def number_4_payload() -> dict:
    rows = [
        {"Customer": "HD SUPPLY", "Item #": "A-100", "Sep Qty": 4, "Sep $": 200.0, "Total Qty": 40, "Total $": 2000.0, "Avg Price": 50.0, "Salesman": "DDweck"},
        {"Customer": "AMAZON.COM DEDC, LLC", "Item #": "B-200", "Sep Qty": 8, "Sep $": 400.0, "Total Qty": 80, "Total $": 4000.0, "Avg Price": 50.0, "Salesman": "HKaufman"},
    ]
    return _payload(
        "number_4",
        "Number 4",
        {
            "by_customer": {"name": "By Customer", "rows": rows},
            "by_item": {"name": "By Item", "rows": rows},
            "by_customer_ytd": {"name": "By Customer YTD", "rows": rows},
            "by_item_ytd": {"name": "By Item YTD", "rows": rows},
        },
        rows,
    )


def customer_activity_payload() -> dict:
    rows = [
        {"CustomerAccount": "C-1001", "CustomerName": "HD SUPPLY", "Salesman": "DDweck", "Last Order Date": "2026-09-02", "Last Order #": "SO-88021"},
        {"CustomerAccount": "C-2001", "CustomerName": "AMAZON.COM DEDC, LLC", "Salesman": "HKaufman", "Last Order Date": "2026-09-04", "Last Order #": "SO-90110"},
        {"CustomerAccount": "C-3001", "CustomerName": "UNASSIGNED CO", "Salesman": "", "Last Order Date": "2026-08-01", "Last Order #": "SO-10001"},
    ]
    return _payload(
        "customer_activity",
        "Customer Activity",
        {
            "all": {"name": "All", "rows": rows},
            "ddweck": {"name": "Dweck, David", "rows": [rows[0]]},
            "hkaufman": {"name": "Kaufman, Herschel", "rows": [rows[1]]},
            "unassigned": {"name": "Unassigned", "rows": [rows[2]]},
        },
        rows,
    )


def item_averages_payload() -> dict:
    rows = [
        {"Item #": "A-100", "Item Name": "Widget", "Total Qty": 120, "Avg/Month": 10.0, "Avg/Week": 2.31},
        {"Item #": "B-200", "Item Name": "Gadget", "Total Qty": 52, "Avg/Month": 4.33, "Avg/Week": 1.0},
    ]
    return _payload("item_averages", "Item Averages", {"items": {"name": "Item Averages", "rows": rows}}, rows)


def sales_by_state_payload() -> dict:
    summary = [
        {"State": "NY", "Sales": 50000.0},
        {"State": "NJ", "Sales": 12000.0},
        {"State": "PA", "Sales": 8000.0},
    ]
    return _payload(
        "sales_by_state",
        "Sales by State",
        {
            "summary": {"name": "Summary", "rows": summary},
            "new_york_city": {"name": "New York City", "rows": [{"Borough": "Brooklyn", "Sales": 22000.0}, {"Borough": "Queens", "Sales": 9000.0}]},
            "detail": {"name": "Detail", "rows": [{"Customer": "HD SUPPLY", "State": "NY", "Sales": 1035.0}]},
        },
        summary,
    )


CTD_COLUMNS = [
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


def customer_transaction_detail_payload() -> dict:
    rows = [
        {
            "Company": "achm",
            "AccountNum": "C-1001",
            "Invoice": "IN1",
            "AmountMST": 100.0,
            "RemainAmountCur": 40.0,
            "Voucher": "AR-100",
            "RecId": "111",
            "CreatedDateTime": "2026-09-02 10:00:00",
            "TransType": "Sales",
            "OffsetTransVoucher": "PAY-1",
            "SettleAmountCur": 60.0,
            "OffsetRecId": "A",
            "OffsetAmountMST": 60.0,
            "OffsetVoucher": "STTL-A",
            "OffsetCreatedDateTime": "2026-09-03 09:00:00",
            "OffsetCreatedBy": "apay",
        },
        {
            "Company": "achm",
            "AccountNum": "C-1001",
            "Invoice": "IN1",
            "AmountMST": 100.0,
            "RemainAmountCur": 40.0,
            "Voucher": "AR-100",
            "RecId": "111",
            "CreatedDateTime": "2026-09-02 10:00:00",
            "TransType": "Sales",
            "OffsetTransVoucher": "PAY-2",
            "SettleAmountCur": 40.0,
            "OffsetRecId": "B",
            "OffsetAmountMST": 40.0,
            "OffsetVoucher": "STTL-B",
            "OffsetCreatedDateTime": "2026-09-04 09:00:00",
            "OffsetCreatedBy": "apay",
        },
    ]
    return _payload(
        "customer_transaction_detail",
        "Customer Transaction Detail",
        {"transactions": {"name": "Transactions", "columns": list(CTD_COLUMNS), "rows": rows}},
        rows,
    )


_BUILDERS = {
    "invoiced": invoiced_payload,
    "ordered": ordered_payload,
    "salesman": salesman_payload,
    "number_4": number_4_payload,
    "customer_activity": customer_activity_payload,
    "item_averages": item_averages_payload,
    "sales_by_state": sales_by_state_payload,
    "customer_transaction_detail": customer_transaction_detail_payload,
}


def _row_salesman(row: dict) -> str:
    direct = str(row.get("salesman") or row.get("Salesman") or "")
    if direct:
        return direct
    name = str(row.get("SalesmanName") or "")
    for salesman in SALESMEN:
        if salesman["name"] == name:
            return salesman["key"]
    return ""


def _row_account(row: dict) -> str:
    direct = str(
        row.get("CustomerAccount")
        or row.get("Customer Account")
        or row.get("AccountNum")
        or row.get("account")
        or ""
    )
    if direct:
        return direct
    name = str(row.get("CustomerName") or row.get("Customer") or "")
    for customer in CUSTOMERS:
        if customer["name"] == name:
            return customer["account"]
    return ""


def _filter_tabs(payload: dict, keep) -> None:
    report = payload["data"]
    for tab in report["tabs"].values():
        tab["rows"] = [row for row in tab["rows"] if keep(row)]
    report["raw"] = [row for row in report["raw"] if keep(row)]


def apply_viewer_filters(
    payload: dict,
    *,
    salesman: str = "",
    customers: list[str] | None = None,
    n4_mode: str = "both",
    hide_commissions: bool = False,
    report_key: str = "",
) -> dict:
    """Post-filter tabs the grid already has. Same rules for mock and live rows."""
    key = report_key or payload.get("data", {}).get("report_key") or ""
    if salesman and key != "customer_transaction_detail":
        _filter_tabs(payload, lambda row: _row_salesman(row) == salesman)
    if customers:
        wanted = set(customers)
        _filter_tabs(payload, lambda row: _row_account(row) in wanted)
    tabs = payload["data"]["tabs"]
    if key == "number_4" and n4_mode in {"by_customer", "by_item"}:
        keep_prefix = "by_customer" if n4_mode == "by_customer" else "by_item"
        payload["data"]["tabs"] = {
            tab_key: tab for tab_key, tab in tabs.items() if tab_key.startswith(keep_prefix)
        }
    if hide_commissions:
        payload["data"]["tabs"].pop("commissions", None)
    totals = payload["data"]["tabs"].get("totals_by_salesman")
    if totals:
        unique = {str(row.get("Salesman") or "") for row in totals["rows"] if row.get("Salesman")}
        if len(unique) < 2:
            payload["data"]["tabs"].pop("totals_by_salesman", None)
    audit = payload["data"]["tabs"].get("audit_reversals")
    if audit and not audit["rows"]:
        payload["data"]["tabs"].pop("audit_reversals", None)
    return payload


def mock_report(
    key: str,
    salesman: str = "",
    customers: list[str] | None = None,
    n4_mode: str = "both",
    hide_commissions: bool = False,
) -> dict:
    builder = _BUILDERS.get(key)
    if builder is None:
        raise KeyError(key)
    payload = deepcopy(builder())
    return apply_viewer_filters(
        payload,
        salesman=salesman,
        customers=customers,
        n4_mode=n4_mode,
        hide_commissions=hide_commissions,
        report_key=key,
    )


def last_order_for(account: str) -> dict | None:
    by_acct = {row["account"]: row for row in CUSTOMERS}
    customer = by_acct.get(account)
    if customer is None:
        return None
    invoices = [
        row
        for row in invoiced_payload()["data"]["raw"]
        if row["CustomerAccount"] == account
    ]
    return {
        "customer": customer,
        "primary": {
            "order_number": "SO-88021" if account != "C-2001" else "SO-90110",
            "order_date": "2026-09-02" if account != "C-2001" else "2026-09-04",
            "salesman": customer["salesman"],
            "po": "PO-1001",
        },
        "lines": [
            {"Item #": "A-100", "Description": "Widget", "Qty": 10, "Price": 40.0, "Amount": 400.0},
            {"Item #": "B-200", "Description": "Gadget", "Qty": 2, "Price": 15.0, "Amount": 30.0},
        ],
        "recent_invoices": invoices,
        "recent_error": "",
    }
