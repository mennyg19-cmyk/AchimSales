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
from web.data.repositories.users import UserRepository


def _dev_cfg(tmp_path) -> Config:
    return Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "precious.db", cache_db_path=tmp_path / "cache.db",
        litestream_blob_url="",
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
            conn.execute("INSERT OR IGNORE INTO salesmen(key) VALUES (?)", (k,))
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


def test_is_developer_ignores_session_role(db):
    authz = Authorization(db)
    users = UserRepository(db)
    users.upsert("d@b.com", role="developer")
    stale = Principal("d@b.com", "D", "salesman")
    assert authz.is_developer(stale) is True
    with db.precious() as conn:
        conn.execute("UPDATE users SET role='salesman' WHERE email='d@b.com'")
    assert authz.is_developer(stale) is False
    with pytest.raises(Forbidden):
        authz.assert_developer(stale)


def test_session_allowed_inactive_and_impersonation(db):
    authz = Authorization(db)
    users = UserRepository(db)
    users.upsert("dev@b.com", role="developer")
    target = users.upsert("rep@b.com", role="salesman")
    own = Principal("dev@b.com", "D", "developer")
    assert authz.session_allowed(own) is True
    users.update(users.get_by_email("dev@b.com").id, is_active=False)
    assert authz.session_allowed(own) is False
    users.update(users.get_by_email("dev@b.com").id, is_active=True)
    users.update(target.id, is_active=False)
    impersonating = Principal(
        "rep@b.com", "R", "salesman", impersonating=True,
        real_email="dev@b.com", real_name="D",
    )
    assert authz.session_allowed(impersonating) is True
    assert authz.is_developer(impersonating) is False
    assert authz.actor_is_developer(impersonating) is True
    users.update(users.get_by_email("dev@b.com").id, role="salesman")
    assert authz.session_allowed(impersonating) is False


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
    assert b"/login/start" in resp.data
    assert b"/legacy/" not in resp.data
    assert b"/login/magic-link" in resp.data
    assert b"next=/healthz" not in resp.data
    assert b"Developer sign-in" not in resp.data


def test_role_picker_impersonates_and_allows_switch_again(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    UserRepository(application.config["DB"]).upsert("dev@x.com", role="developer", display_name="Dev")
    UserRepository(application.config["DB"]).upsert("rep@x.com", role="salesman", display_name="Sales Rep")

    client = application.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "dev@x.com", "name": "Dev", "role": "developer", "is_dev": True}
        s["_csrf_token"] = "t"
    page = client.get("/dev/role-picker")
    assert page.status_code == 200
    assert b"Impersonate User" in page.data
    assert b"Sales Rep" in page.data
    resp = client.post("/dev/role-picker", data={"target_email": "rep@x.com", "csrf_token": "t"})
    assert resp.status_code == 302
    with client.session_transaction() as s:
        assert "user" not in s
        assert s["v3_user"]["email"] == "rep@x.com"
        assert s["v3_user"]["impersonating"] is True
    again = client.get("/dev/role-picker")
    assert again.status_code == 200
    self_resp = client.post("/dev/role-picker", data={"target_email": "__self__", "csrf_token": "t"})
    assert self_resp.status_code == 302
    with client.session_transaction() as s:
        assert s["v3_user"]["email"] == "dev@x.com"
        assert not s["v3_user"].get("impersonating")


def test_role_picker_denied_when_developer_demoted(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    UserRepository(application.config["DB"]).upsert("dev@x.com", role="developer")
    client = application.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "dev@x.com", "name": "Dev", "role": "developer", "is_dev": True}
        s["_csrf_token"] = "t"
    with application.config["DB"].precious() as conn:
        conn.execute("UPDATE users SET role='salesman' WHERE email='dev@x.com'")
    assert client.get("/dev/role-picker").status_code == 403
    assert client.post(
        "/dev/role-picker", data={"target_email": "__self__", "csrf_token": "t"}
    ).status_code == 403


