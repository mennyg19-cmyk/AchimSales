"""SQL coverage and Beta report-source defaults."""

import sqlite3
from types import SimpleNamespace
from pathlib import Path

from flask import Flask

from report_engine.registry import ReportStatus, backlog_reports, built_reports
from web import beta_sources
from web.reporting.cache import build_cache_key
from web.reporting.report_service import ReportService, _ORCHESTRATORS


def test_every_built_report_has_a_sql_path():
    for report in built_reports():
        assert report.key in _ORCHESTRATORS or report.key == "customer_last_order"
    assert [report.key for report in backlog_reports()] == ["customer_aging"]
    assert backlog_reports()[0].status is ReportStatus.BACKLOG


def test_sql_backed_hybrid_reports_default_to_sql():
    sources = beta_sources.default_sources()
    assert sources["item_averages"] == "sql"
    assert sources["number_4"] == "sql"
    assert sources["customer_last_order"] == "sql"
    assert sources["customer_aging"] == "odata"
    assert beta_sources.get_source("sales_by_state") == "sql"


def test_ensure_schema_upgrades_existing_item_averages_source(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from webapp import db as live_db

    db_path = tmp_path / "live.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE beta_report_sources (
                   report_key TEXT PRIMARY KEY,
                   source TEXT NOT NULL CHECK(source IN ('sql', 'odata')),
                   updated_at TEXT NOT NULL DEFAULT (datetime('now'))
               )"""
        )
        conn.execute(
            "INSERT INTO beta_report_sources (report_key, source) VALUES (?, ?)",
            ("item_averages", "odata"),
        )

    def get_test_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(live_db, "get_db", get_test_db)

    assert beta_sources.get_source("item_averages") == "sql"


def test_beta_builder_uses_sql_when_source_map_says_odata(monkeypatch):
    class Client:
        def run_report(self, report_id, params):
            assert report_id == "item_customer_sales_rolling_12"
            return SimpleNamespace(rows=[
                {"Item #": "A", "Item Name": "Alpha", "Total Qty": 12},
            ])

    monkeypatch.setattr(beta_sources, "get_source", lambda report_key: "odata")
    app = Flask(__name__)
    app.config["APP_CONFIG"] = SimpleNamespace(is_beta=True)
    with app.app_context():
        payload = ReportService(Client(), salesmen_repo=None).builder_for("item_averages")({}, None)

    assert payload["report_key"] == "item_averages"
    assert "data_source" not in payload


def test_sql_cutover_bumps_only_builder_cache_namespace():
    versions = {report.key: report.builder_version for report in built_reports()}
    assert {key: versions[key] for key in (
        "ordered", "invoiced", "salesman", "number_4", "customer_activity", "item_averages",
    )} == {
        "ordered": 9, "invoiced": 2, "salesman": 2, "number_4": 6,
        "customer_activity": 2, "item_averages": 2,
    }
    shared = {"report_key": "ordered", "identity": "dev@x.com", "scope_token": "ALL",
              "params": {"period": "ytd"}}
    assert build_cache_key(builder_version=8, **shared) != build_cache_key(
        builder_version=9, **shared)
