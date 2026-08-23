"""Who is making the request."""

# === What's in this file ===
# A Principal is the signed-in person: their email, display name, and role.
# It's immutable -- once built for a request it doesn't change. Roles decide
# what someone can do; "privileged" (a developer/admin, granted via the
# configured developer-email list) means they see everything. Everyone else is a
# regular user scoped to their own salesman number(s).
#
# Principal -- the immutable signed-in identity for one request

from __future__ import annotations

from dataclasses import dataclass

ROLE_DEVELOPER = "developer"
ROLE_USER = "user"

_PRIVILEGED = frozenset({ROLE_DEVELOPER})


@dataclass(frozen=True)
class Principal:
    email: str
    name: str
    role: str

    @property
    def is_privileged(self) -> bool:
        return self.role in _PRIVILEGED
