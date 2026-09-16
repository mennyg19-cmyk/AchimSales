"""Office doorway: translators, thin tabs, mocked HTTP. Never a real API key."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import date
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

import assemble
import catalog
import doorway
import lookups
import params
import period
import reports
from config import DEFAULT_REPORTING_API_BASE, reporting_api_base
from main import create_app
import store as home_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "home.sqlite"))
    monkeypatch.delenv("REPORTING_API_KEY", raising=False)
    with TestClient(create_app()) as test_client:
        yield test_client


def login(client: TestClient):
    client.post("/login/preview", follow_redirects=False)
    html = client.get("/").text
    match = re.search(r'data-csrf="([^"]+)"', html)
    client.csrf = match.group(1)


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.csrf}


def become(client: TestClient, email: str):
    row = home_store.get_user(email)
    res = client.post(
        f"/admin/users/{row['id']}/view-as",
        data={"csrf": client.csrf},
        follow_redirects=False,
    )
    assert res.status_code == 303
    html = client.get("/").text
    match = re.search(r'data-csrf="([^"]+)"', html)
    assert match
    client.csrf = match.group(1)


def _result(report_id: str, rows: list, body: dict | None = None) -> doorway.ReportResult:
    payload = body or {"rows": rows, "report_id": report_id}
    return doorway.ReportResult(report_id, rows, payload)


def fake_run(report_id, params_in=None, timeout=None):
    params_in = dict(params_in or {})
    fake_run.calls.append((report_id, params_in, timeout))
    if report_id == "salesmen_master":
        rows = [{"Salesman": "DDweck", "SalesmanName": "Dweck, David"}]
    elif report_id == "customer_master":
        rows = [
            {
                "CustomerAccount": "C-1001",
                "CustomerName": "HD SUPPLY",
                "SalesGroup": "DDweck",
            }
        ]
    elif report_id == "invoiced_report":
        rows = [
            {
                "InvoiceNumber": "IN-LIVE",
                "CustomerAccount": "C-1001",
                "CustomerName": "HD SUPPLY",
                "Salesman": "DDweck",
                "Total Invoice": 10,
                "IsCredit": False,
            },
            {
                "InvoiceNumber": "CR-LIVE",
                "CustomerAccount": "C-1001",
                "CustomerName": "HD SUPPLY",
                "Salesman": "DDweck",
                "Total Invoice": -2,
                "IsCredit": True,
            },
        ]
    elif report_id == "customer_last_orders":
        acct = str((params_in or {}).get("CustomerAccount") or "C-1001")
        salesman = "HKaufman" if acct == "X-LIVE" else "DDweck"
        rows = [
            {
                "Order Rank": 1,
                "Sales Order Number": "SO-LIVE",
                "Order Date": "2026-09-01",
                "Item #": "A-100",
                "Description": "Widget",
                "Qty Ordered": 2,
                "Sales Price": 5,
                "Total": 10,
                "PO #": "PO1",
                "Customer Account": acct,
                "Salesman": salesman,
            }
        ]
    elif report_id in {"customer_item_sales_rolling_12", "item_customer_sales_rolling_12"}:
        rows = [{"Customer": "HD SUPPLY", "Item #": "A-100", "Total $": 9}]
    elif report_id.startswith("sales_by_state"):
        rows = [{"State": "NY", "Sales": 50}]
    else:
        rows = [
            {
                "CustomerAccount": "C-1001",
                "CustomerName": "HD SUPPLY",
                "Salesman": "DDweck",
            }
        ]
    return _result(report_id, rows)


fake_run.calls = []


@pytest.fixture
def live_client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "home.sqlite"))
    monkeypatch.setenv("REPORTING_API_KEY", "test-key-not-live")
    monkeypatch.setenv("REPORTING_API_BASE_URL", "https://reporting.test.example")
    fake_run.calls = []
    monkeypatch.setattr(doorway, "run_report", fake_run)
    monkeypatch.setattr("lookups.doorway.run_report", fake_run)
    monkeypatch.setattr("reports.doorway.run_report", fake_run)
    with TestClient(create_app()) as test_client:
        yield test_client


def test_default_base_is_office_doorway(monkeypatch):
    monkeypatch.delenv("REPORTING_API_BASE_URL", raising=False)
    assert reporting_api_base() == DEFAULT_REPORTING_API_BASE
    assert "reports.achimonline.com" not in reporting_api_base()


def test_period_ytd_clamps_to_go_live(monkeypatch):
    monkeypatch.setattr(period, "today_eastern", lambda: date(2025, 1, 10))
    window = period.resolve_period("ytd")
    assert window.start_date == period.D365_GO_LIVE
    assert window.end_date == date(2025, 1, 10)


def test_translate_omits_empty_salesman():
    body = params.translate("invoiced", {"period": "all_time", "salesman": ""})
    assert "Salesman" not in body
    assert "InvoiceDateFrom" not in body


def test_translate_single_customer_only():
    body = params.translate("ordered", {"customers": ["C-1001", "C-1002"], "period": "all_time"})
    assert "CustomerAccount" not in body
    one = params.translate("ordered", {"customers": ["C-1001"], "period": "all_time"})
    assert one["CustomerAccount"] == "C-1001"


def test_assemble_uses_existing_tabs():
    result = _result(
        "invoiced_report",
        [],
        {
            "data": {
                "tabs": {
                    "full_details": {
                        "name": "Full Details",
                        "rows": [{"InvoiceNumber": "X"}],
                    }
                }
            }
        },
    )
    payload = assemble.from_result("invoiced", result)
    row = payload["data"]["tabs"]["full_details"]["rows"][0]
    assert row["InvoiceNumber"] == "X"
    assert row["CustomerName"] == ""


def test_assemble_thin_invoiced_splits_credits():
    rows = [
        {"InvoiceNumber": "IN1", "IsCredit": False, "Total Invoice": 10, "Salesman": "A", "CustomerAccount": "1"},
        {"InvoiceNumber": "CR1", "IsCredit": True, "Total Invoice": -1, "Salesman": "B", "CustomerAccount": "2"},
    ]
    tabs = assemble.thin_tabs("invoiced", rows)
    assert len(tabs["credits"]["rows"]) == 1
    assert len(tabs["invoices"]["rows"]) == 1
    assert "full_details" in tabs
    assert len(tabs["totals_by_salesman"]["rows"]) == 2


def test_build_payload_mock_without_key(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "home.sqlite"))
    monkeypatch.delenv("REPORTING_API_KEY", raising=False)
    from db import init_db

    init_db()
    payload = reports.build_payload("invoiced", {"role": "admin", "email": "a@b.c"}, {})
    assert payload["data"]["source"] == "mock"
    assert "full_details" in payload["data"]["tabs"]


def test_run_without_key_is_mock(client):
    login(client)
    html = client.get("/").text
    assert "Dummy JSON" in html
    payload = client.post("/api/reports/invoiced/run", json={}, headers=csrf_headers(client)).json()
    assert payload["data"]["source"] == "mock"


def test_exclusions_page_uses_customer_master(live_client):
    login(live_client)
    html = live_client.get("/settings").text
    assert "C-1001" in html
    assert "HD SUPPLY" in html
    assert "C-1002" not in html
    assert "MAZER WHOLESALE" not in html
    assert 'id="exclPicker"' in html
    assert 'id="exclSearch"' in html
    assert "customer-search" in html
    assert "excl-box" not in html


def test_live_invoiced_run_uses_doorway(live_client):
    login(live_client)
    payload = live_client.post(
        "/api/reports/invoiced/run", json={}, headers=csrf_headers(live_client)
    ).json()
    assert payload["data"]["source"] == "reporting_api"
    assert any(row.get("InvoiceNumber") == "IN-LIVE" for row in payload["data"]["tabs"]["full_details"]["rows"])
    assert "credits" in payload["data"]["tabs"]
    ids = [call[0] for call in fake_run.calls]
    assert "invoiced_report" in ids
    invoiced = next(call for call in fake_run.calls if call[0] == "invoiced_report")
    assert "InvoiceDateFrom" in invoiced[1]


def test_live_number_4_calls_both_sps(live_client):
    login(live_client)
    payload = live_client.post(
        "/api/reports/number_4/run", json={"n4_mode": "both"}, headers=csrf_headers(live_client)
    ).json()
    ids = [call[0] for call in fake_run.calls]
    assert "customer_item_sales_rolling_12" in ids
    assert "item_customer_sales_rolling_12" in ids
    assert "by_customer" in payload["data"]["tabs"]
    assert "by_item" in payload["data"]["tabs"]


def test_live_sales_by_state_calls_three_sps(live_client):
    login(live_client)
    live_client.post("/api/reports/sales_by_state/run", json={}, headers=csrf_headers(live_client))
    ids = [call[0] for call in fake_run.calls]
    assert "sales_by_state_summary" in ids
    assert "sales_by_state_new_york_city" in ids
    assert "sales_by_state_filtered" in ids


def test_live_last_order(live_client):
    login(live_client)
    html = live_client.get("/report/customer-last-order/C-1001").text
    assert "SO-LIVE" in html
    assert "Widget" in html


def test_live_salesman_invoiced_clamps_sp_salesman(live_client):
    login(live_client)
    become(live_client, "salesman@achimonline.com")
    fake_run.calls = []
    live_client.post(
        "/api/reports/invoiced/run",
        json={"salesman": "DDweck"},
        headers=csrf_headers(live_client),
    )
    invoiced = next(call for call in fake_run.calls if call[0] == "invoiced_report")
    assert invoiced[1].get("Salesman") == "HKaufman"


def test_last_order_picker_shows_dummy_banner(client):
    login(client)
    pick = client.get("/report/customer-last-order").text
    assert "Dummy JSON" in pick
    view = client.get("/report/customer-last-order/C-1001").text
    assert "SO-88021" in view
    assert "Dummy JSON" in view


def test_live_last_order_acl_uses_row_salesman_when_lookup_misses(live_client, monkeypatch):
    monkeypatch.setattr(lookups, "customer", lambda account: None)
    login(live_client)
    become(live_client, "salesman@achimonline.com")
    ok = live_client.get("/report/customer-last-order/X-LIVE", follow_redirects=False)
    assert ok.status_code == 200
    assert "SO-LIVE" in ok.text
    denied = live_client.get("/report/customer-last-order/C-1001", follow_redirects=False)
    assert denied.status_code == 302


def test_cell_alias_walk_and_strip():
    row = {"SalesGroup": " DDweck "}
    assert catalog.cell(row, "salesgroup") == " DDweck "
    assert catalog.cell(row, "salesgroup", strip=True) == "DDweck"
    assert catalog.cell({}, "missing", default=0) == 0


def test_salesman_tabs_share_yoy_ytd_keys():
    mock_tabs = catalog.mock_report("salesman")["data"]["tabs"]
    thin = assemble.thin_tabs("salesman", [{"Jan": 1, "YTD": 2}])
    assert set(mock_tabs) == {"yoy", "ytd"}
    assert set(thin) == {"yoy", "ytd"}


def test_live_last_order_sidecar_error_is_visible(live_client, monkeypatch):
    def boom(report_id, params_in=None, timeout=None):
        if report_id == "invoiced_report":
            raise doorway.DoorwayError("Reporting API unreachable for invoiced_report: timeout")
        return fake_run(report_id, params_in, timeout)

    monkeypatch.setattr("reports.doorway.run_report", boom)
    login(live_client)
    html = live_client.get("/report/customer-last-order/C-1001").text
    assert "SO-LIVE" in html
    assert "Recent invoiced could not load" in html
    assert "timeout" in html


def test_dev_reporting_invalid_json_is_400(live_client):
    login(live_client)
    res = live_client.post(
        "/api/dev/reporting/invoiced_report/run",
        content=b"not-json",
        headers={**csrf_headers(live_client), "Content-Type": "application/json"},
    )
    assert res.status_code == 400
    assert "JSON" in res.json()["error"]
    listed = live_client.post(
        "/api/dev/reporting/invoiced_report/run",
        json=[1, 2],
        headers=csrf_headers(live_client),
    )
    assert listed.status_code == 400


def test_dev_reporting_live(live_client):
    login(live_client)
    res = live_client.post(
        "/api/dev/reporting/invoiced_report/run",
        json={"InvoiceDateFrom": "2026-01-01 00:00:00"},
        headers=csrf_headers(live_client),
    )
    assert res.status_code == 200
    assert res.json()["row_count"] == 2
    assert any(call[0] == "invoiced_report" for call in fake_run.calls)


def test_doorway_4xx_does_not_retry(monkeypatch):
    monkeypatch.setenv("REPORTING_API_KEY", "test-key-not-live")
    monkeypatch.setenv("REPORTING_API_BASE_URL", "https://reporting.test.example")
    opens = {"n": 0}

    class Boom(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                "https://reporting.test.example/api/reports/x/run",
                401,
                "Unauthorized",
                hdrs={},
                fp=BytesIO(b'{"error":"Missing API key"}'),
            )

    class Opener:
        def open(self, req, timeout=None):
            opens["n"] += 1
            raise Boom()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: Opener())
    with pytest.raises(doorway.DoorwayError, match="401"):
        doorway.run_report("invoiced_report", {})
    assert opens["n"] == 1


def test_doorway_redirect_is_error(monkeypatch):
    monkeypatch.setenv("REPORTING_API_KEY", "test-key-not-live")
    monkeypatch.setenv("REPORTING_API_BASE_URL", "https://reporting.test.example")

    class Redirect(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                "https://reporting.test.example/api/reports/x/run",
                302,
                "Found",
                hdrs={"Location": "/"},
                fp=BytesIO(b""),
            )

    class Opener:
        def open(self, req, timeout=None):
            raise Redirect()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: Opener())
    with pytest.raises(doorway.DoorwayError, match="redirected"):
        doorway.run_report("invoiced_report", {})


def test_doorway_parses_rows(monkeypatch):
    monkeypatch.setenv("REPORTING_API_KEY", "test-key-not-live")
    monkeypatch.setenv("REPORTING_API_BASE_URL", "https://reporting.test.example")

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"rows": [{"A": 1}], "report_id": "ordered_report"}).encode()

    class Opener:
        def open(self, req, timeout=None):
            assert "X-API-Key" in req.headers or "X-api-key" in req.headers
            return Resp()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: Opener())
    result = doorway.run_report("ordered_report", {"SalesGroup": "DDweck"})
    assert result.rows == [{"A": 1}]


def test_doorway_parses_columns_and_odata(monkeypatch):
    monkeypatch.setenv("REPORTING_API_KEY", "test-key-not-live")
    monkeypatch.setenv("REPORTING_API_BASE_URL", "https://reporting.test.example")
    bodies = [
        {
            "columns": ["CustomerAccount", "CustomerName", "SalesGroup"],
            "rows": [["C-9001", "LIVE CO", "DDweck"], ["C-9002"]],
        },
        {"value": [{"CustomerAccount": "C-9003", "CustomerName": "ODATA CO"}]},
        {"Table": [{"CustomerAccount": "C-9004"}]},
    ]
    index = {"n": 0}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(bodies[index["n"]]).encode()

    class Opener:
        def open(self, req, timeout=None):
            return Resp()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: Opener())
    first = doorway.run_report("customer_master", {})
    assert first.rows[0]["CustomerAccount"] == "C-9001"
    assert first.rows[1]["CustomerName"] == ""
    index["n"] = 1
    assert doorway.run_report("customer_master", {}).rows[0]["CustomerAccount"] == "C-9003"
    index["n"] = 2
    assert doorway.run_report("customer_master", {}).rows[0]["CustomerAccount"] == "C-9004"


def test_assemble_converts_old_rows_and_pads_empty_fields():
    result = _result(
        "invoiced_report",
        [{"InvoiceNumber": "IN-OLD", "CustomerAccount": "C-1"}],
        {"rows": [{"InvoiceNumber": "IN-OLD", "CustomerAccount": "C-1"}]},
    )
    payload = assemble.from_result("invoiced", result)
    row = payload["data"]["tabs"]["full_details"]["rows"][0]
    assert row["InvoiceNumber"] == "IN-OLD"
    assert row["CustomerAccount"] == "C-1"
    assert row["CustomerName"] == ""
    assert row["Total Invoice"] == ""
    assert "full_details" in payload["data"]["tabs"]
    assert "credits" in payload["data"]["tabs"]
