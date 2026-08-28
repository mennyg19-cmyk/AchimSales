"""precious-repair must not mutate on GET (CSRF-exempt)."""

from web.data.migrate import migrate
from web.data.repositories.jobs import JobRepository

from tests.test_blueprints import _CSRF, _login, _make_app

_URL = "/api/reports/diagnostics/precious-repair"


def test_get_check_ok_for_developer(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="dev@x.com", role="developer")
    resp = client.get(_URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action"] == "check"
    assert "integrity_check" in body


def test_get_delete_ghosts_is_405_and_does_not_delete(tmp_path):
    app = _make_app(tmp_path)
    migrate(app.config["DB"])
    JobRepository(app.config["DB"]).enqueue("probe")
    client = app.test_client()
    _login(client, app, email="dev@x.com", role="developer")
    before = client.get(_URL).get_json()["queued_via_index"]
    assert before >= 1
    resp = client.get(_URL + "?action=delete-ghosts")
    assert resp.status_code == 405
    after = client.get(_URL).get_json()["queued_via_index"]
    assert after == before


def test_post_delete_ghosts_requires_csrf_then_deletes(tmp_path):
    app = _make_app(tmp_path)
    migrate(app.config["DB"])
    JobRepository(app.config["DB"]).enqueue("probe")
    client = app.test_client()
    _login(client, app, email="dev@x.com", role="developer")
    denied = client.post(_URL + "?action=delete-ghosts")
    assert denied.status_code == 400
    still = client.get(_URL).get_json()["queued_via_index"]
    assert still >= 1
    ok = client.post(
        _URL + "?action=delete-ghosts",
        headers={"X-CSRF-Token": _CSRF},
    )
    assert ok.status_code == 200
    assert ok.get_json()["deleted"] >= 1
    assert client.get(_URL).get_json()["queued_via_index"] == 0


def test_admin_cannot_check(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    assert client.get(_URL).status_code == 403


def test_backup_table_names_must_be_identifiers():
    import pytest
    from web.blueprints.report_diagnostics import _sqlite_ident

    assert _sqlite_ident("jobs") == '"jobs"'
    with pytest.raises(ValueError, match="non-identifier"):
        _sqlite_ident("jobs; DROP TABLE users")
    with pytest.raises(ValueError, match="non-identifier"):
        _sqlite_ident("users--")
