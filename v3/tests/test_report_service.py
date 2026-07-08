"""ReportService: report_key -> fetch -> adapt -> build -> payload wiring."""

from datetime import date

import pytest

from report_engine.facts import SalesmanFact
from report_engine.lib import salesman_key
from report_engine.sources import ordered as src_ordered
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
        # Fresh list per call, like the real client (which json-parses new rows
        # each time); the adapters consume the list to save memory on big runs.
        rows = list(self.rows_by_id.get(report_id, []))
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
    out = _svc({"ordered_report": rows}).builder_for("ordered")({}, None)
    assert out["report_key"] == "ordered"
    assert out["row_count"] == 1
    assert [t["key"] for t in out["tabs"]][0] == "summary"


def test_invoiced_does_ytd_fetch_for_commissions():
    rows = [{"Invoice": "I1", "InvoiceAccount": "100", "InvoiceDate": "2026-03-01",
             "Amount": "100", "SalesGroup": "REdwards"}]
    svc = _svc({"invoiced_report": rows})
    out = svc.builder_for("invoiced")({"year": "2026"}, None)
    assert out["report_key"] == "invoiced"
    # invoiced_report fetched twice: selected period + YTD window
    assert svc.client.calls.count("invoiced_report") == 2


def test_invoiced_ytd_window_anchors_to_selected_period_end():
    """v2 parity: the commissions YTD window is Jan 1 .. selected period end,
    derived from the period filter (not a separate year filter)."""
    rows = [{"Invoice": "I1", "InvoiceAccount": "100", "InvoiceDate": "2025-06-01",
             "Amount": "100", "SalesGroup": "REdwards"}]
    svc = _svc({"invoiced_report": rows})
    svc.builder_for("invoiced")({"period": "custom",
                                 "start_date": "2025-02-01", "end_date": "2025-06-15"}, None)
    # Second invoiced fetch = the YTD window; it must open at Jan 1 of the period
    # end's year and close at the period end (end-of-day), regardless of start.
    ytd_params = [p for (rid, p) in svc.client.params_calls
                  if rid == "invoiced_report"][1]
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
    svc = _svc({"invoiced_report": rows})
    out = svc.builder_for("invoiced")({"customers": ["100", "300"]}, None)
    accts = {r["CustomerAccount"]
             for t in out["tabs"] if t["key"] == "invoices" for r in t["rows"]}
    assert accts == {"100", "300"}     # 200 excluded
    assert out["row_count"] == 2


_N4_CUSTOMER_ROW = {"Customer #": "100", "Customer Name": "Acme", "Item #": "ITM-A",
                    "Item Name": "W", "Jun-26 Qty": "3", "Jun-26 $": "30",
                    "Total Qty": "3", "Total $": "30", "Avg Price": "10",
                    "Salesman": "REdwards", "Book Price": "12.5"}
_N4_ITEM_ROW = {"Item #": "ITM-A", "Item Name": "W", "Customer #": "100",
                "Customer Name": "Acme", "Jun-26 Qty": "3", "Jun-26 $": "30",
                "Total Qty": "3", "Total $": "30", "Avg Price": "10",
                "Salesman": "REdwards", "Book Price": "12.5"}
_N4_ROWS = {"customer_item_sales_rolling_12": [_N4_CUSTOMER_ROW],
            "item_customer_sales_rolling_12": [_N4_ITEM_ROW]}


def test_number_4_both_mode_calls_both_sps_and_builds_two_tabs():
    svc = _svc(_N4_ROWS)
    out = svc.builder_for("number_4")({"mode": "both"}, None)
    assert [t["key"] for t in out["tabs"]] == ["by_customer", "by_item"]
    assert svc.client.calls == [
        "customer_item_sales_rolling_12", "item_customer_sales_rolling_12"]
    assert out["row_count"] == 2  # one row in each view


def test_number_4_single_mode_calls_only_its_sp():
    svc = _svc(_N4_ROWS)
    out = svc.builder_for("number_4")({"mode": "by_item"}, None)
    assert [t["key"] for t in out["tabs"]] == ["by_item"]
    assert svc.client.calls == ["item_customer_sales_rolling_12"]


def test_number_4_sends_as_of_date_and_include_current_month():
    svc = _svc(_N4_ROWS)
    svc.builder_for("number_4")({"mode": "by_customer"}, None)
    _, sp = svc.client.params_calls[0]
    assert sp["IncludeCurrentMonth"] is True
    assert len(sp["AsOfDate"]) == 10  # yyyy-mm-dd


def test_number_4_scoped_user_only_sees_their_salesman_rows():
    other = dict(_N4_CUSTOMER_ROW, **{"Customer #": "200", "Salesman": "JSmith"})
    svc = _svc({"customer_item_sales_rolling_12": [_N4_CUSTOMER_ROW, other]})
    out = svc.builder_for("number_4")({"mode": "by_customer"}, {"redwards"})
    rows = out["tabs"][0]["rows"]
    assert [r["Customer #"] for r in rows] == ["100"]
    assert out["row_count"] == 1


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
    svc = _svc({"ordered_report": rows})
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


