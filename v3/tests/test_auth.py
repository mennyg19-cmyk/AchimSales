"""Auth + the single authorization/scope layer (rule 6)."""

from pathlib import Path

import pytest

from report_engine import registry
from report_engine.registry import ReportSpec, ReportStatus
from web import create_app
from web.auth.authorization import Authorization, Forbidden
from web.auth.principal import Principal
from web.config import Config
from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.users import User, UserRepository


def _dev_cfg(tmp_path) -> Config:
    return Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "precious.db", cache_db_path=tmp_path / "cache.db",
        litestream_blob_url="", new_app_marker=True,
    )


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "precious.db", tmp_path / "cache.db")
    migrate(d)
    return d


def _seed_salesman_scope(db, email, role, keys):
    users = UserRepository(db)
    u = users.upsert(email, role=role)
    with db.precious() as conn:
        for k in keys:
            conn.execute(
                "INSERT INTO user_salesman_access(user_id, salesman_key) VALUES (?, ?)",
                (u.id, k),
            )
    return u


# --- Principal --------------------------------------------------------------

def test_principal_defaults_unknown_role_to_salesman():
    p = Principal.from_dict({"email": "a@b.com", "role": "wizard"})
    assert p.role == "salesman" and not p.is_privileged


def test_principal_requires_email():
    assert Principal.from_dict({"name": "x"}) is None


# --- scope ------------------------------------------------------------------

def test_privileged_is_unrestricted(db):
    UserRepository(db).upsert("admin@b.com", role="admin")
    authz = Authorization(db)
    admin = Principal("admin@b.com", "A", "admin")
    assert authz.visible_salesman_keys(admin) is None
    assert authz.can_view_customer(admin, "anything") is True


def test_unknown_user_is_denied_even_with_privileged_cookie(db):
    """A privileged-looking cookie for a user not in the DB sees nothing."""
    authz = Authorization(db)
    ghost = Principal("ghost@b.com", "G", "admin")
    assert authz.visible_salesman_keys(ghost) == set()
    assert authz.can_view_customer(ghost, "anything") is False


def test_salesman_scope_is_enforced(db):
    _seed_salesman_scope(db, "sm@b.com", "salesman", ["mkolko"])
    authz = Authorization(db)
    p = Principal("sm@b.com", "S", "salesman")
    assert authz.visible_salesman_keys(p) == {"mkolko"}
    assert authz.can_view_customer(p, "M Kolko") is True       # normalizes to mkolko
    assert authz.can_view_customer(p, "H Kaufman") is False
    with pytest.raises(Forbidden):
        authz.assert_can_view_customer(p, "H Kaufman")


# --- report access ----------------------------------------------------------

def test_backlog_report_never_viewable(db):
    authz = Authorization(db)
    users = UserRepository(db)
    users.upsert("admin@b.com", role="admin")
    admin = Principal("admin@b.com", "A", "admin")
    # customer_aging is BACKLOG -> even an active admin cannot view it (no fake stub)
    assert authz.can_view_report(admin, "customer_aging") is False
    assert authz.can_view_report(admin, "does_not_exist") is False


def test_built_report_is_default_deny_for_non_privileged(db, monkeypatch):
    # Pretend "ordered" is BUILT for this test.
    monkeypatch.setitem(
        registry._BY_KEY, "ordered", ReportSpec("ordered", "Ordered", ReportStatus.BUILT)
    )
    authz = Authorization(db)
    users = UserRepository(db)
    users.upsert("admin@b.com", role="admin")
    users.upsert("sm@b.com", role="salesman")

    admin = Principal("admin@b.com", "A", "admin")
    p = Principal("sm@b.com", "S", "salesman")
    assert authz.can_view_report(admin, "ordered") is True   # privileged sees built reports
    assert authz.can_view_report(p, "ordered") is False      # FAIL CLOSED: no allow row

    u = users.get_by_email("sm@b.com")
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO user_report_access(user_id, report_key, allowed) VALUES (?, 'ordered', 1)",
            (u.id,),
        )
    assert authz.can_view_report(p, "ordered") is True       # explicit allow
    with db.precious() as conn:
        conn.execute(
            "UPDATE user_report_access SET allowed=0 WHERE user_id=? AND report_key='ordered'",
            (u.id,),
        )
    assert authz.can_view_report(p, "ordered") is False      # explicit deny


