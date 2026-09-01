"""Browser security headers applied to every response."""

from __future__ import annotations

# 'unsafe-inline' stays for existing page scripts. Feather and Tabulator are
# local. Google Maps stays on Google's CDN (dynamic loader, no SRI).
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' "
    "https://maps.googleapis.com https://maps.gstatic.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https:; "
    "font-src 'self' data:; "
    "connect-src 'self' https:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)

SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": _CSP,
}


def apply_security_headers(response, *, hsts: bool = False):
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    if hsts:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000"
        )
    return response
