"""Delivery subsystem: layout replay, email outbox, SharePoint mock, orchestration."""

from __future__ import annotations

import io
import urllib.error

import pytest

from web.config import Config
from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.outbox import OutboxRepository
from web.data.repositories.delivery_legs import DeliveryLegRepository
from web.delivery.email import MAX_GRAPH_ATTACH_BYTES, EmailService, split_recipients
from web.delivery.graph_mail import GraphMailError, GraphMailer
from web.delivery.layout import apply_layout, expand_clones
from web.delivery.service import DeliveryService
from web.delivery.onedrive import onedrive_children_url
from web.delivery.sharepoint import TEST_SHAREPOINT_FOLDER, SharePointService


def _cfg(tmp_path, **over) -> Config:
    base = dict(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="", new_app_marker=True, outbox_dir=tmp_path / "outbox",
    )
    base.update(over)
    return Config(**base)


# --- layout ----------------------------------------------------------------

def _payload():
    return {"tabs": [{
        "key": "summary", "name": "Summary",
        "columns": [{"field": "a", "header": "A"}, {"field": "b", "header": "B"},
                    {"field": "c", "header": "C"}],
        "rows": [{"a": "x", "b": 3, "c": "keep"}, {"a": "y", "b": 1, "c": "drop"},
                 {"a": "z", "b": 2, "c": "keep"}],
    }]}


def test_expand_clones_recreates_duplicate_tab_and_orders():
    payload = _payload()
    layout = {
        "order": ["summary__copy", "summary"],
        "clones": [{"key": "summary__copy", "baseKey": "summary", "name": "Summary (copy)"}],
        "views": {},
    }
    out = expand_clones(payload, layout)
    keys = [t["key"] for t in out["tabs"]]
    assert keys == ["summary__copy", "summary"]          # clone created + on-screen order
    clone = out["tabs"][0]
    assert clone["name"] == "Summary (copy)"
    assert clone["rows"] == payload["tabs"][0]["rows"]    # data copied from base
    # Independence: mutating the clone must not touch the base tab.
    clone["rows"].append({"a": "new"})
    assert len(out["tabs"][1]["rows"]) == 3


def test_expand_clones_noop_without_clones_or_order():
    assert expand_clones(_payload(), None) == _payload()
    assert expand_clones(_payload(), {"views": {}}) == _payload()


def test_expand_clones_drops_tabs_not_in_order():
    payload = {"tabs": [
        {"key": "summary", "name": "Summary", "rows": [{"a": 1}]},
        {"key": "commissions", "name": "Commissions", "rows": [{"a": 2}]},
        {"key": "invoices", "name": "Invoices", "rows": [{"a": 3}]},
    ]}
    out = expand_clones(payload, {"order": ["summary", "invoices"], "views": {}})
    assert [t["key"] for t in out["tabs"]] == ["summary", "invoices"]


def test_expand_clones_empty_order_keeps_every_tab():
    payload = _payload()
    assert expand_clones(payload, {"order": []}) == payload


def test_apply_layout_hides_reorders_sorts_and_filters():
    layout = {"views": {"summary": {
        "hidden": ["a"], "order": ["c", "b"],
        "sorters": [{"column": "b", "dir": "asc"}],
        "headerFilters": [{"field": "c", "value": "keep"}],
    }}}
    out = apply_layout(_payload(), layout)
    tab = out["tabs"][0]
    assert [c["field"] for c in tab["columns"]] == ["c", "b"]      # hidden a, reordered
    assert [r["b"] for r in tab["rows"]] == [2, 3]                 # filtered to keep, sorted asc
    assert all(r["c"] == "keep" for r in tab["rows"])


def test_apply_layout_legacy_header_filters_still_work():
    # Old presets stored a flat substring list under "headerFilters".
    layout = {"views": {"summary": {"headerFilters": [{"field": "c", "value": "keep"}]}}}
    out = apply_layout(_payload(), layout)
    assert all(r["c"] == "keep" for r in out["tabs"][0]["rows"])


def test_apply_layout_columnfilters_numeric_and_text_operators():
    payload = {"tabs": [{
        "key": "summary", "name": "Summary",
        "columns": [{"field": "a", "header": "A", "type": "text"},
                    {"field": "b", "header": "B", "type": "int"}],
        "rows": [{"a": "apple", "b": 3}, {"a": "banana", "b": 1}, {"a": "apricot", "b": 5}],
    }]}
    # numeric "greater than or equal" 3  +  text "starts with" ap
    layout = {"views": {"summary": {"columnFilters": {
        "b": {"op": "ge", "v": "3"},
        "a": {"op": "starts", "v": "ap"},
    }}}}
    rows = apply_layout(payload, layout)["tabs"][0]["rows"]
    assert [r["a"] for r in rows] == ["apple", "apricot"]


def test_apply_layout_columnfilters_between():
    payload = {"tabs": [{
        "key": "s", "name": "S",
        "columns": [{"field": "b", "header": "B", "type": "money"}],
        "rows": [{"b": 1}, {"b": 2}, {"b": 3}, {"b": 4}],
    }]}
    layout = {"views": {"s": {"columnFilters": {"b": {"op": "between", "v": "2", "v2": "3"}}}}}
    rows = apply_layout(payload, layout)["tabs"][0]["rows"]
    assert [r["b"] for r in rows] == [2, 3]