def test_inherit_resolves_to_role_default(db, monkeypatch):
    """No override row = 'inherit': managers see all built reports; salesmen see
    only salesman-default reports. Explicit allow/deny still override."""
    monkeypatch.setitem(
        registry._BY_KEY, "ordered",
        ReportSpec("ordered", "Ordered", ReportStatus.BUILT, salesman_default=True),
    )
    monkeypatch.setitem(
        registry._BY_KEY, "salesman",
        ReportSpec("salesman", "Salesman", ReportStatus.BUILT, salesman_default=False),
    )
    authz = Authorization(db)
    users = UserRepository(db)
    users.upsert("sm@b.com", role="salesman")
    users.upsert("mgr@b.com", role="manager")
    sm = Principal("sm@b.com", "S", "salesman")
    mgr = Principal("mgr@b.com", "M", "manager")

    # Salesman inherits role defaults: salesman-default report visible, others not.
    assert authz.can_view_report(sm, "ordered") is True
    assert authz.can_view_report(sm, "salesman") is False
    # Manager inherits "see all".
    assert authz.can_view_report(mgr, "ordered") is True
    assert authz.can_view_report(mgr, "salesman") is True

    # Explicit overrides beat the inherited default in both directions.
    u = users.get_by_email("sm@b.com")
    users.set_report_access(u.id, "salesman", True)   # allow a non-default report
    users.set_report_access(u.id, "ordered", False)   # deny a default report
    assert authz.can_view_report(sm, "salesman") is True
    assert authz.can_view_report(sm, "ordered") is False
    # Clearing reverts to inherit.
    users.clear_report_access(u.id, "ordered")
    assert authz.can_view_report(sm, "ordered") is True


def test_global_report_off_hides_unless_override(db, monkeypatch):
    monkeypatch.setitem(
        registry._BY_KEY, "ordered",
        ReportSpec("ordered", "Ordered", ReportStatus.BUILT, salesman_default=True),
    )
    from web.data.repositories.report_config import ReportConfigRepository
    users = UserRepository(db)
    users.upsert("sm@b.com", role="salesman")
    users.upsert("admin@b.com", role="admin")
    ReportConfigRepository(db).set("ordered", False)
    authz = Authorization(db)
    sm = Principal("sm@b.com", "S", "salesman")
    admin = Principal("admin@b.com", "A", "admin")
    assert authz.can_view_report(sm, "ordered") is False
    assert authz.can_view_report(admin, "ordered") is False
    users.set_report_access(users.get_by_email("sm@b.com").id, "ordered", True)
    assert authz.can_view_report(sm, "ordered") is True


def test_role_revocation_takes_effect_immediately(db):
    """Downgrading a user in the DB must drop privileges even with an old cookie."""
    authz = Authorization(db)
    users = UserRepository(db)
    users.upsert("u@b.com", role="admin")
    # Session still claims admin (stale cookie):
    stale = Principal("u@b.com", "U", "admin")
    assert authz.visible_salesman_keys(stale) is None  # privileged now
    with db.precious() as conn:
        conn.execute("UPDATE users SET role='salesman' WHERE email='u@b.com'")
    assert authz.visible_salesman_keys(stale) == set()  # downgraded -> scoped, no keys


def test_inactive_user_denied_everything(db, monkeypatch):
    monkeypatch.setitem(
        registry._BY_KEY, "ordered", ReportSpec("ordered", "Ordered", ReportStatus.BUILT)
    )
    authz = Authorization(db)
    users = UserRepository(db)
    u = users.upsert("gone@b.com", role="admin")
    with db.precious() as conn:
        conn.execute("INSERT INTO user_report_access(user_id, report_key, allowed) VALUES (?, 'ordered', 1)", (u.id,))
        conn.execute("UPDATE users SET is_active=0, sharepoint_access=1 WHERE email='gone@b.com'")
    p = Principal("gone@b.com", "G", "admin")
    assert authz.visible_salesman_keys(p) == set()
    assert authz.can_view_customer(p, "anything") is False
    assert authz.can_view_report(p, "ordered") is False
    assert authz.has_sharepoint_access(p) is False


