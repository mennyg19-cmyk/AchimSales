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
from web.delivery.sharepoint import SharePointService


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
    assert (cfg.outbox_dir / res.eml_name).exists()
    row = OutboxRepository(db).get(res.outbox_id)
    assert row and row.status == "outbox" and row.attachment_meta["filename"] == "ordered.xlsx"


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


def _graph_svc(tmp_path, graph):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    cfg = _cfg(tmp_path, tenant_id="t", client_id="c", client_secret="s",
               email_from="reports@x.com")
    return EmailService(cfg, OutboxRepository(db), SharePointService(cfg), graph=graph)


class _FakeGraph:
    def __init__(self):
        self.calls = []

    def send(self, **kwargs):
        self.calls.append(kwargs)


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
    body = graph.calls[0]["body_text"].lower()
    assert "too large" in body
    assert "mock://Ordered/YTD/Ordered_Report_YTD.xlsx" in graph.calls[0]["body_text"]
    assert res.sharepoint_saved is True


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


def test_sharepoint_prod_without_creds_raises(tmp_path):
    sp = SharePointService(_cfg(tmp_path, app_env="prod",
                                tenant_id="", client_id="", client_secret=""))
    assert sp.is_configured() is False
    with pytest.raises(RuntimeError):
        sp.upload_file("Ordered", "r.xlsx", b"x")


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
    assert req.puts[0][0] == "https://graph/content"

    req = _Req()
    big = upload_drive_item(
        req, put_url="https://graph/content", session_url="https://graph/session",
        headers={"Authorization": "Bearer t"},
        content=b"x" * SIMPLE_UPLOAD_MAX, put_timeout=10,
    )
    assert big["webUrl"] == "https://sp/file"
    assert req.posts[0][0] == "https://graph/session"
    assert req.puts[0][0] == "https://upload/session"
    assert "Content-Range" in req.puts[0][1]["headers"]


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
    svc = DeliveryService(runner, lambda key: (lambda params: payload), email)
    outcome = svc.run_and_deliver(
        report_key="ordered", identity="u@x.com", visible_salesman_keys=None,
        builder_version=1, params={}, layout={"views": {"t": {"hidden": ["a"]}}},
        recipients="a@x.com", subject="S", report_name="Ordered", sharepoint_path="",
    )
    assert outcome.result.ok and outcome.row_count == 2
    assert OutboxRepository(db).get(outcome.result.outbox_id) is not None
