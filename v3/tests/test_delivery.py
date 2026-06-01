"""Delivery subsystem: layout replay, email outbox, SharePoint mock, orchestration."""

from __future__ import annotations

import pytest

from web.config import Config
from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.outbox import OutboxRepository
from web.delivery.email import EmailService, split_recipients
from web.delivery.layout import apply_layout
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


def test_sharepoint_mock_lists_folders(tmp_path):
    sp = SharePointService(_cfg(tmp_path))
    assert sp.is_configured() is False
    names = [f["name"] for f in sp.list_folders("")]
    assert "Ordered" in names and "Invoiced" in names


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