def test_apply_layout_puts_number4_prices_before_salesman():
    payload = {"tabs": [{
        "key": "by_customer", "name": "By Customer",
        "columns": [
            {"field": "Total $", "header": "Total $", "type": "money"},
            {"field": "Avg Price", "header": "Avg Price", "type": "money"},
            {"field": "Salesman", "header": "Salesman", "type": "text"},
            {"field": "Book Price", "header": "Book Price", "type": "money"},
        ],
        "rows": [{"Total $": 10, "Avg Price": 2, "Salesman": "S", "Book Price": 3}],
    }]}
    layout = {"views": {"by_customer": {
        "order": ["Total $", "Avg Price", "Salesman", "Book Price"],
    }}}
    fields = [c["field"] for c in apply_layout(payload, layout)["tabs"][0]["columns"]]
    assert fields == ["Total $", "Avg Price", "Book Price", "Salesman"]


def test_apply_layout_moves_new_month_before_number4_trailing():
    payload = {"tabs": [{
        "key": "by_item", "name": "By Item",
        "columns": [
            {"field": "Item #", "header": "Item #", "type": "text"},
            {"field": "Jul-25 Qty", "header": "Jul-25 Qty", "type": "int"},
            {"field": "Total Qty", "header": "Total Qty", "type": "int"},
            {"field": "Total $", "header": "Total $", "type": "money"},
            {"field": "Avg Price", "header": "Avg Price", "type": "money"},
            {"field": "Book Price", "header": "Book Price", "type": "money"},
            {"field": "Salesman", "header": "Salesman", "type": "text"},
            {"field": "Sep-26 Qty", "header": "Sep-26 Qty", "type": "int"},
            {"field": "Sep-26 $", "header": "Sep-26 $", "type": "money"},
        ],
        "rows": [{}],
    }]}
    layout = {"views": {"by_item": {
        "order": ["Item #", "Jul-25 Qty", "Total Qty", "Total $", "Avg Price",
                  "Book Price", "Salesman", "Sep-26 Qty", "Sep-26 $"],
    }}}
    fields = [c["field"] for c in apply_layout(payload, layout)["tabs"][0]["columns"]]
    assert fields == [
        "Item #", "Jul-25 Qty", "Sep-26 Qty", "Sep-26 $",
        "Total Qty", "Total $", "Avg Price", "Book Price", "Salesman"]


def test_apply_layout_noop_without_views():
    assert apply_layout(_payload(), None) == _payload()
    assert apply_layout(_payload(), {"views": {}}) == _payload()


# --- email outbox + sharepoint mock ----------------------------------------

