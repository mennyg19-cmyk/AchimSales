"""Public site origin for emailed links and the Entra redirect URI.

Never taken from the request Host header.
"""

from __future__ import annotations

import os

_DEFAULT_PUBLIC_ORIGIN = "https://reports.achimonline.com"


def public_origin() -> str:
    explicit = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    if os.environ.get("WEBSITE_SITE_NAME") or os.environ.get("WEBSITE_INSTANCE_ID"):
        return _DEFAULT_PUBLIC_ORIGIN
    return "http://127.0.0.1:5001"
