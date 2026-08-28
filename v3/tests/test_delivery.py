"""Delivery subsystem: layout replay, email outbox, SharePoint mock, orchestration."""

from __future__ import annotations

import pytest

from web.config import Config
from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.outbox import OutboxRepository
from web.delivery.email import MAX_GRAPH_ATTACH_BYTES, EmailService, split_recipients
from web.delivery.graph_mail import GraphMailError
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
        litestream_blob_url="", outbox_dir=tmp_path / "outbox",
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
    assert row and row.status == "outbox" and row.attachment_meta["filename"] == "ordered.xlsx"


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
    )
    assert res.ok and res.send_channel == "graph"
    assert graph.calls[0]["xlsx_bytes"] is None
    assert "Download it from SharePoint" in graph.calls[0]["body_text"]
    assert graph.calls[0]["body_html"] is None
    assert res.sharepoint_saved is False


def test_graph_retries_without_attachment_after_413(tmp_path):
    class RejectThenOk(_FakeGraph):
        def send(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("xlsx_bytes"):
                raise GraphMailError("Microsoft Graph rejected the send (HTTP 413).",
                                     status_code=413)

    graph = RejectThenOk()
    svc = _graph_svc(tmp_path, graph)
    res = svc.deliver(subject="S", recipients_raw="a@x.com", body_text="hi",
                      report_name="Ordered", filename="ordered.xlsx",
                      xlsx_bytes=b"PK\x03\x04")
    assert res.ok and res.send_channel == "graph"
    assert len(graph.calls) == 2
    assert graph.calls[0]["xlsx_bytes"] == b"PK\x03\x04"
    assert graph.calls[1]["xlsx_bytes"] is None
    assert "too large" in graph.calls[1]["body_text"].lower()


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


def test_email_ok_but_sharepoint_failure_still_fails(email):
    svc, *_ = email
    def boom(*a, **k):
        raise RuntimeError("graph down")
    svc.sharepoint.upload_file = boom  # type: ignore[method-assign]
    res = svc.deliver(subject="S", recipients_raw="a@x.com", body_text="",
                      report_name="R", filename="r.xlsx", xlsx_bytes=b"x",
                      sharepoint_path="Ordered/Daily")
    # A requested target failed -> the whole delivery is a failure (surfaced to the job).
    assert res.ok is False


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