@pytest.fixture()
def email(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    cfg = _cfg(tmp_path)
    return EmailService(cfg, OutboxRepository(db), SharePointService(cfg)), cfg, db


def test_split_recipients_filters_invalid():
    assert split_recipients("a@x.com; bad, b@y.com") == ["a@x.com", "b@y.com"]
    assert split_recipients("") == []


def test_email_writes_eml_and_logs_outbox(email):
    svc, cfg, db = email
    res = svc.deliver(subject="S", recipients_raw="a@x.com", body_text="hi",
                      report_name="Ordered", filename="ordered.xlsx", xlsx_bytes=b"PK\x03\x04")
    assert res.ok and res.recipients == ["a@x.com"]
    assert res.sent_via_smtp is False
    assert (cfg.outbox_dir / res.eml_name).exists()
    row = OutboxRepository(db).get(res.outbox_id)
    assert row and row.status == "prepared" and row.attachment_meta["filename"] == "ordered.xlsx"


def test_email_text_only_has_no_attachment(email):
    svc, cfg, db = email
    res = svc.deliver(subject="Ordered Report - No Data Found (yesterday)",
                      recipients_raw="a@x.com",
                      body_text="Your requested Ordered Report for period 'yesterday' returned no results.",
                      report_name="Ordered Report", filename="", xlsx_bytes=None)
    assert res.ok
    raw = (cfg.outbox_dir / res.eml_name).read_bytes()
    assert b"vnd.openxmlformats-officedocument" not in raw
    assert b"No Data Found" in raw or b"returned no results" in raw


def test_email_sends_via_graph_when_configured(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    cfg = _cfg(tmp_path, tenant_id="t", client_id="c", client_secret="s",
               email_from="reports@x.com")

    class FakeGraph:
        def __init__(self):
            self.calls = []

        def send(self, **kwargs):
            self.calls.append(kwargs)

    graph = FakeGraph()
    svc = EmailService(cfg, OutboxRepository(db), SharePointService(cfg), graph=graph)  # type: ignore[arg-type]
    res = svc.deliver(subject="S", recipients_raw="a@x.com", body_text="hi",
                      report_name="Ordered", filename="ordered.xlsx", xlsx_bytes=b"PK\x03\x04")
    assert res.ok and res.sent_via_smtp is True
    assert res.send_channel == "graph"
    assert len(graph.calls) == 1
    assert graph.calls[0]["to"] == ["a@x.com"]
    assert OutboxRepository(db).get(res.outbox_id).status == "sent"


def test_manual_delivery_leg_uses_durable_job_id(tmp_path):
    graph = _FakeGraph()
    svc = _graph_svc(tmp_path, graph)
    res = svc.deliver(
        subject="S", recipients_raw="a@x.com", body_text="", report_name="Ordered",
        job_id="durable-job", slot_id="manual:durable-job",
    )
    leg = DeliveryLegRepository(svc.outbox.db).get_by_job("durable-job")[0]
    assert res.delivery_status == "sent"
    assert leg.slot_id == "manual:durable-job" and leg.kind == "email" and leg.status == "sent"


def test_no_data_notice_has_its_own_delivery_leg(tmp_path):
    svc = _graph_svc(tmp_path, _FakeGraph())
    delivery = DeliveryService(None, None, svc)  # type: ignore[arg-type]
    res = delivery.send_no_data_notice(
        recipients="a@x.com", subject="No data", body_text="No rows",
        report_name="Ordered", job_id="notice-job", run_id=7,
        slot_id="master:1:2026-06-01:0800",
    )
    legs = DeliveryLegRepository(svc.outbox.db).get_by_job("notice-job")
    assert res.result.ok and [(leg.kind, leg.status) for leg in legs] == [("notice", "sent")]
    assert (legs[0].run_id, legs[0].slot_id) == (7, "master:1:2026-06-01:0800")


def test_failed_no_data_notice_stays_failed(tmp_path):
    class FailedGraph(_FakeGraph):
        def send(self, **kwargs):
            raise GraphMailError("rejected", delivery_status="failed")

    svc = _graph_svc(tmp_path, FailedGraph())
    delivery = DeliveryService(None, None, svc)  # type: ignore[arg-type]
    res = delivery.send_no_data_notice(
        recipients="a@x.com", subject="No data", body_text="No rows",
        report_name="Ordered", job_id="notice-failure", slot_id="manual:notice-failure",
    )
    legs = DeliveryLegRepository(svc.outbox.db).get_by_job("notice-failure")
    assert res.result.ok is False and res.result.delivery_status == "failed"
    assert [(leg.kind, leg.status) for leg in legs] == [("notice", "failed")]


def test_dual_delivery_creates_independent_email_and_folder_legs(tmp_path):
    graph = _FakeGraph()
    svc = _graph_svc(tmp_path, graph)
    svc.sharepoint.upload_file = lambda *args: {"id": "remote-item"}  # type: ignore[method-assign]
    res = svc.deliver(
        subject="S", recipients_raw="a@x.com", body_text="", report_name="Ordered",
        filename="ordered.xlsx", xlsx_bytes=b"x", sharepoint_path="Ordered/Daily",
        job_id="dual-job", slot_id="personal:1:2026-06-01:0800",
    )
    legs = DeliveryLegRepository(svc.outbox.db).get_by_job("dual-job")
    assert res.ok and [(leg.kind, leg.status) for leg in legs] == [
        ("folder", "sent"), ("email", "sent")]
    assert {(leg.job_id, leg.slot_id) for leg in legs} == {
        ("dual-job", "personal:1:2026-06-01:0800")}


def test_folder_only_creates_one_verified_folder_leg(email):
    svc, _, db = email
    res = svc.deliver(
        subject="S", recipients_raw="", body_text="", report_name="Ordered",
        filename="ordered.xlsx", xlsx_bytes=b"x", sharepoint_path="Ordered/Daily",
        job_id="folder-job", slot_id="manual:folder-job",
    )
    legs = DeliveryLegRepository(db).get_by_job("folder-job")
    assert res.ok and [(leg.kind, leg.status) for leg in legs] == [("folder", "sent")]


def test_folder_missing_remote_item_fails_without_resending_email(tmp_path):
    graph = _FakeGraph()
    svc = _graph_svc(tmp_path, graph)
    svc.sharepoint.upload_file = lambda *args: {}  # type: ignore[method-assign]
    res = svc.deliver(
        subject="S", recipients_raw="a@x.com", body_text="", report_name="Ordered",
        filename="ordered.xlsx", xlsx_bytes=b"x", sharepoint_path="Ordered/Daily",
        job_id="missing-folder", slot_id="manual:missing-folder",
    )
    legs = DeliveryLegRepository(svc.outbox.db).get_by_job("missing-folder")
    assert res.ok and len(graph.calls) == 1
    assert [(leg.kind, leg.status) for leg in legs] == [("folder", "failed"), ("email", "sent")]


def test_email_artifact_exists_before_folder_leg_is_sending(tmp_path):
    graph = _FakeGraph()
    svc = _graph_svc(tmp_path, graph)
    updates = []
    update = svc.delivery_legs.update

    def track(leg_id, *, status, error=""):
        if status == "sending":
            updates.append(any(svc.cfg.outbox_dir.glob("*.eml")))
        update(leg_id, status=status, error=error)

    svc.delivery_legs.update = track  # type: ignore[method-assign]
    svc.deliver(
        subject="S", recipients_raw="a@x.com", body_text="", report_name="Ordered",
        filename="ordered.xlsx", xlsx_bytes=b"x", sharepoint_path="Ordered/Daily",
    )
    assert updates == [True, True]


def test_unknown_graph_delivery_keeps_unknown_leg(tmp_path):
    class ConnectionLost(_FakeGraph):
        def send(self, **kwargs):
            raise GraphMailError("connection lost", delivery_status="unknown")

    svc = _graph_svc(tmp_path, ConnectionLost())
    res = svc.deliver(
        subject="S", recipients_raw="a@x.com", body_text="", report_name="Ordered",
        job_id="unknown-job", slot_id="manual:unknown-job",
    )
    leg = DeliveryLegRepository(svc.outbox.db).get_by_job("unknown-job")[0]
    assert res.ok is False and res.delivery_status == "unknown"
    assert leg.status == "unknown"


def test_graph_mail_classifies_http_reject_and_connection_loss(monkeypatch):
    mailer = GraphMailer("tenant", "client", "secret")
    monkeypatch.setattr(mailer, "_token", lambda: "token")
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b""

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response())
    assert mailer.send(sender="reports@x.com", to=["a@x.com"], subject="S", body_text="") is None

    request_error = urllib.error.HTTPError(
        "https://graph.example", 400, "bad request", {}, io.BytesIO(b"rejected"),
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(request_error))
    with pytest.raises(GraphMailError) as rejected:
        mailer.send(sender="reports@x.com", to=["a@x.com"], subject="S", body_text="")
    assert rejected.value.delivery_status == "failed"

    lost_calls = []
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: lost_calls.append(1) or (_ for _ in ()).throw(TimeoutError("connection lost")),
    )
    with pytest.raises(GraphMailError) as unknown:
        mailer.send(sender="reports@x.com", to=["a@x.com"], subject="S", body_text="")
    assert unknown.value.delivery_status == "unknown"
    assert lost_calls == [1]


