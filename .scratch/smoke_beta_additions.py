# Verify clo LastOrder attribute access and keep/export imports
import sys
sys.path.insert(0, "v3")
from report_engine.reports.customer_last_order import LastOrder, OrderSummary, LineRow
from web.reporting.last_order_export import last_order_pdf
from web.delivery.filename_template import resolve_filename_template
from web.reporting.odata_bridge import _attach_ordered_default_group

pdf = last_order_pdf(
    customer_name="Acme", account="100",
    primary={"order_number": "SO1", "order_date": "2026-07-01"},
    display_po="PO1",
    lines=[{"item": "A", "description": "Item", "qty_ordered": 1, "qty_shipped": 1,
            "qty_cancelled": 0, "sales_price": 2.5, "total": 2.5}],
    totals={"qty_ordered": 1, "qty_shipped": 1, "qty_cancelled": 0, "total": 2.5},
)
assert pdf.startswith(b"%PDF"), pdf[:20]

tab = _attach_ordered_default_group({"key": "summary", "name": "Summary", "rows": []})
assert tab["default_group"] == ["Salesman"]
tab2 = _attach_ordered_default_group({"key": "full_data", "name": "Full Data", "rows": []})
assert "default_group" not in tab2

print("ok", resolve_filename_template("{MM}_{Month}", report_name="X"))
