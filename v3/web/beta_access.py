"""Live-DB gate for Beta access (mirrors test_access_enabled)."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def user_has_beta_access(email: str | None) -> bool:
    """True when the live user row has beta_access_enabled=1.

    Developers/admins still need the flag (or we treat role developer/admin as
    allowed when the column is missing during rollout — see below).
    """
    if not email:
        return False
    email = email.strip().lower()
    try:
        from webapp.db import get_db

        conn = get_db()
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(app_users)").fetchall()]
            if "beta_access_enabled" not in cols:
                # Pre-migration: allow developers/admins only so Beta isn't locked out.
                row = conn.execute(
                    "SELECT role FROM app_users WHERE email = ?",
                    (email,),
                ).fetchone()
                return bool(row and row["role"] in ("admin", "developer"))
            row = conn.execute(
                "SELECT beta_access_enabled, role FROM app_users WHERE email = ?",
                (email,),
            ).fetchone()
            if row is None:
                return False
            if row["beta_access_enabled"]:
                return True
            # Developers always reach Beta so they can flip sources / debug.
            return row["role"] in ("developer",)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - fail closed
        log.exception("beta access check failed for %s", email)
        return False
