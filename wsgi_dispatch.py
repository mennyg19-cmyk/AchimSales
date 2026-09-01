"""Path helpers around the home Flask app (no app imports — tests use dummies)."""

from __future__ import annotations


def _join_qs(path: str, environ: dict) -> str:
    qs = environ.get("QUERY_STRING") or ""
    if qs:
        return f"{path}?{qs}"
    return path


class PrefixRedirectMiddleware:
    """302 /beta/foo -> /foo (and /beta -> /)."""

    def __init__(self, app, prefix: str = "/beta"):
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