def test_email_requires_a_target(email):
    svc, *_ = email
    res = svc.deliver(subject="S", recipients_raw="nope", body_text="",
                      report_name="R", filename="r.xlsx", xlsx_bytes=b"x")
    assert res.ok is False and "recipient" in res.error.lower()


def test_email_uploads_to_sharepoint_mock(email):
    svc, *_ = email
    res = svc.deliver(subject="S", recipients_raw="a@x.com", body_text="",
                      report_name="R", filename="r.xlsx", xlsx_bytes=b"x",
                      sharepoint_path="Ordered/Daily")
    assert res.sharepoint_saved is True and res.sharepoint_url.startswith("mock://")


class _FakeGraph:
    def __init__(self):
        self.calls = []

    def send(self, **kwargs):
        self.calls.append(kwargs)


def _graph_svc(tmp_path, graph):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    cfg = _cfg(tmp_path, tenant_id="t", client_id="c", client_secret="s",
               email_from="reports@x.com")
    return EmailService(cfg, OutboxRepository(db), SharePointService(cfg), graph=graph)


def test_graph_omits_attachment_when_workbook_too_large(tmp_path):
    graph = _FakeGraph()
    svc = _graph_svc(tmp_path, graph)
    svc.sharepoint.upload_file = (  # type: ignore[method-assign]
        lambda folder, name, content: {
            "webUrl": f"mock://{folder}/{name}", "name": name, "id": "1",
        }
    )
    big = b"P" * MAX_GRAPH_ATTACH_BYTES
    res = svc.deliver(subject="YTD Ordered", recipients_raw="a@x.com", body_text="",
                      report_name="Ordered", filename="Ordered_Report_YTD.xlsx",
                      xlsx_bytes=big, sharepoint_path="Ordered/YTD")
    assert res.ok and res.send_channel == "graph"
    assert graph.calls[0]["xlsx_bytes"] is None
    assert graph.calls[0]["filename"] == ""
    assert "too large" in graph.calls[0]["body_text"].lower()
    assert "mock://Ordered/YTD/Ordered_Report_YTD.xlsx" in graph.calls[0]["body_text"]
    html = graph.calls[0]["body_html"]
    assert "Download workbook" in html
    assert "mock://Ordered/YTD/Ordered_Report_YTD.xlsx" in html
    assert "#2563eb" in html
    assert res.sharepoint_saved is True


def test_graph_oversize_without_folder_uploads_fallback_and_html_button(tmp_path):
    graph = _FakeGraph()
    svc = _graph_svc(tmp_path, graph)
    folders = []

    def up(folder, name, content):
        folders.append(folder)
        return {"webUrl": f"https://achim.sharepoint.com/{folder}/{name}",
                "name": name, "id": "1"}

    svc.sharepoint.upload_file = up  # type: ignore[method-assign]
    big = b"P" * MAX_GRAPH_ATTACH_BYTES
    res = svc.deliver(
        subject="Daily 5am Number 4", recipients_raw="a@x.com", body_text="",
        report_name="Number 4", filename="Daily_5am_Number_4.xlsx",
        xlsx_bytes=big, sharepoint_path="",
        job_id="oversize-fallback", slot_id="manual:oversize-fallback",
    )
    assert res.ok and res.send_channel == "graph"
    assert folders == [TEST_SHAREPOINT_FOLDER]
    url = "https://achim.sharepoint.com/Test/Daily_5am_Number_4.xlsx"
    assert url in graph.calls[0]["body_text"]
    html = graph.calls[0]["body_html"]
    assert "Download workbook" in html
    assert url in html
    assert graph.calls[0]["xlsx_bytes"] is None
    assert res.sharepoint_saved is True
    assert res.sharepoint_url == url
    legs = DeliveryLegRepository(svc.outbox.db).get_by_job("oversize-fallback")
    assert [(leg.kind, leg.status) for leg in legs] == [("folder", "sent"), ("email", "sent")]


def test_graph_oversize_fallback_upload_failure_still_sends_email(tmp_path):
    graph = _FakeGraph()
    svc = _graph_svc(tmp_path, graph)

    def boom(*a, **k):
        raise RuntimeError("graph 500")

    svc.sharepoint.upload_file = boom  # type: ignore[method-assign]
    big = b"P" * MAX_GRAPH_ATTACH_BYTES
    res = svc.deliver(
        subject="S", recipients_raw="a@x.com", body_text="",
        report_name="Ordered", filename="big.xlsx", xlsx_bytes=big,
        job_id="oversize-fail", slot_id="manual:oversize-fail",
    )
    assert res.ok and res.send_channel == "graph"
    assert graph.calls[0]["xlsx_bytes"] is None
    assert "Download it from SharePoint" in graph.calls[0]["body_text"]
    assert graph.calls[0]["body_html"] is None
    assert res.sharepoint_saved is False
    legs = DeliveryLegRepository(svc.outbox.db).get_by_job("oversize-fail")
    assert [(leg.kind, leg.status) for leg in legs] == [("folder", "failed"), ("email", "sent")]


