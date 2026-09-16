"""15-minute external magic-link tokens (itsdangerous)."""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import config

_SALT = "home-magic-link"
_MAX_AGE = 15 * 60


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(config.session_secret(), salt=_SALT)


def issue_token(email: str) -> str:
    return _serializer().dumps({"email": email.strip().lower()})


def read_token(token: str) -> str | None:
    try:
        data = _serializer().loads(token, max_age=_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    email = str(data.get("email") or "").strip().lower()
    return email or None
