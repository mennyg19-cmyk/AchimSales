"""The authenticated principal (who is making the request)."""

from __future__ import annotations

from dataclasses import dataclass

ROLE_ADMIN = "admin"
ROLE_DEVELOPER = "developer"
ROLE_MANAGER = "manager"
ROLE_SALESMAN = "salesman"
VALID_ROLES = (ROLE_ADMIN, ROLE_DEVELOPER, ROLE_MANAGER, ROLE_SALESMAN)

# admin + developer see everything (live convention, webapp/services/access.py).
_PRIVILEGED = frozenset({ROLE_ADMIN, ROLE_DEVELOPER})


@dataclass(frozen=True)
class Principal:
    email: str
    name: str
    role: str
    is_dev: bool = False   # True when signed in via the dev picker (local only)

    @property
    def is_privileged(self) -> bool:
        return self.role in _PRIVILEGED

    def to_dict(self) -> dict:
        return {"email": self.email, "name": self.name, "role": self.role, "is_dev": self.is_dev}

    @classmethod
    def from_dict(cls, d: dict) -> "Principal | None":
        if not isinstance(d, dict) or not d.get("email"):
            return None
        role = d.get("role") or ROLE_SALESMAN
        return cls(
            email=str(d["email"]).strip().lower(),
            name=d.get("name") or d["email"],
            role=role if role in VALID_ROLES else ROLE_SALESMAN,
            is_dev=bool(d.get("is_dev")),
        )
