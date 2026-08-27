"""Legacy mutating requests require a per-session CSRF token."""

from flask import Flask

from webapp.csrf import _SESSION_KEY, init_csrf


def _app():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    init_csrf(app)

    @app.post("/write")
    def write():
        return {"ok": True}

    @app.get("/login-page")
    def login_page():
        from webapp.csrf import csrf_token
        return csrf_token()

    return app


def test_csrf_blocks_write_without_token():
    client = _app().test_client()
    assert client.post("/write").status_code == 400


def test_csrf_allows_write_with_header():
    client = _app().test_client()
    with client.session_transaction() as sess:
        sess[_SESSION_KEY] = "known-token"
    resp = client.post("/write", headers={"X-CSRF-Token": "known-token"})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


def test_csrf_allows_write_with_form_field():
    client = _app().test_client()
    with client.session_transaction() as sess:
        sess[_SESSION_KEY] = "known-token"
    resp = client.post("/write", data={"csrf_token": "known-token"})
    assert resp.status_code == 200


def test_csrf_rejects_mismatched_token():
    client = _app().test_client()
    with client.session_transaction() as sess:
        sess[_SESSION_KEY] = "known-token"
    assert client.post("/write", headers={"X-CSRF-Token": "wrong"}).status_code == 400


def test_csrf_skips_get():
    client = _app().test_client()
    assert client.get("/login-page").status_code == 200


def test_entra_callback_post_is_exempt():
    from flask import Blueprint

    app = Flask(__name__)
    app.secret_key = "test-secret"
    bp = Blueprint("auth", __name__)

    @bp.route("/auth/callback", methods=["POST"])
    def auth_callback():
        return "ok"

    app.register_blueprint(bp)
    init_csrf(app)
    assert app.test_client().post("/auth/callback").status_code == 200
