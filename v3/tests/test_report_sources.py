"""Home-site SQL/OData source map lives in precious.db."""

from web import create_app
from web.config import Config
from web.data.migrate import migrate
from web.beta_sources import default_sources, get_source, get_sources, set_source


def _cfg(tmp_path) -> Config:
    return Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "precious.db", cache_db_path=tmp_path / "cache.db",
        litestream_blob_url="", is_beta=True,
    )


def test_defaults_signed_off_sql():
    sources = default_sources()
    assert sources["ordered"] == "sql"
    assert sources["invoiced"] == "sql"
    assert sources["customer_activity"] == "sql"
    assert sources["number_4"] == "odata"


def test_set_and_read_round_trip(tmp_path):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    with app.app_context():
        assert get_source("number_4") == "odata"
        set_source("number_4", "sql")
        assert get_source("number_4") == "sql"
        set_source("number_4", "odata")
        assert get_sources()["number_4"] == "odata"


def test_odata_workbook_to_tabs(tmp_path):
    from openpyxl import Workbook

    from web.reporting import odata_bridge as mod

    wb = Workbook()
    ws = wb.active
    ws.title = "Full Details"
    ws.append(["InvoiceNumber", "Total Invoice", "Salesman"])
    ws.append(["IN1", 10.5, "SM01"])
    ws.append(["IN2", 20.0, "SM02"])
    xlsx = tmp_path / "sample.xlsx"
    wb.save(xlsx)

    tabs = mod._workbook_to_tabs(str(xlsx))
    assert len(tabs) == 1
    assert tabs[0]["key"] == "full_details"
    assert tabs[0]["columns"] == ["InvoiceNumber", "Total Invoice", "Salesman"]
    assert len(tabs[0]["rows"]) == 2

    scoped = mod._scope_tab(tabs[0], {"SM01"})
    assert len(scoped["rows"]) == 1
    assert scoped["rows"][0]["InvoiceNumber"] == "IN1"


def test_login_redirect_escapes_open_redirect():
    from web.auth.session import login_redirect

    assert login_redirect("/") == "/login?next=/"
    assert login_redirect("/reports") == "/login?next=/reports"
    assert login_redirect("https://evil.example/") == "/login?next=/"
