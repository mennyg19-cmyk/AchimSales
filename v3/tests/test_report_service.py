"""ReportService: report_key -> fetch -> adapt -> build -> payload wiring."""

import pytest

from report_engine.facts import SalesmanFact
from report_engine.lib import salesman_key
from web.reporting.http_client import ReportResult, ReportingApiError
from web.reporting.report_service import ReportService


class _FakeClient:
    """Returns canned rows per report_id; records the report_ids requested."""

    def __init__(self, rows_by_id: dict, fail_ids: set | None = None):
        self.rows_by_id = rows_by_id
        self.fail_ids = fail_ids or set()
        self.calls: list[str] = []
        self.params_calls: list[tuple[str, dict]] = []

    def run_report(self, report_id: str, params: dict) -> ReportResult:
        self.calls.append(report_id)
        self.params_calls.append((report_id, dict(params)))
        if report_id in self.fail_ids:
            raise ReportingApiError(f"forced failure for {report_id}")
        rows = self.rows_by_id.get(report_id, [])
        return ReportResult(report_id=report_id, columns=[], rows=rows, row_count=len(rows))


class _FakeSalesmenRepo:
    def all_as_facts(self):
        return {salesman_key("REdwards"): SalesmanFact(
            source="reporting_api", key="redwards", number="080",
            full_name="Reggie Edwards", display_name="Reggie", commission_pct=0.05)}


def _svc(rows_by_id, fail_ids=None, mirror=None):
    return ReportService(_FakeClient(rows_by_id, fail_ids), _FakeSalesmenRepo(),
                         customer_mirror=mirror)


def test_unknown_report_raises():
    with pytest.raises(KeyError):
        _svc({}).builder_for("nope")


def test_ordered_payload_shape():
    rows = [{"SalesOrderNumber": "SO1", "CustomerAccount": "100", "Item": "A",
             "QuantityOrdered": "5", "Ordered $": "50", "SalesStatus": "Open"}]
    out = _svc({"salesline_release": rows}).builder_for("ordered")({}, None)
    assert out["report_key"] == "ordered"
    assert out["row_count"] == 1
    assert [t["key"] for t in out["tabs"]][0] == "summary"


def test_invoiced_does_ytd_fetch_for_commissions():
    rows = [{"Invoice": "I1", "InvoiceAccount": "100", "InvoiceDate": "2026-03-01",
             "Amount": "100", "SalesGroup": "REdwards"}]
    svc = _svc({"invoiced_order_charges": rows})
    out = svc.builder_for("invoiced")({"year": "2026"}, None)
    assert out["report_key"] == "invoiced"
    # invoiced_order_charges fetched twice: selected period + YTD window
    assert svc.client.calls.count("invoiced_order_charges") == 2


def test_invoiced_ytd_window_anchors_to_selected_period_end():
    """v2 parity: the commissions YTD window is Jan 1 .. selected period end,
    derived from the period filter (not a separate year filter)."""
    rows = [{"Invoice": "I1", "InvoiceAccount": "100", "InvoiceDate": "2025-06-01",
             "Amount": "100", "SalesGroup": "REdwards"}]
    svc = _svc({"invoiced_order_charges": rows})
    svc.builder_for("invoiced")({"period": "custom",
                                 "start_date": "2025-02-01", "end_date": "2025-06-15"}, None)
    # Second invoiced fetch = the YTD window; it must open at Jan 1 of the period
    # end's year and close at the period end (end-of-day), regardless of start.
    ytd_params = [p for (rid, p) in svc.client.params_calls
                  if rid == "invoiced_order_charges"][1]
    assert ytd_params["InvoiceDateFrom"].startswith("2025-01-01")
    assert ytd_params["InvoiceDateTo"].startswith("2025-06-15")


def test_invoiced_multi_customer_is_post_filtered():
    """The SP can only push one InvoiceAccount, so a 2+ customer selection must
    be narrowed in-process (period + YTD facts) instead of returning everyone."""
    rows = [
        {"Invoice": "I1", "InvoiceAccount": "100", "InvoiceDate": "2026-03-01",
         "Amount": "100", "SalesGroup": "REdwards"},
        {"Invoice": "I2", "InvoiceAccount": "200", "InvoiceDate": "2026-03-02",
         "Amount": "200", "SalesGroup": "REdwards"},
        {"Invoice": "I3", "InvoiceAccount": "300", "InvoiceDate": "2026-03-03",
         "Amount": "300", "SalesGroup": "REdwards"},
    ]
    svc = _svc({"invoiced_order_charges": rows})
    out = svc.builder_for("invoiced")({"customers": ["100", "300"]}, None)
    accts = {r["CustomerAccount"]
             for t in out["tabs"] if t["key"] == "invoices" for r in t["rows"]}
    assert accts == {"100", "300"}     # 200 excluded
    assert out["row_count"] == 2