def test_graph_retries_without_attachment_after_413_includes_link(tmp_path):
    class RejectThenOk(_FakeGraph):
        def send(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("xlsx_bytes"):
                raise GraphMailError("Microsoft Graph rejected the send (HTTP 413).",
                                     status_code=413)

    graph = RejectThenOk()
    svc = _graph_svc(tmp_path, graph)
    svc.sharepoint.upload_file = (  # type: ignore[method-assign]
        lambda folder, name, content: {
            "webUrl": f"https://achim.sharepoint.com/{folder}/{name}",
            "name": name, "id": "1",
        }
    )
    res = svc.deliver(subject="S", recipients_raw="a@x.com", body_text="hi",
                      report_name="Ordered", filename="ordered.xlsx",
                      xlsx_bytes=b"PK\x03\x04",
                      job_id="graph-413", slot_id="manual:graph-413")
    assert res.ok and res.send_channel == "graph"
    assert len(graph.calls) == 2
    assert graph.calls[0]["xlsx_bytes"] == b"PK\x03\x04"
    assert graph.calls[1]["xlsx_bytes"] is None
    url = "https://achim.sharepoint.com/Test/ordered.xlsx"
    assert url in graph.calls[1]["body_text"]
    assert "Download workbook" in graph.calls[1]["body_html"]
    assert url in graph.calls[1]["body_html"]
    assert res.sharepoint_url == url
    legs = DeliveryLegRepository(svc.outbox.db).get_by_job("graph-413")
    assert {(leg.kind, leg.status) for leg in legs} == {("email", "sent"), ("folder", "sent")}


def test_sharepoint_mock_lists_folders(tmp_path):
    sp = SharePointService(_cfg(tmp_path))
    assert sp.is_configured() is False
    names = [f["name"] for f in sp.list_folders("")]
    assert "Ordered" in names and "Invoiced" in names


def test_sharepoint_only_failure_fails_the_delivery(email):
    svc, *_ = email
    # Force the (mock) upload to fail: a SharePoint-only send must NOT report ok.
    def boom(*a, **k):
        raise RuntimeError("graph 500")
    svc.sharepoint.upload_file = boom  # type: ignore[method-assign]
    res = svc.deliver(subject="S", recipients_raw="", body_text="",
                      report_name="R", filename="r.xlsx", xlsx_bytes=b"x",
                      sharepoint_path="Ordered/Daily")
    assert res.ok is False
    assert "graph 500" in (res.error or "") or "SharePoint" in (res.error or "")


def test_email_sent_keeps_ok_when_sharepoint_fails(email):
    svc, *_ = email
    def boom(*a, **k):
        raise RuntimeError("graph down")
    svc.sharepoint.upload_file = boom  # type: ignore[method-assign]
    res = svc.deliver(subject="S", recipients_raw="a@x.com", body_text="",
                      report_name="R", filename="r.xlsx", xlsx_bytes=b"x",
                      sharepoint_path="Ordered/Daily")
    assert res.ok is True
    assert res.sharepoint_saved is False
    assert "graph down" in (res.sharepoint_error or "")


def test_graph_send_then_sharepoint_fail_does_not_mark_failed(tmp_path):
    graph = _FakeGraph()
    svc = _graph_svc(tmp_path, graph)

    def boom(*a, **k):
        raise RuntimeError("Test folder 500")
    svc.sharepoint.upload_file = boom  # type: ignore[method-assign]
    res = svc.deliver(subject="[TEST] Nightly", recipients_raw="menny@x.com",
                      body_text="", report_name="Ordered", filename="r.xlsx",
                      xlsx_bytes=b"x", sharepoint_path=TEST_SHAREPOINT_FOLDER)
    assert res.ok is True
    assert res.send_channel == "graph"
    assert len(graph.calls) == 1
    assert res.sharepoint_saved is False
    assert "Test folder 500" in (res.sharepoint_error or "")


def test_sharepoint_rejects_path_traversal(tmp_path):
    from web.delivery.sharepoint import _validate_segments

    with pytest.raises(ValueError):
        _validate_segments("Ordered/../../etc")
    with pytest.raises(ValueError):
        _validate_segments("Ordered/Da:ily")
    assert _validate_segments("Ordered/Daily") == ["Ordered", "Daily"]


def test_strip_reports_home_drops_duplicated_prefix():
    from web.delivery.sharepoint import strip_reports_home

    assert strip_reports_home("Direct Reports/Salesman Report/Daily") == "Salesman Report/Daily"
    assert strip_reports_home("Direct Reports/Direct Reports/Ordered") == "Ordered"
    assert strip_reports_home("Direct Reports") == ""
    assert strip_reports_home("Salesman Report/Customer Activity") == "Salesman Report/Customer Activity"


def test_sharepoint_list_and_upload_strip_home_prefix(tmp_path):
    sp = SharePointService(_cfg(tmp_path))
    names = [f["name"] for f in sp.list_folders("Direct Reports")]
    assert "Ordered" in names
    res = sp.upload_file("Direct Reports/Salesman Report/Customer Activity", "f.xlsx", b"x")
    assert res["webUrl"] == "mock://Salesman Report/Customer Activity/f.xlsx"


def test_upload_drive_item_uses_session_over_4mb():
    from web.delivery.graph_upload import SIMPLE_UPLOAD_MAX, upload_drive_item

    class _Resp:
        def __init__(self, status, payload=None):
            self.status_code = status
            self._payload = payload or {}

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

    class _Req:
        def __init__(self):
            self.puts = []
            self.posts = []

        def put(self, url, **kwargs):
            self.puts.append((url, kwargs))
            return _Resp(200, {"webUrl": "https://sp/file", "name": "f.xlsx", "id": "1"})

        def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            return _Resp(200, {"uploadUrl": "https://upload/session"})

    req = _Req()
    small = upload_drive_item(
        req, put_url="https://graph/content", session_url="https://graph/session",
        headers={"Authorization": "Bearer t"}, content=b"hello", put_timeout=10,
    )
    assert small["webUrl"] == "https://sp/file"
    assert req.posts == []

    req = _Req()
    big = upload_drive_item(
        req, put_url="https://graph/content", session_url="https://graph/session",
        headers={"Authorization": "Bearer t"},
        content=b"x" * SIMPLE_UPLOAD_MAX, put_timeout=10,
    )
    assert big["webUrl"] == "https://sp/file"
    assert req.posts[0][0] == "https://graph/session"
    assert req.puts[0][0] == "https://upload/session"


def test_resolve_web_url_from_body_get_then_create_link():
    from web.delivery.graph_upload import resolve_web_url, web_url_from_item

    class _Resp:
        def __init__(self, payload, ok=True):
            self.ok = ok
            self._payload = payload

        def json(self):
            return self._payload

    class _Req:
        def __init__(self, get_payload=None, post_payload=None, get_ok=True):
            self.get_payload = get_payload or {}
            self.post_payload = post_payload or {}
            self.get_ok = get_ok
            self.gets = []
            self.posts = []

        def get(self, url, **kwargs):
            self.gets.append(url)
            return _Resp(self.get_payload, ok=self.get_ok)

        def post(self, url, **kwargs):
            self.posts.append((url, kwargs.get("json")))
            return _Resp(self.post_payload)

    assert web_url_from_item({"link": {"webUrl": "https://from-link"}}) == "https://from-link"
    assert resolve_web_url(
        _Req(), headers={}, body={"webUrl": "https://from-body"},
        get_url="https://g", items_base="https://i", timeout=1,
    ) == "https://from-body"

    req = _Req(get_payload={"webUrl": "https://from-get", "id": "x"})
    assert resolve_web_url(
        req, headers={}, body={"id": "x"},
        get_url="https://g", items_base="https://i", timeout=1,
    ) == "https://from-get"
    assert req.gets == ["https://i/x"]
    assert req.posts == []

    req = _Req(get_payload={"id": "x"}, post_payload={"link": {"webUrl": "https://from-link"}})
    assert resolve_web_url(
        req, headers={}, body={},
        get_url="https://g", items_base="https://i", timeout=1,
    ) == "https://from-link"
    assert req.posts == [("https://i/x/createLink",
                          {"type": "view", "scope": "organization"})]


def test_resolve_web_url_gets_item_by_id_when_path_get_fails():
    from web.delivery.graph_upload import resolve_web_url

    class _Resp:
        def __init__(self, payload, ok=True):
            self.ok = ok
            self._payload = payload

        def json(self):
            return self._payload

    class _Req:
        def __init__(self):
            self.gets = []
            self.posts = []

        def get(self, url, **kwargs):
            self.gets.append(url)
            if url.endswith("/item1"):
                return _Resp({"id": "item1", "webUrl": "https://sp/n4.xlsx"})
            return _Resp({}, ok=False)

        def post(self, url, **kwargs):
            self.posts.append(url)
            return _Resp({}, ok=False)

    req = _Req()
    assert resolve_web_url(
        req, headers={}, body={"id": "item1"},
        get_url="https://graph/root:/Test/n4.xlsx",
        items_base="https://graph/items", timeout=1,
    ) == "https://sp/n4.xlsx"
    assert req.gets == ["https://graph/items/item1"]
    assert req.posts == []


def test_resolve_web_url_retries_path_get_with_trailing_colon():
    from web.delivery.graph_upload import resolve_web_url

    class _Resp:
        def __init__(self, payload, ok=True):
            self.ok = ok
            self._payload = payload

        def json(self):
            return self._payload

    class _Req:
        def __init__(self):
            self.gets = []

        def get(self, url, **kwargs):
            self.gets.append(url)
            if url.endswith(":"):
                return _Resp({"webUrl": "https://from-colon-path", "id": "z"})
            return _Resp({}, ok=False)

        def post(self, url, **kwargs):
            raise AssertionError("createLink should not run")

    req = _Req()
    body = {"expirationDateTime": "2026-09-02T12:00:00Z", "nextExpectedRanges": []}
    assert resolve_web_url(
        req, headers={}, body=body,
        get_url="https://graph/root:/Direct%20Reports/Test/n4.xlsx",
        items_base="https://graph/items", timeout=1,
    ) == "https://from-colon-path"
    assert "https://graph/root:/Direct%20Reports/Test/n4.xlsx:" in req.gets


def test_graph_oversize_upload_without_weburl_names_the_folder(tmp_path):
    graph = _FakeGraph()
    svc = _graph_svc(tmp_path, graph)
    svc.sharepoint.upload_file = (  # type: ignore[method-assign]
        lambda folder, name, content: {"webUrl": None, "name": name, "id": "1"}
    )
    big = b"P" * MAX_GRAPH_ATTACH_BYTES
    res = svc.deliver(
        subject="Daily 5am Number 4", recipients_raw="a@x.com", body_text="",
        report_name="Number 4", filename="Daily_5am_Number_4.xlsx",
        xlsx_bytes=big, sharepoint_path="",
    )
    assert res.ok and res.send_channel == "graph"
    body = graph.calls[0]["body_text"]
    assert "too large" in body.lower()
    assert "Direct Reports/Test/Daily_5am_Number_4.xlsx" in body
    assert graph.calls[0]["body_html"] is None
    assert res.sharepoint_saved is True
    assert res.sharepoint_url is None


def test_sharepoint_prod_without_creds_raises(tmp_path):
    sp = SharePointService(_cfg(tmp_path, app_env="prod",
                                tenant_id="", client_id="", client_secret=""))
    assert sp.is_configured() is False
    with pytest.raises(RuntimeError):
        sp.upload_file("Ordered", "r.xlsx", b"x")


def test_onedrive_children_url_root_is_not_double_colon():
    url = onedrive_children_url("mennyg@achimonline.com", "")
    assert url.endswith("/drive/root/children")
    assert "root::" not in url


def test_onedrive_children_url_nested_uses_colon_path():
    url = onedrive_children_url("mennyg@achimonline.com", "Reports/2026")
    assert "/drive/root:/Reports/2026:/children" in url


# --- orchestration ---------------------------------------------------------

def test_delivery_service_builds_applies_layout_and_delivers(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    cfg = _cfg(tmp_path)
    email = EmailService(cfg, OutboxRepository(db), SharePointService(cfg))

    from web.reporting.cache import ReportCache
    from web.reporting.runner import ReportRunner

    payload = {"tabs": [{"key": "t", "name": "T",
                         "columns": [{"field": "a"}, {"field": "b"}],
                         "rows": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]}]}
    runner = ReportRunner(ReportCache(db))
    svc = DeliveryService(runner, lambda key: (lambda params, vk: payload), email)
    outcome = svc.run_and_deliver(
        report_key="ordered", identity="u@x.com", visible_salesman_keys=None,
        builder_version=1, params={}, layout={"views": {"t": {"hidden": ["a"]}}},
        recipients="a@x.com", subject="S", report_name="Ordered", sharepoint_path="",
    )
    assert outcome.result.ok and outcome.row_count == 2
    assert OutboxRepository(db).get(outcome.result.outbox_id) is not None


def test_delivery_stamps_skip_commissions_when_layout_drops_that_tab(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    cfg = _cfg(tmp_path)
    email = EmailService(cfg, OutboxRepository(db), SharePointService(cfg))

    from web.reporting.cache import ReportCache
    from web.reporting.runner import ReportRunner

    seen = {}
    payload = {"tabs": [
        {"key": "summary_by_customer", "name": "Summary", "columns": [{"field": "a"}], "rows": [{"a": 1}]},
        {"key": "commissions", "name": "Commissions", "columns": [{"field": "a"}], "rows": [{"a": 2}]},
        {"key": "invoices", "name": "Invoices", "columns": [{"field": "a"}], "rows": [{"a": 3}]},
    ]}

    def builder(params, vk):
        seen["params"] = params
        return payload

    runner = ReportRunner(ReportCache(db))
    svc = DeliveryService(runner, lambda key: builder, email)
    layout = {"order": ["summary_by_customer", "invoices"]}
    outcome = svc.run_and_deliver(
        report_key="invoiced", identity="u@x.com", visible_salesman_keys=None,
        builder_version=1, params={"period": "yesterday"}, layout=layout,
        recipients="a@x.com", subject="S", report_name="Invoiced", sharepoint_path="",
    )
    assert seen["params"].get("_skip_commissions") is True
    assert outcome.result.ok


def test_delivery_expands_folder_tokens_and_strips_home(tmp_path, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    frozen = datetime(2026, 8, 19, 12, 0, tzinfo=ZoneInfo("America/New_York"))

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen if tz is None else frozen.astimezone(tz)

    monkeypatch.setattr("web.delivery.filename_template.datetime", FrozenDateTime)

    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    cfg = _cfg(tmp_path)
    email = EmailService(cfg, OutboxRepository(db), SharePointService(cfg))
    seen = {}
    orig = email.deliver

    def wrap(**kwargs):
        seen["sharepoint_path"] = kwargs.get("sharepoint_path")
        return orig(**kwargs)

    email.deliver = wrap  # type: ignore[method-assign]

    from web.reporting.cache import ReportCache
    from web.reporting.runner import ReportRunner

    payload = {"tabs": [{"key": "t", "name": "T",
                         "columns": [{"field": "a"}],
                         "rows": [{"a": 1}]}]}
    svc = DeliveryService(
        ReportRunner(ReportCache(db)), lambda key: (lambda params, vk: payload), email,
    )
    outcome = svc.run_and_deliver(
        report_key="customer_activity", identity="u@x.com", visible_salesman_keys=None,
        builder_version=1, params={}, layout={},
        recipients="a@x.com", subject="S", report_name="Customer Activity",
        sharepoint_path="Direct Reports/Salesman Report/Customer Activity/{Month} {YYYY}",
    )
    assert outcome.result.ok
    assert seen["sharepoint_path"] == "Salesman Report/Customer Activity/August 2026"


def test_graph_token_cache_refreshes_before_expiry(monkeypatch):
    from web.delivery.graph_auth import GraphTokenCache

    now = [100.0]
    monkeypatch.setattr("web.delivery.graph_auth.time.monotonic", lambda: now[0])
    tokens = iter([
        {"access_token": "first", "expires_in": 120},
        {"access_token": "second", "expires_in": 120},
    ])
    cache = GraphTokenCache()
    assert cache.get(lambda: next(tokens)) == "first"
    now[0] = 150.0
    assert cache.get(lambda: next(tokens)) == "first"
    now[0] = 160.0
    assert cache.get(lambda: next(tokens)) == "second"


def test_sharepoint_get_401_refreshes_token_once(tmp_path, monkeypatch):
    service = SharePointService(_cfg(tmp_path, tenant_id="tenant", client_id="client", client_secret="secret"))
    service._drive_id = "drive"
    token_calls = []
    monkeypatch.setattr(service, "_get_token", lambda refresh=False: token_calls.append(refresh) or "new")

    class Response:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

    responses = iter([Response(401, {}), Response(200, {"value": []})])
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: next(responses))
    assert service.list_folders() == []
    assert token_calls == [False, True]


def test_graph_mail_retries_rejected_401_once_with_fresh_token(monkeypatch):
    mailer = GraphMailer("tenant", "client", "secret")
    tokens = iter(["old", "new"])
    monkeypatch.setattr(mailer, "_token", lambda: next(tokens))
    cleared = []
    monkeypatch.setattr(mailer, "_clear_token", lambda: cleared.append(True))
    authorizations = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b""

    def send(request, **kwargs):
        authorizations.append(request.get_header("Authorization"))
        if len(authorizations) == 1:
            raise urllib.error.HTTPError("https://graph.example", 401, "unauthorized", {}, io.BytesIO())
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", send)
    mailer.send(sender="reports@x.com", to=["a@x.com"], subject="S", body_text="")
    assert authorizations == ["Bearer old", "Bearer new"]
    assert cleared == [True]


@pytest.mark.parametrize("status_code", [429, 503])
def test_graph_throttle_waits_once_with_capped_retry_after(monkeypatch, status_code):
    from web.delivery.graph_auth import retry_graph_response

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.headers = {"Retry-After": "300"}

    responses = iter([Response(status_code), Response(200)])
    delays = []
    monkeypatch.setattr("web.delivery.graph_auth.time.sleep", delays.append)
    assert retry_graph_response(lambda token: next(responses), lambda refresh: "token").status_code == 200
    assert delays == [60]


def test_graph_throttle_then_401_refreshes_token_once(monkeypatch):
    from web.delivery.graph_auth import retry_graph_response

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.headers = {"Retry-After": "1"}

    responses = iter([Response(429), Response(401), Response(200)])
    token_calls = []
    monkeypatch.setattr("web.delivery.graph_auth.time.sleep", lambda *_: None)
    assert retry_graph_response(
        lambda _token: next(responses),
        lambda refresh: token_calls.append(refresh) or ("fresh" if refresh else "stale"),
    ).status_code == 200
    assert token_calls == [False, False, True]


def test_graph_401_then_throttle_retries_once(monkeypatch):
    from web.delivery.graph_auth import retry_graph_response

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.headers = {"Retry-After": "1"}

    responses = iter([Response(401), Response(429), Response(200)])
    token_calls = []
    delays = []
    monkeypatch.setattr("web.delivery.graph_auth.time.sleep", delays.append)
    assert retry_graph_response(
        lambda _token: next(responses),
        lambda refresh: token_calls.append(refresh) or ("fresh" if refresh else "stale"),
    ).status_code == 200
    assert token_calls == [False, True, False]
    assert delays == [1]


def test_folder_put_401_uses_a_fresh_token():
    from web.delivery.graph_upload import upload_drive_item

    class Response:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {}
            self.headers = {}

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

    class Requests:
        def __init__(self):
            self.headers = []

        def put(self, url, **kwargs):
            self.headers.append(kwargs["headers"]["Authorization"])
            return Response(401 if len(self.headers) == 1 else 200, {"id": "item"})

    requests = Requests()
    refreshes = []
    assert upload_drive_item(
        requests, put_url="https://graph/content", session_url="unused",
        headers={"Authorization": "Bearer stale"}, content=b"file", put_timeout=10,
        token=lambda refresh: refreshes.append(refresh) or ("fresh" if refresh else "stale"),
    ) == {"id": "item"}
    assert refreshes == [False, True]
    assert requests.headers == ["Bearer stale", "Bearer fresh"]


def test_upload_session_resumes_at_graph_next_expected_range():
    from web.delivery.graph_upload import CHUNK_SIZE, SIMPLE_UPLOAD_MAX, upload_drive_item

    class Response:
        status_code = 200

        def __init__(self, payload=None):
            self._payload = payload or {}

        def json(self):
            return self._payload

        def raise_for_status(self):
            return None

    class Requests:
        def __init__(self):
            self.puts = []

        def post(self, *args, **kwargs):
            return Response({"uploadUrl": "https://upload/session"})

        def put(self, url, **kwargs):
            self.puts.append(kwargs["headers"]["Content-Range"])
            if len(self.puts) == 1:
                raise RuntimeError("connection reset")
            return Response({"id": "item"})

        def get(self, url, **kwargs):
            return Response({"nextExpectedRanges": [f"{CHUNK_SIZE}-"]})

    requests = Requests()
    upload_drive_item(
        requests, put_url="https://graph/content", session_url="https://graph/session",
        headers={"Authorization": "Bearer token"}, content=b"x" * SIMPLE_UPLOAD_MAX,
        put_timeout=10,
    )
    assert requests.puts[0].startswith("bytes 0-")
    assert requests.puts[1].startswith(f"bytes {CHUNK_SIZE}-")


def test_retry_after_uses_http_date_and_default():
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime
    from web.delivery.graph_auth import retry_after_seconds

    assert retry_after_seconds(None) == 1
    far = datetime.now(UTC) + timedelta(seconds=300)
    assert retry_after_seconds(format_datetime(far, usegmt=True)) == 60
    soon = datetime.now(UTC) + timedelta(seconds=12)
    delay = retry_after_seconds(format_datetime(soon, usegmt=True))
    assert 1 <= delay <= 12


def test_graph_mail_retries_throttle_once(monkeypatch):
    mailer = GraphMailer("tenant", "client", "secret")
    monkeypatch.setattr(mailer, "_token", lambda: "token")
    delays = []
    monkeypatch.setattr("web.delivery.graph_mail.time.sleep", delays.append)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b""

    calls = []

    def send(request, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                "https://graph.example", 429, "throttle", {"Retry-After": "300"}, io.BytesIO(),
            )
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", send)
    mailer.send(sender="reports@x.com", to=["a@x.com"], subject="S", body_text="")
    assert calls == [1, 1]
    assert delays == [60]


def test_sharepoint_folder_create_401_refreshes_token_once(tmp_path, monkeypatch):
    service = SharePointService(_cfg(
        tmp_path, tenant_id="tenant", client_id="client", client_secret="secret",
    ))
    service._drive_id = "drive"
    token_calls = []
    monkeypatch.setattr(
        service, "_get_token",
        lambda refresh=False: token_calls.append(refresh) or ("fresh" if refresh else "stale"),
    )

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.headers = {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

    posts = []

    def post(url, **kwargs):
        posts.append(kwargs["headers"]["Authorization"])
        if len(posts) == 1:
            return Response(401)
        return Response(201)

    monkeypatch.setattr("requests.post", post)
    service._ensure_folder("")
    assert posts[0] == "Bearer stale"
    assert posts[1] == "Bearer fresh"
    assert token_calls[:2] == [False, True]
