"""Path routing around the Flask apps (no app imports here — tests use dummies).

When Beta is the site home:
  /              -> Beta (v3 is_beta)
  /legacy/...    -> former Live app
  /beta/...      -> 302 to the same path without /beta
  /auth/...      -> Live at site root (Entra redirect URI stays /auth/callback)
  /login/start, /login/magic-link... -> 307 to /legacy/... (MSAL + magic links)
  /login, /logout, /dev/role-picker  -> home (Beta)
"""

from __future__ import annotations


def _join_qs(path: str, environ: dict) -> str:
    qs = environ.get("QUERY_STRING") or ""
    if qs:
        return f"{path}?{qs}"
    return path


class PrefixRedirectMiddleware:
    """302 /beta/foo -> /foo (and /beta -> /)."""

    def __init__(self, app, prefix: str):
        self.app = app
        self.prefix = (prefix or "/beta").rstrip("/") or "/beta"

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO") or ""
        if path == self.prefix or path.startswith(self.prefix + "/"):
            dest = path[len(self.prefix) :] or "/"
            start_response(
                "302 Found",
                [("Location", _join_qs(dest, environ)), ("Content-Length", "0")],
            )
            return [b""]
        return self.app(environ, start_response)


def _is_live_login_path(path: str) -> bool:
    """MSAL start + magic-link stay on Live. /login itself is the home app."""
    if path == "/dev-login" or path.startswith("/dev-login"):
        return True
    if path == "/login/start" or path.startswith("/login/start"):
        return True
    return path.startswith("/login/magic-link")


class LiveRootAuthMiddleware:
    """Entra callback stays on Live at /. Login HTML is the home app."""

    def __init__(self, app, live_app, legacy_prefix: str = "/legacy"):
        self.app = app
        self.live_app = live_app
        self.legacy = (legacy_prefix or "/legacy").rstrip("/") or "/legacy"

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO") or ""
        if path == self.legacy:
            start_response(
                "302 Found",
                [("Location", _join_qs(self.legacy + "/", environ)), ("Content-Length", "0")],
            )
            return [b""]
        if path == "/auth" or path.startswith("/auth/"):
            return self.live_app(environ, start_response)
        if _is_live_login_path(path):
            start_response(
                "307 Temporary Redirect",
                [
                    ("Location", _join_qs(self.legacy + path, environ)),
                    ("Content-Length", "0"),
                ],
            )
            return [b""]
        return self.app(environ, start_response)


def mount_beta_as_home(
    beta_app,
    live_app,
    extra_mounts: dict,
    *,
    legacy: str = "/legacy",
    beta_redirect: str = "/beta",
):
    from werkzeug.middleware.dispatcher import DispatcherMiddleware

    mounts = dict(extra_mounts)
    mounts[legacy] = live_app
    inner = DispatcherMiddleware(beta_app, mounts)
    return PrefixRedirectMiddleware(
        LiveRootAuthMiddleware(inner, live_app, legacy),
        beta_redirect,
    )