def test_legacy_live_cookie_does_not_sign_in_or_create_user(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    client = application.test_client()
    with client.session_transaction() as s:
        s["user"] = {
            "email": "ghost@x.com", "name": "Ghost", "role": "admin",
            "_dev": True, "_dev_email": "ghost@x.com",
        }
    resp = client.get("/")
    assert resp.status_code in (302, 301)
    assert "/login" in (resp.headers.get("Location") or "")
    assert UserRepository(application.config["DB"]).get_by_email("ghost@x.com") is None


def test_msal_callback_unknown_user_denied(app, monkeypatch):
    monkeypatch.setattr(
        "web.blueprints.auth.msal_flow.complete_login",
        lambda cfg: {"email": "new@x.com", "name": "New"},
    )
    resp = app.test_client().get("/auth/callback")
    assert resp.status_code == 403
    assert b"Not authorized" in resp.data
    assert UserRepository(app.config["DB"]).get_by_email("new@x.com") is None


def test_msal_callback_inactive_user_denied(app, monkeypatch):
    UserRepository(app.config["DB"]).upsert("old@x.com", role="salesman")
    with app.config["DB"].precious() as conn:
        conn.execute("UPDATE users SET is_active=0 WHERE email='old@x.com'")
    monkeypatch.setattr(
        "web.blueprints.auth.msal_flow.complete_login",
        lambda cfg: {"email": "old@x.com", "name": "Old"},
    )
    resp = app.test_client().get("/auth/callback")
    assert resp.status_code == 403
    assert UserRepository(app.config["DB"]).get_by_email("old@x.com").is_active is False


def test_leftover_live_cookie_does_not_sign_in_existing_user(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    UserRepository(application.config["DB"]).upsert("a@x.com", role="admin")
    client = application.test_client()
    with client.session_transaction() as s:
        s["user"] = {
            "email": "a@x.com", "name": "A", "role": "admin", "is_admin": True,
        }
    resp = client.get("/")
    assert resp.status_code in (302, 301)
    assert "/login" in (resp.headers.get("Location") or "")
    with client.session_transaction() as s:
        assert "v3_user" not in s


def test_leftover_live_cookie_does_not_skip_role_refresh(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    UserRepository(application.config["DB"]).upsert("a@x.com", role="admin")
    client = application.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "a@x.com", "name": "A", "role": "admin"}
        s["user"] = {
            "email": "a@x.com", "name": "A", "role": "admin", "is_admin": True,
        }
    with application.config["DB"].precious() as conn:
        conn.execute("UPDATE users SET role='salesman' WHERE email='a@x.com'")
    client.get("/")
    with client.session_transaction() as s:
        assert s["v3_user"]["role"] == "salesman"


def test_role_picker_denied_for_admin_even_with_is_dev_cookie(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    UserRepository(application.config["DB"]).upsert("admin@x.com", role="admin")
    client = application.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {
            "email": "admin@x.com", "name": "A", "role": "admin", "is_dev": True,
        }
        s["_csrf_token"] = "t"
    assert client.get("/dev/role-picker").status_code == 403
    assert client.post(
        "/dev/role-picker", data={"target_email": "__self__", "csrf_token": "t"}
    ).status_code == 403


def test_role_picker_denied_when_impersonating_actor_demoted(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    UserRepository(application.config["DB"]).upsert("dev@x.com", role="developer")
    UserRepository(application.config["DB"]).upsert("rep@x.com", role="salesman")
    client = application.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {
            "email": "rep@x.com", "name": "Rep (as Dev)", "role": "salesman",
            "is_dev": True, "impersonating": True,
            "real_email": "dev@x.com", "real_name": "Dev",
        }
        s["_csrf_token"] = "t"
    with application.config["DB"].precious() as conn:
        conn.execute("UPDATE users SET role='salesman' WHERE email='dev@x.com'")
    resp = client.get("/dev/role-picker")
    assert resp.status_code in (302, 403)
    if resp.status_code in (301, 302):
        assert "/login" in (resp.headers.get("Location") or "")


def test_magic_link_records_trusted_proxy_ip_not_leftmost_xff(tmp_path):
    from dataclasses import replace

    cfg = replace(_dev_cfg(tmp_path), is_beta=True)
    application = create_app(cfg)
    migrate(application.config["DB"])
    users = UserRepository(application.config["DB"])
    row = users.upsert("rep@x.com", role="salesman")
    users.update(row.id, is_external=True)
    client = application.test_client()
    with client.session_transaction() as s:
        s["_csrf_token"] = "t"
    client.post(
        "/login/magic-link",
        data={"email": "rep@x.com", "csrf_token": "t"},
        headers={"X-Forwarded-For": "1.2.3.4, 9.9.9.9"},
    )
    with application.config["DB"].precious() as conn:
        attempt_ips = [r[0] for r in conn.execute(
            "SELECT ip FROM magic_link_attempts"
        )]
        token_ips = [r[0] for r in conn.execute(
            "SELECT request_ip FROM magic_link_tokens"
        )]
    assert attempt_ips == ["9.9.9.9"]
    assert "1.2.3.4" not in attempt_ips
    assert token_ips == ["9.9.9.9"]


def test_rotated_secret_rejects_old_session_cookie(tmp_path):
    from dataclasses import replace

    old = replace(_dev_cfg(tmp_path), is_beta=True, flask_secret="old-secret")
    app_old = create_app(old)
    migrate(app_old.config["DB"])
    UserRepository(app_old.config["DB"]).upsert("a@x.com", role="admin")
    c_old = app_old.test_client()
    with c_old.session_transaction() as s:
        s["v3_user"] = {"email": "a@x.com", "name": "A", "role": "admin"}
    cookie = c_old.get_cookie("session")
    assert cookie is not None

    new = replace(_dev_cfg(tmp_path), is_beta=True, flask_secret="new-secret")
    app_new = create_app(new)
    c_new = app_new.test_client()
    c_new.set_cookie("session", cookie.value)
    resp = c_new.get("/")
    assert resp.status_code in (301, 302)
    assert "/login" in (resp.headers.get("Location") or "")
