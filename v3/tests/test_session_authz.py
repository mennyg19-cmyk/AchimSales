"""Developer routes and login gates use the DB, not the session role cookie."""

import pytest

from web.auth.authorization import Authorization, Forbidden
from web.auth.principal import Principal
from web.data.repositories.users import UserRepository

from tests.test_blueprints import _CSRF, _login, _make_app


def test_is_developer_ignores_session_role(tmp_path):
    app = _make_app(tmp_path)
    db = app.config["DB"]
    authz = Authorization(db)
    UserRepository(db).upsert("d@x.com", role="developer")
    stale = Principal("d@x.com", "D", "salesman")
    assert authz.is_developer(stale) is True
    with db.precious() as conn:
        conn.execute("UPDATE users SET role='salesman' WHERE email='d@x.com'")
    assert authz.is_developer(stale) is False
    with pytest.raises(Forbidden):
        authz.assert_developer(stale)


def test_demoted_developer_cannot_open_devtools(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="dev@x.com", role="developer")
    assert client.get("/dev/db-explorer").status_code == 200
    repo = UserRepository(app.config["DB"])
    repo.update(repo.get_by_email("dev@x.com").id, role="salesman")
    assert client.get("/dev/db-explorer").status_code == 403
    assert client.get("/api/reports/diagnostics/reporting-api").status_code == 403
    assert client.get("/settings").status_code == 200


def test_disabled_user_is_signed_out(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="dev@x.com", role="developer")
    repo = UserRepository(app.config["DB"])
    repo.update(repo.get_by_email("dev@x.com").id, is_active=False)
    denied = client.post("/settings/theme", data={"theme": "dark", "csrf_token": _CSRF})
    assert denied.status_code in (301, 302, 401)
    resp = client.get("/")
    assert resp.status_code in (301, 302)
    assert "/login" in (resp.headers.get("Location") or "")
    with client.session_transaction() as s:
        assert not s.get("v3_user")


def test_impersonating_inactive_target_is_allowed_without_devtools(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    repo = UserRepository(app.config["DB"])
    repo.upsert("dev@x.com", role="developer")
    target = repo.upsert("rep@x.com", role="salesman")
    repo.update(target.id, is_active=False)
    with client.session_transaction() as s:
        s["v3_user"] = {
            "email": "rep@x.com", "name": "Rep (as Dev)", "role": "salesman",
            "is_dev": True, "impersonating": True,
            "real_email": "dev@x.com", "real_name": "Dev",
        }
        s["_csrf_token"] = _CSRF
    assert client.get("/").status_code == 200
    assert client.get("/dev/db-explorer").status_code == 403


def test_stale_admin_cookie_cannot_open_devtools(tmp_path):
    """Admin is privileged but not a developer — diagnostics stay developer-only."""
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="admin@x.com", role="admin")
    assert client.get("/dev/db-explorer").status_code == 403
    assert client.get("/api/reports/diagnostics/precious-repair").status_code == 403