class _DateWindowClient:
    """Fake SP that returns only rows whose CreatedDateTime falls in the requested
    window, like the real stored procedure. Records each (from, to) day pair so a
    test can prove the service split one big window into month-sized requests."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.windows: list[tuple[str, str]] = []

    def run_report(self, report_id: str, params: dict) -> ReportResult:
        frm = (params.get("CreatedDateTimeFrom") or "0000-00-00")[:10]
        to = (params.get("CreatedDateTimeTo") or "9999-99-99")[:10]
        self.windows.append((frm, to))
        sel = [r for r in self.rows if frm <= str(r["CreatedDateTime"])[:10] <= to]
        return ReportResult(report_id=report_id, columns=[], rows=list(sel), row_count=len(sel))


def _order_row(order_no: str, created: str) -> dict:
    return {"SalesOrderNumber": order_no, "CustomerAccount": "100", "Item": "A",
            "QuantityOrdered": "1", "Ordered $": "10", "SalesStatus": "Open",
            "SalesGroup": "REdwards", "CreatedDateTime": created}


def test_chunked_fetch_unions_months_into_one_window():
    """A multi-month window is fetched one month at a time and stitched back into
    exactly the rows a single full-window call would return - in order, no gaps."""
    rows = [
        _order_row("SO-DEC", "2025-12-31T10:00:00"),   # before window -> excluded
        _order_row("SO-JAN-A", "2026-01-05T10:00:00"),
        _order_row("SO-JAN-B", "2026-01-31T23:00:00"),
        _order_row("SO-FEB", "2026-02-14T10:00:00"),
        _order_row("SO-MAR-A", "2026-03-01T00:30:00"),
        _order_row("SO-MAR-B", "2026-03-31T12:00:00"),
        _order_row("SO-APR", "2026-04-01T09:00:00"),    # after window -> excluded
    ]
    client = _DateWindowClient(rows)
    svc = ReportService(client, _FakeSalesmenRepo())

    facts = svc._facts_chunked(
        "salesline_release", {}, src_ordered.to_facts, None,
        from_key="CreatedDateTimeFrom", to_key="CreatedDateTimeTo",
        start=date(2026, 1, 1), end=date(2026, 3, 31))

    assert [f.sales_order_number for f in facts] == [
        "SO-JAN-A", "SO-JAN-B", "SO-FEB", "SO-MAR-A", "SO-MAR-B"]
    # three month-sized requests with day-aligned boundaries (no overlap, no gap)
    assert client.windows == [
        ("2026-01-01", "2026-01-31"),
        ("2026-02-01", "2026-02-28"),
        ("2026-03-01", "2026-03-31"),
    ]


def test_ordered_bounded_period_is_fetched_in_chunks_and_matches_single_call():
    """The ordered report over a bounded period chunks the fetch by month, and the
    stitched result equals what one big call over the same window would produce."""
    rows = [
        _order_row("SO-JAN", "2026-01-10T10:00:00"),
        _order_row("SO-FEB", "2026-02-10T10:00:00"),
        _order_row("SO-MAR", "2026-03-10T10:00:00"),
        _order_row("SO-OUT", "2026-05-10T10:00:00"),   # outside the window
    ]
    svc = ReportService(_DateWindowClient(rows), _FakeSalesmenRepo())
    out = svc.builder_for("ordered")(
        {"period": "custom", "start_date": "2026-01-01", "end_date": "2026-03-31"}, None)

    assert out["row_count"] == 3                        # SO-OUT excluded
    assert svc.client.windows == [
        ("2026-01-01", "2026-01-31"),
        ("2026-02-01", "2026-02-28"),
        ("2026-03-01", "2026-03-31"),
    ]
    full = next(t for t in out["tabs"] if t["key"] == "full_data")
    assert {r["SalesOrderNumber"] for r in full["rows"]} == {"SO-JAN", "SO-FEB", "SO-MAR"}


def test_ordered_all_time_stays_single_call():
    """Open-ended (all_time) keeps one call so the SP's own default window is
    unchanged - chunking only applies to bounded periods."""
    rows = [_order_row("SO1", "2026-02-01T10:00:00")]
    svc = ReportService(_DateWindowClient(rows), _FakeSalesmenRepo())
    svc.builder_for("ordered")({"period": "all_time"}, None)
    # one request, with no date window pushed down
    assert len(svc.client.windows) == 1
    assert svc.client.windows[0] == ("0000-00-00", "9999-99-99")


def test_ensure_customers_resyncs_then_finds():
    """ensure_customers triggers a resync; known customers return [] (no errors)."""
    from web.reporting.lookups import LookupService

    svc = _svc({"customer_master": [
        {"CustomerAccount": "100", "CustomerName": "Acme", "SalesGroup": "REdwards"},
        {"CustomerAccount": "200", "CustomerName": "Globex", "SalesGroup": "JSmith"},
    ]})
    lk = LookupService(svc, _FakeSalesmenRepo())
    # Before any populate, 100 is unknown (cache cold)
    assert lk.customer("100") is None
    # ensure_customers triggers a resync
    still_unknown = lk.ensure_customers(["100", "200"])
    assert still_unknown == []
    assert lk.customer("100") is not None
    # Truly unknown customer remains unknown after resync
    assert lk.ensure_customers(["999"]) == ["999"]
