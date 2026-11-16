"""Warehouse dashboard access: email allowlist only (not role-based)."""

from __future__ import annotations

DEFAULT_ALLOWED_EMAILS = ("bgrossman@achimonline.com",)


def parse_allowed_emails(raw: str | None) -> frozenset[str]:
    """Comma-separated emails → lowercase set. Empty raw → default Baruch only."""
    if raw is None or not str(raw).strip():
        return frozenset(DEFAULT_ALLOWED_EMAILS)
    emails = {
        part.strip().lower()
        for part in str(raw).split(",")
        if part.strip()
    }
    return frozenset(emails) if emails else frozenset(DEFAULT_ALLOWED_EMAILS)


def email_may_access_wh_dashboard(
    email: str | None, allowed: frozenset[str] | tuple[str, ...] | list[str],
) -> bool:
    """True when the signed-in email/UPN is on the allowlist (case-insensitive)."""
    if not email:
        return False
    allowed_set = frozenset(a.strip().lower() for a in allowed if a and str(a).strip())
    return email.strip().lower() in allowed_set
