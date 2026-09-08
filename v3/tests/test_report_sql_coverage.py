"""SQL coverage for every built report."""

import sys
from types import SimpleNamespace

from flask import Flask

from report_engine.registry import ReportStatus, backlog_reports, built_reports
from web.reporting.cache import build_cache_key
from web.reporting.report_service import ReportService, _ORCHESTRATORS


def test_every_built_report_has_a_sql_path():
    for report in built_reports():
        assert report.key in _ORCHESTRATORS or report.key == "customer_last_order"
    assert [report.key for report in backlog_reports()] == ["customer_aging"]
    assert backlog_reports()[0].status is ReportStatus.BACKLOG


def test_beta_builder_uses_sql():
    class Client:
        def run_report(self, report_id, params):
            assert report_id == "item_customer_sales_rolling_12"
            return SimpleNamespace(rows=[
                {"Item #": "A", "Item Name": "Alpha", "Total Qty": 12},
            ])

    app = Flask(__name__)
    app.config["APP_CONFIG"] = SimpleNamespace(is_beta=True)
    with app.app_context():
        payload = ReportService(Client(), salesmen_repo=None).builder_for("item_averages")({}, None)

    assert payload["report_key"] == "item_averages"
    assert "data_source" not in payload


def test_create_app_does_not_import_cli_odata_clients(tmp_path):
    from web import create_app
    from web.config import Config

    create_app(Config(
        app_env="dev", auth_mode="dev", flask_secret="", tenant_id="", client_id="",
        client_secret="", reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "precious.db", cache_db_path=tmp_path / "cache.db",
        litestream_blob_url="", new_app_marker=False,
    ))

    forbidden = {
        "web.reporting.odata_bridge",
        "web.beta_sources",
        "core.odata",
        "data.d365_entities",
        "data.field_maps",
    }
    assert not forbidden.intersection(sys.modules)


def test_sql_cutover_bumps_only_builder_cache_namespace():
    versions = {report.key: report.builder_version for report in built_reports()}
    assert {key: versions[key] for key in (
        "ordered", "invoiced", "salesman", "number_4", "customer_activity", "item_averages",
    )} == {
        "ordered": 9, "invoiced": 4, "salesman": 2, "number_4": 6,
        "customer_activity": 2, "item_averages": 2,
    }
    shared = {"report_key": "ordered", "identity": "dev@x.com", "scope_token": "ALL",
              "params": {"period": "ytd"}}
    assert build_cache_key(builder_version=8, **shared) != build_cache_key(
        builder_version=9, **shared)