def test_sharepoint_access(db):
    authz = Authorization(db)
    users = UserRepository(db)
    users.upsert("sm@b.com", role="salesman")
    p = Principal("sm@b.com", "S", "salesman")
    assert authz.has_sharepoint_access(p) is False
    with db.precious() as conn:
        conn.execute("UPDATE users SET sharepoint_access=1 WHERE email='sm@b.com'")
    assert authz.has_sharepoint_access(p) is True
    users.upsert("a@b.com", role="developer")
    assert authz.has_sharepoint_access(Principal("a@b.com", "A", "developer")) is True


def test_from_row_defaults_company_views_when_column_absent(db):
    """Schedule runs SELECT * / a partial user row. Missing flag must not IndexError."""
    UserRepository(db).upsert("a@x.com", role="admin")
    with db.precious() as conn:
        row = conn.execute(
            "SELECT id, email, display_name, role, is_active, is_external, "
            "dashboard_enabled, sharepoint_access, test_access FROM users WHERE email=?",
            ("a@x.com",),
        ).fetchone()
    u = User.from_row(row)
    assert u.can_see_company_views is False
    assert u.email == "a@x.com"


def test_get_by_email_when_company_views_column_dropped(db):
    import sqlite3

    repo = UserRepository(db)
    repo.upsert("a@x.com", role="admin")
    with db.precious() as conn:
        try:
            conn.execute("ALTER TABLE users DROP COLUMN can_see_company_views")
        except sqlite3.OperationalError as exc:
            pytest.skip(str(exc))
    u = repo.get_by_email("a@x.com")
    assert u is not None and u.can_see_company_views is False


def test_company_views_flag_is_the_only_gate_for_non_privileged(db):
    authz = Authorization(db)
    users = UserRepository(db)
    users.upsert("sm@b.com", role="salesman")
    p = Principal("sm@b.com", "S", "salesman")
    assert authz.can_see_company_views(p) is False
    users.update(users.get_by_email("sm@b.com").id, can_see_company_views=True)
    assert authz.can_see_company_views(p) is True
    users.upsert("admin@b.com", role="admin")
    assert authz.can_see_company_views(Principal("admin@b.com", "A", "admin")) is True
    users.update(users.get_by_email("admin@b.com").id, can_see_company_views=False)
    assert authz.can_see_company_views(Principal("admin@b.com", "A", "admin")) is True
    users.upsert("dev@b.com", role="developer")
    assert authz.can_see_company_views(Principal("dev@b.com", "D", "developer")) is True
    users.update(users.get_by_email("dev@b.com").id, can_see_company_views=False)
    assert authz.can_see_company_views(Principal("dev@b.com", "D", "developer")) is True
    with db.precious() as conn:
        conn.execute("UPDATE users SET is_active=0 WHERE email='dev@b.com'")
    assert authz.can_see_company_views(Principal("dev@b.com", "D", "developer")) is False


# --- blueprint flows --------------------------------------------------------

@pytest.fixture
def app(tmp_path):
    cfg = _dev_cfg(tmp_path)
    application = create_app(cfg)
    migrate(application.config["DB"])
    return application


def test_dev_login_and_session(app):
    client = app.test_client()
    page = client.get("/login")
    assert page.status_code == 200 and b"Developer sign-in" in page.data
    # CSRF token is in the form; reuse the session token the GET established.
    with client.session_transaction() as sess:
        token = sess["_csrf_token"]
    resp = client.post(
        "/login/dev",
        data={"email": "dev@b.com", "role": "admin", "csrf_token": token},
    )
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess["v3_user"]["email"] == "dev@b.com"
        assert sess["v3_user"]["role"] == "admin"


def test_dev_login_refused_when_not_dev(tmp_path):
    cfg = _dev_cfg(tmp_path)
    object.__setattr__(cfg, "auth_mode", "msal")  # frozen dataclass
    application = create_app(cfg)
    migrate(application.config["DB"])
    client = application.test_client()
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "t"
    resp = client.post("/login/dev", data={"email": "x@b.com", "csrf_token": "t"})
    assert resp.status_code == 403


def test_inactive_user_cannot_login(app):
    client = app.test_client()
    # First sign-in creates an active user.
    with client.session_transaction() as sess:
        token = sess.get("_csrf_token", "seed")
        sess["_csrf_token"] = token
    client.post("/login/dev", data={"email": "d@b.com", "role": "salesman", "csrf_token": token})
    # Disable the account, then try again.
    with app.config["DB"].precious() as conn:
        conn.execute("UPDATE users SET is_active=0 WHERE email='d@b.com'")
    client.get("/logout")  # GET should not log out (POST-only)
    resp = client.post("/login/dev", data={"email": "d@b.com", "role": "salesman", "csrf_token": token})
    assert resp.status_code == 403


