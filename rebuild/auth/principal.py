"""Who is making the request."""

# === What's in this file ===
# A Principal is the signed-in person: their email, display name, and role.
# It's immutable -- once built for a request it doesn't change. Roles decide
# what someone can do; "privileged" (admin/developer) means they see everything.
# Report-level and salesman-scope rules arrive with the report phase; for now a
# principal is either privileged or a regular user.
#
# Principal -- the immutable signed-in identity for one request

from __future__ import annotations

from dataclasses import dataclass

ROLE_DEVELOPER = "developer"
ROLE_ADMIN = "admin"
ROLE_USER = "user"

_PRIVILEGED = frozenset({ROLE_DEVELOPER, ROLE_ADMIN})


@dataclass(frozen=True)
class Principal:
    email: str
    name: str
    role: str

    @property
    def is_privileged(self) -> bool:
        return self.role in _PRIVILEGED
