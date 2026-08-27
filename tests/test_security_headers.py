"""Security header helper (webapp copy)."""

from werkzeug.wrappers import Response

from webapp.security_headers import apply_security_headers


def test_sets_frame_and_csp_and_optional_hsts():
    resp = Response()
    apply_security_headers(resp, hsts=False)
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "object-src 'none'" in resp.headers["Content-Security-Policy"]
    assert "unpkg.com" not in resp.headers["Content-Security-Policy"]
    assert "jsdelivr.net" not in resp.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in resp.headers
    apply_security_headers(resp, hsts=True)
    assert resp.headers["Strict-Transport-Security"] == "max-age=31536000"