def test_logout_requires_post(app):
    client = app.test_client()
    assert client.get("/logout").status_code == 405  # state change must be POST


def test_msal_callback_without_flow_is_rejected(app):
    # No auth flow in session -> safe error, not a crash.
    resp = app.test_client().get("/auth/callback")
    assert resp.status_code == 400


def test_msal_callback_denies_unknown_user_without_creating_row(app, monkeypatch):
    from web.auth import msal_flow

    monkeypatch.setattr(msal_flow, "complete_login", lambda _cfg: {
        "email": "unknown@x.com", "name": "Unknown",
    })
    response = app.test_client().get("/auth/callback")
    assert response.status_code == 403
    assert b"Access denied" in response.data
    assert UserRepository(app.config["DB"]).get_by_email("unknown@x.com") is None


def test_msal_callback_logs_in_known_active_user(app, monkeypatch):
    from web.auth import msal_flow

    UserRepository(app.config["DB"]).upsert("known@x.com", role="salesman")
    monkeypatch.setattr(msal_flow, "complete_login", lambda _cfg: {
        "email": "known@x.com", "name": "Known",
    })
    client = app.test_client()
    assert client.get("/auth/callback").status_code == 302
    with client.session_transaction() as sess:
        assert sess["v3_user"]["email"] == "known@x.com"


def test_msal_callback_denies_inactive_user(app, monkeypatch):
    from web.auth import msal_flow

    user = UserRepository(app.config["DB"]).upsert("inactive@x.com", role="salesman")
    UserRepository(app.config["DB"]).update(user.id, is_active=False)
    monkeypatch.setattr(msal_flow, "complete_login", lambda _cfg: {
        "email": "inactive@x.com", "name": "Inactive",
    })
    assert app.test_client().get("/auth/callback").status_code == 403


# --- impersonation ----------------------------------------------------------

def test_impersonate_start_and_end(app):
    """A developer can impersonate a user and end the session."""
    db = app.config["DB"]
    UserRepository(db).upsert("dev@x.com", role="developer")
    UserRepository(db).upsert("rep@x.com", role="salesman", display_name="Sales Rep")
    client = app.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "dev@x.com", "name": "Dev", "role": "developer", "is_dev": True}
        s["_csrf_token"] = "t"
    # Start impersonation
    resp = client.post("/impersonate", data={"email": "rep@x.com", "csrf_token": "t"})
    assert resp.status_code == 302
    with client.session_transaction() as s:
        assert s["v3_user"]["email"] == "rep@x.com"
        assert s["v3_user"]["impersonating"] is True
        assert s["v3_user"]["real_email"] == "dev@x.com"
        assert "as Dev" in s["v3_user"]["name"]
    # End impersonation
    resp = client.post("/impersonate/end", data={"csrf_token": "t"})
    assert resp.status_code == 302
    with client.session_transaction() as s:
        assert s["v3_user"]["email"] == "dev@x.com"
        assert s["v3_user"].get("impersonating") is not True


def test_impersonate_denied_for_admin(app):
    db = app.config["DB"]
    UserRepository(db).upsert("adm@x.com", role="admin")
    UserRepository(db).upsert("dev@x.com", role="developer")
    client = app.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "adm@x.com", "name": "Adm", "role": "admin", "is_dev": False}
        s["_csrf_token"] = "t"
    assert client.get("/impersonate").status_code == 403
    assert client.post("/impersonate", data={"email": "dev@x.com", "csrf_token": "t"}).status_code == 403


def test_impersonation_stops_when_real_developer_disabled(app):
    db = app.config["DB"]
    repo = UserRepository(db)
    dev = repo.upsert("dev@x.com", role="developer")
    repo.upsert("adm@x.com", role="admin")
    client = app.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "dev@x.com", "name": "Dev", "role": "developer", "is_dev": True}
        s["_csrf_token"] = "t"
    assert client.post("/impersonate", data={"email": "adm@x.com", "csrf_token": "t"}).status_code == 302
    repo.update(dev.id, is_active=False)
    assert client.get("/api/admin/users").status_code == 401
    with client.session_transaction() as s:
        assert not s.get("v3_user")


