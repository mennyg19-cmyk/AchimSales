"""Diagnostics: developer + POST+CSRF; GET no longer mutates."""

from tests.test_blueprints import _CSRF, _login, _make_app

_CLAIM = "/api/reports/diagnostics/claim-once"
_SALESMAN = "/api/reports/diagnostics/reconcile-salesman-invoiced"
_NUMBER4 = "/api/reports/diagnostics/reconcile-number4-invoiced"


def test_claim_once_get_is_405(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="dev@x.com", role="developer")
    assert client.get(_CLAIM).status_code == 405


def test_claim_once_post_requires_csrf_then_probes(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="dev@x.com", role="developer")
    denied = client.post(_CLAIM)
    assert denied.status_code == 400
    ok = client.post(_CLAIM, headers={"X-CSRF-Token": _CSRF})
    assert ok.status_code == 200
    assert "select_found_id" in ok.get_json()


def test_reconcile_get_is_405_and_post_needs_developer(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    assert client.get(_SALESMAN).status_code == 405
    assert client.get(_NUMBER4).status_code == 405
    denied = client.post(_SALESMAN, headers={"X-CSRF-Token": _CSRF})
    assert denied.status_code == 403


def test_reconcile_post_developer_without_api_is_503(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="dev@x.com", role="developer")
    no_csrf = client.post(_SALESMAN)
    assert no_csrf.status_code == 400
    resp = client.post(_SALESMAN, headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 503
    assert resp.get_json()["ok"] is False
    n4 = client.post(_NUMBER4, json={"view": "by_customer"},
                     headers={"X-CSRF-Token": _CSRF})
    assert n4.status_code == 503
