"""SQL coverage and Beta report-source defaults."""

import sqlite3
from pathlib import Path

from report_engine.registry import ReportStatus, backlog_reports, built_reports
from web import beta_sources
from web.reporting.report_service import _ORCHESTRATORS


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