def test_impersonate_denied_for_non_privileged(app):
    """Non-privileged users cannot impersonate."""
    db = app.config["DB"]
    UserRepository(db).upsert("mgr@x.com", role="manager")
    client = app.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "mgr@x.com", "name": "Mgr", "role": "manager", "is_dev": False}
        s["_csrf_token"] = "t"
    assert client.get("/impersonate").status_code == 403
    assert client.post("/impersonate", data={"email": "x@x.com", "csrf_token": "t"}).status_code == 403


def test_impersonate_cannot_nest(app):
    """An impersonating session cannot start another impersonation."""
    db = app.config["DB"]
    UserRepository(db).upsert("dev@x.com", role="developer")
    UserRepository(db).upsert("rep@x.com", role="salesman")
    client = app.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "rep@x.com", "name": "Rep (as Dev)", "role": "salesman",
                        "is_dev": True, "impersonating": True, "real_email": "dev@x.com",
                        "real_name": "Dev"}
        s["_csrf_token"] = "t"
    assert client.get("/impersonate").status_code == 400
    assert client.post("/impersonate", data={"email": "x@x.com", "csrf_token": "t"}).status_code == 400


def test_beta_login_shows_microsoft_button(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    resp = application.test_client().get("/login")
    assert resp.status_code == 200
    assert b"Achim User Login" in resp.data
    assert b"/legacy/login/start" in resp.data
    assert b"Developer sign-in" not in resp.data


def test_beta_magic_link_uses_active_external_v3_user_only(tmp_path, monkeypatch):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    repo = UserRepository(application.config["DB"])
    repo.create("external@x.com", role="salesman", is_external=True)
    repo.create("internal@x.com", role="salesman", is_external=False)
    sent = []

    class Mailer:
        def __init__(self, *_args):
            pass

        def send(self, **kwargs):
            sent.append(kwargs)

    monkeypatch.setattr("web.blueprints.auth.GraphMailer", Mailer)
    client = application.test_client()
    page = client.get("/login")
    assert b'action="/login/magic-link"' in page.data
    with client.session_transaction() as session:
        token = session["_csrf_token"]
    external = client.post("/login/magic-link", data={
        "email": "external@x.com", "csrf_token": token,
    }, follow_redirects=True)
    unknown = client.post("/login/magic-link", data={
        "email": "unknown@x.com", "csrf_token": token,
    }, follow_redirects=True)
    internal = client.post("/login/magic-link", data={
        "email": "internal@x.com", "csrf_token": token,
    }, follow_redirects=True)
    assert external.data == unknown.data == internal.data
    assert len(sent) == 1 and sent[0]["to"] == ["external@x.com"]
    link = sent[0]["body_text"].rsplit("/", 1)[-1]
    with application.config["DB"].precious() as conn:
        row = conn.execute("SELECT token_hash, email, used FROM magic_link_tokens").fetchone()
    assert row["email"] == "external@x.com"
    assert row["token_hash"] != link and row["used"] == 0
    assert client.get(f"/login/magic-link/{link}").status_code == 302
    with client.session_transaction() as session:
        assert session["v3_user"]["email"] == "external@x.com"
    assert client.get(f"/login/magic-link/{link}", follow_redirects=True).status_code == 200
    with application.config["DB"].precious() as conn:
        assert conn.execute("SELECT used FROM magic_link_tokens").fetchone()["used"] == 1


def test_beta_magic_link_denies_user_disabled_after_request(tmp_path, monkeypatch):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    repo = UserRepository(application.config["DB"])
    user = repo.create("external@x.com", role="salesman", is_external=True)
    sent = []

    class Mailer:
        def __init__(self, *_args):
            pass

        def send(self, **kwargs):
            sent.append(kwargs)

    monkeypatch.setattr("web.blueprints.auth.GraphMailer", Mailer)
    client = application.test_client()
    client.get("/login")
    with client.session_transaction() as session:
        token = session["_csrf_token"]
    client.post("/login/magic-link", data={"email": user.email, "csrf_token": token})
    link = sent[0]["body_text"].rsplit("/", 1)[-1]
    repo.update(user.id, is_active=False)
    response = client.get(f"/login/magic-link/{link}", follow_redirects=True)
    assert b"invalid or has expired" in response.data
    with client.session_transaction() as session:
        assert "v3_user" not in session


def test_role_picker_impersonates_and_allows_switch_again(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    UserRepository(application.config["DB"]).upsert("dev@x.com", role="developer", display_name="Dev")
    UserRepository(application.config["DB"]).upsert("rep@x.com", role="salesman", display_name="Sales Rep")

    client = application.test_client()
    with client.session_transaction() as s:
        s["user"] = {
            "email": "dev@x.com", "name": "Dev", "role": "developer",
            "salesman_key": None, "_dev": True, "_dev_name": "Dev", "_dev_email": "dev@x.com",
        }
        s["_csrf_token"] = "t"
    page = client.get("/dev/role-picker")
    assert page.status_code == 200
    assert b"Impersonate User" in page.data
    assert b"Sales Rep" in page.data
    resp = client.post("/dev/role-picker", data={"target_email": "rep@x.com", "csrf_token": "t"})
    assert resp.status_code == 302
    with client.session_transaction() as s:
        assert s["user"]["email"] == "rep@x.com"
        assert s["user"]["_dev"] is True
        assert s["v3_user"]["email"] == "rep@x.com"
        assert s["v3_user"]["impersonating"] is True
    again = client.get("/dev/role-picker")
    assert again.status_code == 200
    self_resp = client.post("/dev/role-picker", data={"target_email": "__self__", "csrf_token": "t"})
    assert self_resp.status_code == 302
    with client.session_transaction() as s:
        assert s["user"]["email"] == "dev@x.com"
        assert s["v3_user"]["email"] == "dev@x.com"
        assert not s["v3_user"].get("impersonating")


def test_role_picker_includes_v3_user_absent_from_live(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    UserRepository(application.config["DB"]).upsert("dev@x.com", role="developer", display_name="Dev")
    UserRepository(application.config["DB"]).upsert(
        "newbie@x.com", role="salesman", display_name="New Hire")

    client = application.test_client()
    with client.session_transaction() as s:
        s["user"] = {
            "email": "dev@x.com", "name": "Dev", "role": "developer",
            "salesman_key": None, "_dev": True, "_dev_name": "Dev", "_dev_email": "dev@x.com",
        }
        s["_csrf_token"] = "t"
    page = client.get("/dev/role-picker")
    assert page.status_code == 200
    assert b"New Hire" in page.data
    assert b"newbie@x.com" in page.data


def test_beta_adopt_keeps_v3_user_edits(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    repo = UserRepository(application.config["DB"])
    u = repo.create("rep@x.com", role="manager", display_name="Renamed",
                    sales_group="HKaufman")
    repo.set_salesman_access(u.id, ["hkaufman"])
    client = application.test_client()
    with client.session_transaction() as s:
        s["user"] = {
            "email": "rep@x.com", "name": "Live Rep", "role": "salesman",
            "salesman_key": "REdwards",
        }
        s["_csrf_token"] = "t"
    assert client.get("/").status_code == 200
    row = repo.get_by_email("rep@x.com")
    assert row.display_name == "Renamed"
    assert row.role == "manager"
    assert row.sales_group == "HKaufman"
    assert repo.get_salesman_access(u.id) == {"hkaufman"}
    with client.session_transaction() as s:
        assert (s.get("v3_user") or {}).get("name") == "Renamed"


def test_stale_dev_cookie_cannot_use_role_picker_or_admin(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    repo = UserRepository(application.config["DB"])
    u = repo.upsert("dev@x.com", role="developer", display_name="Dev")
    repo.update(u.id, role="salesman")
    client = application.test_client()
    with client.session_transaction() as s:
        s["user"] = {
            "email": "dev@x.com", "name": "Dev", "role": "developer",
            "salesman_key": None, "_dev": True, "_dev_name": "Dev",
            "_dev_email": "dev@x.com",
        }
        s["_csrf_token"] = "t"
    picker = client.get("/dev/role-picker")
    assert picker.status_code == 302
    assert client.get("/api/admin/users").status_code == 403
    assert repo.get_by_email("dev@x.com").role == "salesman"


def test_stale_dev_impersonation_cookie_cannot_keep_admin(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    repo = UserRepository(application.config["DB"])
    dev = repo.upsert("dev@x.com", role="developer", display_name="Dev")
    boss = repo.upsert("boss@x.com", role="admin", display_name="Boss")
    repo.update(dev.id, role="salesman")
    client = application.test_client()
    with client.session_transaction() as s:
        s["user"] = {
            "email": "boss@x.com", "name": "Boss (as Dev)", "role": "admin",
            "salesman_key": None, "_dev": True, "_dev_name": "Dev",
            "_dev_email": "dev@x.com",
        }
        s["_csrf_token"] = "t"
    assert client.get("/").status_code == 200
    with client.session_transaction() as s:
        v3 = s.get("v3_user") or {}
        assert v3.get("email") == "dev@x.com"
        assert v3.get("role") == "salesman"
        assert not v3.get("impersonating")
        live = s.get("user") or {}
        assert live.get("email") == "dev@x.com"
        assert live.get("_dev") is not True
        assert not live.get("_dev_email")
    assert client.get("/api/admin/users").status_code == 403
    put = client.put(
        f"/api/admin/users/{dev.id}", json={"role": "developer"},
        headers={"X-CSRF-Token": "t"},
    )
    assert put.status_code == 403
    assert repo.get_by_email("dev@x.com").role == "salesman"
    assert repo.get_by_email("boss@x.com").role == "admin"


def test_live_developer_first_login_is_denied_without_creating_v3_row(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    repo = UserRepository(application.config["DB"])
    client = application.test_client()
    with client.session_transaction() as s:
        s["user"] = {
            "email": "newdev@x.com", "name": "New Dev", "role": "developer",
            "salesman_key": None, "_dev": True, "_dev_name": "New Dev",
            "_dev_email": "newdev@x.com",
        }
        s["_csrf_token"] = "t"
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in (response.headers.get("Location") or "")
    assert repo.get_by_email("newdev@x.com") is None
    with client.session_transaction() as s:
        assert not s.get("user")
        assert not s.get("v3_user")


def test_inactive_live_cookie_logs_out_without_creating_or_updating(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    repo = UserRepository(application.config["DB"])
    user = repo.upsert("rep@x.com", role="salesman", display_name="Rep")
    repo.update(user.id, is_active=False)
    client = application.test_client()
    with client.session_transaction() as s:
        s["user"] = {
            "email": "rep@x.com", "name": "Live Rep", "role": "admin",
            "salesman_key": "REdwards",
        }
        s["_csrf_token"] = "t"
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in (response.headers.get("Location") or "")
    row = repo.get_by_email("rep@x.com")
    assert row is not None and not row.is_active and row.role == "salesman"
    with client.session_transaction() as s:
        assert not s.get("user")
        assert not s.get("v3_user")


def test_impersonating_missing_v3_user_stays_developer(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    UserRepository(application.config["DB"]).upsert("dev@x.com", role="developer", display_name="Dev")
    client = application.test_client()
    with client.session_transaction() as s:
        s["user"] = {
            "email": "ghost@x.com", "name": "Ghost (as Dev)", "role": "salesman",
            "salesman_key": None, "_dev": True, "_dev_name": "Dev",
            "_dev_email": "dev@x.com",
        }
        s["_csrf_token"] = "t"
    assert client.get("/").status_code == 200
    with client.session_transaction() as s:
        assert (s.get("v3_user") or {}).get("email") == "dev@x.com"
        assert (s.get("v3_user") or {}).get("role") == "developer"
        assert not (s.get("v3_user") or {}).get("impersonating")
    picker = client.get("/dev/role-picker")
    assert picker.status_code == 200
    assert b"ghost@x.com" not in picker.data
    missing = client.post(
        "/dev/role-picker", data={"target_email": "ghost@x.com", "csrf_token": "t"}
    )
    assert missing.status_code == 404


def test_stale_impersonation_with_missing_actor_logs_out(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    repo = UserRepository(application.config["DB"])
    repo.upsert("boss@x.com", role="admin", display_name="Boss")
    client = application.test_client()
    with client.session_transaction() as s:
        s["user"] = {
            "email": "boss@x.com", "name": "Boss (as Ghost)", "role": "admin",
            "salesman_key": None, "_dev": True, "_dev_name": "Ghost",
            "_dev_email": "ghost-dev@x.com",
        }
        s["_csrf_token"] = "t"
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in (r.headers.get("Location") or "")
    with client.session_transaction() as s:
        assert not s.get("user")
        assert not s.get("v3_user")
    assert repo.get_by_email("ghost-dev@x.com") is None