def test_number_4_blank_book_price_when_released_products_down():
    rows = [{"Invoice": "I1", "InvoiceAccount": "100", "InvoiceDate": "2026-03-01",
             "Item": "ITM-A", "ItemName": "W", "InventQTY": "1", "Amount": "9",
             "SalesGroup": "REdwards", "SalesOrder": "SO1"}]
    svc = _svc({"invoice_lines": rows}, fail_ids={"released_products"})
    out = svc.builder_for("number_4")({}, None)
    by_item = next(t for t in out["tabs"] if t["key"] == "by_item_12mo")
    assert all(r["BookPrice"] is None for r in by_item["rows"])


def test_number_4_book_price_joined_when_available():
    rows = [{"Invoice": "I1", "InvoiceAccount": "100", "InvoiceDate": "2026-03-01",
             "Item": "ITM-A", "ItemName": "W", "InventQTY": "1", "Amount": "9",
             "SalesGroup": "REdwards", "SalesOrder": "SO1"}]
    released = [{"ItemNumber": "ITM-A", "SalesPrice": "2.50"}]
    svc = _svc({"invoice_lines": rows, "released_products": released})
    out = svc.builder_for("number_4")({}, None)
    by_item = next(t for t in out["tabs"] if t["key"] == "by_item_12mo")
    assert by_item["rows"][0]["BookPrice"] == 2.50


def test_lookup_salesmen_emits_raw_salesgroup_not_normalized_key():
    """The salesman dropdown VALUE must be the raw SalesGroup the SP expects.
    Before the universe warms we return [] (never the normalized master keys)."""
    from web.reporting.lookups import LookupService

    svc = _svc({"customer_master": [
        {"CustomerAccount": "1", "CustomerName": "Acme", "SalesGroup": "REdwards"},
    ]})
    lk = LookupService(svc, _FakeSalesmenRepo())
    assert lk.salesmen() == []          # not warm yet -> no (wrong) fallback values
    lk._populate()
    sm = lk.salesmen()
    assert [r["key"] for r in sm] == ["REdwards"]   # raw, not "redwards"
    assert sm[0]["name"] == "Reggie"                # display enriched from master


class _MirrorCustomer:
    """Minimal stand-in for a persisted dashboard-mirror customer row."""

    def __init__(self, account, name, salesgroup):
        self.customer_account = account
        self.customer_name = name
        self.sales_group = salesgroup


def test_lookup_dropdowns_populate_from_mirror_before_universe_warms():
    """The dropdowns must populate from the shared persisted mirror even when
    this worker's live universe hasn't been populated yet (multi-worker case)."""
    from web.reporting.lookups import LookupService

    svc = _svc({"customer_master": []})  # live universe never warmed here
    mirror = [_MirrorCustomer("100", "Acme", "REdwards"),
              _MirrorCustomer("200", "Globex", "REdwards")]
    lk = LookupService(svc, _FakeSalesmenRepo(), mirror_customers=lambda: mirror)

    custs = lk.customers()
    assert [c["key"] for c in custs] == ["100", "200"]
    sm = lk.salesmen()
    assert [r["key"] for r in sm] == ["REdwards"]   # raw SalesGroup from the mirror
    assert sm[0]["name"] == "Reggie"                # still enriched from the master
    assert lk.status()["mirror_row_count"] == 2

    # The authorization path resolves from the mirror too (same authoritative
    # SalesGroup), so auth works on a worker whose live universe is still cold.
    rec = lk.customer("100")
    assert rec == {"key": "100", "name": "Acme", "salesman": "REdwards"}


def test_customer_activity_uses_mirror_when_master_down():
    orders = [{"CustomerAccount": "100", "SalesOrderNumber": "SO1",
               "CreatedDateTime": "2026-03-01T00:00:00", "QuantityOrdered": "1", "Item": "A"}]
    mirror_rows = [{"CustomerAccount": "100", "CustomerName": "Acme", "SalesGroup": "REdwards"}]
    svc = _svc({"salesline_release": orders}, fail_ids={"customer_master"},
               mirror=lambda: mirror_rows)
    out = svc.builder_for("customer_activity")({}, None)
    all_tab = next(t for t in out["tabs"] if t["key"] == "all")
    assert len(all_tab["rows"]) == 1
    assert all_tab["rows"][0]["Customer Account"] == "100"


def test_scope_filters_facts_to_visible_keys():
    """A scoped user only sees facts whose sales_group matches their keys."""
    rows = [
        {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "Item": "A",
         "QuantityOrdered": "5", "Ordered $": "50", "SalesStatus": "Open",
         "SalesGroup": "REdwards"},
        {"SalesOrderNumber": "SO2", "CustomerAccount": "200", "Item": "B",
         "QuantityOrdered": "3", "Ordered $": "30", "SalesStatus": "Open",
         "SalesGroup": "JSmith"},
    ]
    svc = _svc({"salesline_release": rows})
    # Unrestricted: sees both
    out_all = svc.builder_for("ordered")({}, None)
    assert out_all["row_count"] == 2
    # Scoped to REdwards only
    out_scoped = svc.builder_for("ordered")({}, {"redwards"})
    assert out_scoped["row_count"] == 1
    full = next(t for t in out_scoped["tabs"] if t["key"] == "full_data")
    assert full["rows"][0]["SalesOrderNumber"] == "SO1"
    # Empty scope: sees nothing
    out_empty = svc.builder_for("ordered")({}, set())
    assert out_empty["row_count"] == 0
