"""Session-backed principal storage."""

from __future__ import annotations

from urllib.parse import quote

from flask import session

from web.auth.principal import Principal

_SESSION_KEY = "v3_user"


def current_principal() -> Principal | None:
    return Principal.from_dict(session.get(_SESSION_KEY) or {})


def login(principal: Principal) -> None:
    session[_SESSION_KEY] = principal.to_dict()
    session.permanent = True


def logout() -> None:
    session.pop(_SESSION_KEY, None)
    session.pop("user", None)


def safe_internal_path(path: str, *, fallback: str = "/") -> str:
    """Same-app relative path only. Rejects protocol-relative and backslash tricks."""
    raw = path or ""
    if not raw.startswith("/") or raw.startswith("//"):
        return fallback
    if "\\" in raw or "%5c" in raw.lower():
        return fallback
    return raw


def login_redirect(next_path: str = "/") -> str:
    safe = safe_internal_path(next_path, fallback="/")
    return f"/login?next={quote(safe, safe='/?=&')}"


def refresh_from_db(*, role: str, is_dev: bool | None) -> None:
    # Presentation cache only. Authorization re-reads role from the DB.
    data = session.get(_SESSION_KEY)
    if not isinstance(data, dict):
        return
    updated = {**data, "role": role}
    if is_dev is not None:
        updated["is_dev"] = is_dev
    if updated != data:
        session[_SESSION_KEY] = updated
